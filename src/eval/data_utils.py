"""
data_utils.py

Shared dataset loading, QC, and clustering logic used by EVERY condition
(Baseline 1, 2, 3, orchestrated system). This is deliberately factored out
so that all conditions cluster the data identically — only the annotation
step differs between conditions. If each condition re-clustered
independently, differences in cluster boundaries would confound the
comparison and you wouldn't know whether accuracy differences come from
the annotation method or from different clustering.
"""

from __future__ import annotations

import scanpy as sc
import pandas as pd


def load_dataset(name: str, path: str | None = None) -> sc.AnnData:
    if path:
        return sc.read_h5ad(path)
    if name == "pbmc3k":
        # sanity-check dataset only — has NO ground truth labels
        return sc.datasets.pbmc3k()
    if name == "pbmc68k_reduced":
        # REAL evaluation dataset: genuine FACS-sorted ground truth (Zheng
        # et al. 2017), 10 cell types, 700 cells (reduced/HVG-subset
        # version bundled with Scanpy — no download needed).
        # .X in the raw object is log-normalized; the top-level .X is
        # already z-scored for the tutorial's own PCA, which we don't want
        # to reuse (we re-cluster ourselves for methodological consistency
        # across all conditions). Restore log-normalized values, rename
        # the label column to the standard name every scoring script
        # expects, and let preprocess_and_cluster take it from here.
        adata = sc.datasets.pbmc68k_reduced()
        adata = adata.raw.to_adata()
        adata.obs["ground_truth_cell_type"] = adata.obs["bulk_labels"].astype(str)
        return adata
    raise ValueError(f"Unknown dataset '{name}'. Use --data-path for custom data.")


def preprocess_and_cluster(adata: sc.AnnData, seed: int, already_normalized: bool = False) -> sc.AnnData:
    """
    Standard QC + normalize + cluster pipeline. Identical across all
    conditions — do not modify per-condition, modify here once if the
    protocol changes.

    already_normalized: set True for datasets that arrive already QC'd,
    normalized, log-transformed, and HVG-subsetted (e.g. pbmc68k_reduced).
    Skips redundant steps but still re-runs OUR OWN scale/PCA/neighbors/
    Leiden clustering, so clustering methodology stays consistent across
    every dataset and condition — we never reuse a dataset's bundled
    clusters, only its ground-truth labels.
    """
    if not already_normalized:
        sc.pp.filter_cells(adata, min_genes=200)
        sc.pp.filter_genes(adata, min_cells=3)

        adata.var["mt"] = adata.var_names.str.startswith("MT-")
        sc.pp.calculate_qc_metrics(adata, qc_vars=["mt"], inplace=True, percent_top=None)
        adata = adata[adata.obs["pct_counts_mt"] < 20].copy()

        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)

    adata.raw = adata  # keep full log-normalized matrix for marker gene lookup

    if not already_normalized:
        if adata.n_vars > 50:
            n_top = min(2000, adata.n_vars)
            sc.pp.highly_variable_genes(adata, n_top_genes=n_top)
            adata = adata[:, adata.var.highly_variable].copy()
        else:
            print(
                f"[data_utils] only {adata.n_vars} genes present — skipping HVG "
                "selection (expected for small/test panels, not real scRNA-seq data)"
            )

    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, svd_solver="arpack", random_state=seed)
    sc.pp.neighbors(adata, n_neighbors=10, n_pcs=min(40, adata.obsm["X_pca"].shape[1]), random_state=seed)
    sc.tl.leiden(adata, resolution=0.6, random_state=seed)

    return adata


def get_cluster_marker_genes(adata: sc.AnnData, n_genes: int = 10) -> dict[str, list[str]]:
    """
    Top differentially-expressed genes per cluster via Wilcoxon rank-sum
    test. This is what gets handed to the LLM (Baseline 2+) instead of a
    hand-curated marker dict — more realistic and generalizes beyond PBMC.
    """
    raw = adata.raw.to_adata()
    raw.obs["leiden"] = adata.obs["leiden"]
    sc.tl.rank_genes_groups(raw, groupby="leiden", method="wilcoxon", n_genes=n_genes)

    result = {}
    for cluster_id in raw.obs["leiden"].cat.categories:
        genes = raw.uns["rank_genes_groups"]["names"][cluster_id][:n_genes]
        result[cluster_id] = list(genes)
    return result


def cluster_sizes(adata: sc.AnnData) -> dict[str, int]:
    return adata.obs["leiden"].value_counts().to_dict()
