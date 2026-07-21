"""
add_reference_labels_and_rescore.py

Attaches canonical PBMC3k reference cell-type labels (standard, widely-
published cluster identities from the Seurat/Scanpy PBMC3k tutorials,
matched here to the specific clustering your pipeline produced at seed=0)
and re-scores an already-annotated h5ad from Baseline 1 or Baseline 2.

IMPORTANT CAVEAT: this reference mapping is tied to the exact clustering
produced by data_utils.preprocess_and_cluster with seed=0. It is a sanity-
check convenience, not an independent expert-verified ground truth. Do
NOT use these numbers in your paper. Use them to iterate quickly while
you get GenoTEX access. Your real, citable numbers must come from a
dataset with genuine independent ground truth (GenoTEX).

Usage (single run):
    python src/eval/add_reference_labels_and_rescore.py \
        --h5ad experiments/results/baseline2_pbmc3k_trial0_annotated.h5ad \
        --condition-name baseline2_llama3.2-3b \
        --trial 0

This appends one row to experiments/results/baseline2_llama3.2-3b.csv.
Run it once per trial, then use aggregate_results.py to get mean +/- std
across all trials.
"""

import argparse
import sys
from pathlib import Path

import scanpy as sc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.eval.score import (
    compute_task_metrics,
    compute_per_class_f1,
    RunResult,
    OrchestrationLog,
    CostLog,
    save_result,
)


# Canonical identities for the seed=0 clustering from data_utils.py.
# Re-derive this mapping if you change clustering parameters — cluster IDs
# and boundaries will shift. Do NOT reuse this for a different seed's
# clustering without re-deriving it (cluster ids won't mean the same thing).
REFERENCE_LABELS = {
    "0": "CD4 T cell",       # ribosomal genes + CD3D
    "1": "CD14+ Monocyte",   # S100A9, LYZ, S100A8, FCN1
    "2": "CD8 T cell",       # NKG7, GZMA, CST7, PRF1, CCL5
    "3": "B cell",           # CD79A, CD79B, MS4A1
    "4": "FCGR3A+ Monocyte", # LST1, FCER1G, AIF1, FCGR3A
    "5": "Dendritic cell",   # HLA-DPA1, FCER1A, CST3
    "6": "Platelet",         # SDPR, PF4, PPBP
    "7": "CD4 T cell",       # proliferation markers, ambiguous — closest call
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5ad", required=True)
    parser.add_argument("--condition-name", default="sanity_check")
    parser.add_argument("--trial", type=int, default=0, help="trial/repeat index, saved as the 'seed' column for aggregation")
    parser.add_argument("--dataset", default="pbmc3k")
    args = parser.parse_args()

    adata = sc.read_h5ad(args.h5ad)

    missing = set(adata.obs["leiden"].astype(str).unique()) - set(REFERENCE_LABELS.keys())
    if missing:
        print(
            f"WARNING: clusters {missing} not in REFERENCE_LABELS — this "
            "usually means your clustering used a different seed/resolution "
            "than seed=0 (check you passed --seed 0 to the baseline script). "
            "Skipping save — fix clustering seed and re-run."
        )
        return

    adata.obs["ground_truth_cell_type"] = (
        adata.obs["leiden"].astype(str).map(REFERENCE_LABELS)
    )

    y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
    y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()

    metrics = compute_task_metrics(y_true, y_pred)
    per_class = compute_per_class_f1(y_true, y_pred)

    print(f"\n=== {args.condition_name} trial {args.trial} (SANITY CHECK ONLY — not paper numbers) ===")
    print("Task metrics:", metrics)
    print("Per-class F1:", per_class)

    result = RunResult(
        condition=args.condition_name,
        dataset=args.dataset,
        seed=args.trial,
        task_metrics=metrics,
        orchestration_log=OrchestrationLog(iterations_used=1, max_iterations=1),
        cost_log=CostLog(),  # token/cost info lives in the baseline script's own save; this is a rescoring pass
        notes="sanity-check scoring against PBMC3k reference labels, NOT paper-grade ground truth",
    )
    path = save_result(result)
    print(f"Saved to {path}")
    print(
        "\nReminder: this reference mapping is derived from the same "
        "canonical marker-gene logic as Baseline 1's own method, so it is "
        "NOT an independent ground truth. Use GenoTEX for real results."
    )


if __name__ == "__main__":
    main()

