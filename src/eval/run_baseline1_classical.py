"""
run_baseline1_classical.py

Baseline 1 (protocol Section 4): standard Scanpy pipeline with rule-based,
marker-gene-scoring cell-type annotation. No LLM anywhere in this script.
This is the "classical bioinformatics floor" every other condition must beat.

Pipeline: QC filter -> normalize -> log1p -> HVG -> PCA -> neighbors ->
Leiden clustering -> per-cluster marker-gene-score annotation.

IMPORTANT — ground truth caveat:
PBMC3k (the sanity-check dataset) does not ship official expert-verified
cell-type labels. This script will run end-to-end and print predictions
regardless, but scoring against score.py's metrics only happens if you
provide ground truth in `adata.obs["ground_truth_cell_type"]`.
For your real, citable results, run this same pipeline against GenoTEX
(which does have expert ground truth) — see data/README.md.

Usage:
    python src/eval/run_baseline1_classical.py --dataset pbmc3k --seed 0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import scanpy as sc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.eval.score import (
    RunResult,
    OrchestrationLog,
    CostLog,
    compute_task_metrics,
    compute_per_class_f1,
    save_result,
)


# ---------------------------------------------------------------------------
# Canonical PBMC marker genes (standard, widely published — e.g. Seurat/
# Scanpy PBMC3k tutorials). Swap this dict out entirely when you move to a
# different tissue/dataset; do not assume it generalizes.
# ---------------------------------------------------------------------------

PBMC_MARKERS = {
    "CD4 T cell": ["IL7R", "CD3D", "CD3E"],
    "CD8 T cell": ["CD8A", "CD3D", "CD3E"],
    "B cell": ["MS4A1", "CD79A", "CD79B"],
    "NK cell": ["GNLY", "NKG7", "KLRD1"],
    "CD14+ Monocyte": ["CD14", "LYZ", "S100A8"],
    "FCGR3A+ Monocyte": ["FCGR3A", "MS4A7"],
    "Dendritic cell": ["FCER1A", "CST3"],
    "Platelet": ["PPBP", "PF4"],
}


def load_dataset(name: str, path: str | None = None) -> sc.AnnData:
    if path:
        return sc.read_h5ad(path)
    if name == "pbmc3k":
        # NOTE: this downloads from a 10x/Scanpy-hosted URL — requires
        # internet access. If it fails in a restricted environment, download
        # manually and pass --data-path instead.
        return sc.datasets.pbmc3k()
    raise ValueError(f"Unknown dataset '{name}'. Use --data-path for custom data.")


def preprocess(adata: sc.AnnData, seed: int) -> sc.AnnData:
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    adata.var["mt"] = adata.var_names.str.startswith("MT-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True, percent_top=None)
    adata = adata[adata.obs["pct_counts_mt"] < 20].copy()

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    adata.raw = adata  # keep full log-normalized matrix for marker scoring

    if adata.n_vars > 50:
        n_top = min(2000, adata.n_vars)
        sc.pp.highly_variable_genes(adata, n_top_genes=n_top)
        adata = adata[:, adata.var.highly_variable].copy()
    else:
        print(
            f"[baseline1] only {adata.n_vars} genes present — skipping HVG "
            "selection (expected for small/test panels, not real scRNA-seq data)"
        )
    sc.pp.scale(adata, max_value=10)

    sc.tl.pca(adata, svd_solver="arpack", random_state=seed)
    sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40, random_state=seed)
    sc.tl.leiden(adata, resolution=0.6, random_state=seed)

    return adata


def annotate_clusters(adata: sc.AnnData, markers: dict) -> dict[str, str]:
    """
    Rule-based annotation: score each cluster against each candidate cell
    type's marker set using Scanpy's score_genes, assign the highest-scoring
    label per cluster. Pure classical bioinformatics, no LLM.
    """
    raw = adata.raw.to_adata()

    for cell_type, genes in markers.items():
        present = [g for g in genes if g in raw.var_names]
        if not present:
            continue
        sc.tl.score_genes(raw, gene_list=present, score_name=f"score_{cell_type}")

    score_cols = [f"score_{ct}" for ct in markers if f"score_{ct}" in raw.obs.columns]

    cluster_to_label = {}
    for cluster_id in adata.obs["leiden"].cat.categories:
        mask = adata.obs["leiden"] == cluster_id
        mean_scores = raw.obs.loc[mask, score_cols].mean()
        best = mean_scores.idxmax().replace("score_", "")
        cluster_to_label[cluster_id] = best

    return cluster_to_label


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="pbmc3k")
    parser.add_argument("--data-path", default=None, help="path to a local .h5ad file")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    np.random.seed(args.seed)
    t0 = time.time()

    print(f"[baseline1] loading dataset={args.dataset} seed={args.seed}")
    adata = load_dataset(args.dataset, args.data_path)

    print(f"[baseline1] preprocessing + clustering ({adata.n_obs} cells)")
    adata = preprocess(adata, seed=args.seed)
    n_clusters = adata.obs["leiden"].nunique()
    print(f"[baseline1] found {n_clusters} clusters")

    print("[baseline1] annotating clusters via marker-gene scoring")
    cluster_to_label = annotate_clusters(adata, PBMC_MARKERS)
    for cid, label in sorted(cluster_to_label.items()):
        n_cells = (adata.obs["leiden"] == cid).sum()
        print(f"    cluster {cid} ({n_cells} cells) -> {label}")

    adata.obs["predicted_cell_type"] = adata.obs["leiden"].map(cluster_to_label)

    elapsed = time.time() - t0

    if "ground_truth_cell_type" in adata.obs.columns:
        y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
        y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()

        metrics = compute_task_metrics(y_true, y_pred)
        per_class = compute_per_class_f1(y_true, y_pred)
        print("[baseline1] task metrics:", metrics)
        print("[baseline1] per-class F1:", per_class)

        result = RunResult(
            condition="baseline1_classical",
            dataset=args.dataset,
            seed=args.seed,
            task_metrics=metrics,
            orchestration_log=OrchestrationLog(iterations_used=1, max_iterations=1),
            cost_log=CostLog(wall_clock_seconds=elapsed),  # no tokens — no LLM
            notes="classical pipeline, no LLM, rule-based marker scoring",
        )
        path = save_result(result)
        print(f"[baseline1] saved result to {path}")
    else:
        print(
            "[baseline1] WARNING: no 'ground_truth_cell_type' column found in "
            "adata.obs — skipping scoring. This is expected for raw PBMC3k. "
            "Add ground truth labels (e.g. from GenoTEX) to get real metrics."
        )

    out_path = Path(__file__).resolve().parents[2] / "experiments" / "results" / f"baseline1_{args.dataset}_seed{args.seed}_annotated.h5ad"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    print(f"[baseline1] wrote annotated AnnData to {out_path}")
    print(f"[baseline1] done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
