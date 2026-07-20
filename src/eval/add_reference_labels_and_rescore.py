"""
add_reference_labels_and_rescore.py

Attaches canonical PBMC3k reference cell-type labels (standard, widely-
published cluster identities from the Seurat/Scanpy PBMC3k tutorials,
matched here to the specific clustering your pipeline produced) and
re-scores an already-annotated h5ad from Baseline 1 or Baseline 2.

IMPORTANT CAVEAT: this reference mapping is tied to the exact clustering
in your run (seed=0, resolution=0.6 from data_utils.py) — it is a sanity-
check convenience, not an independent expert-verified ground truth. Do
NOT use these numbers in your paper. Use them to iterate quickly while
you get GenoTEX access. Your real, citable numbers must come from a
dataset with genuine independent ground truth (GenoTEX).

Usage:
    python src/eval/add_reference_labels_and_rescore.py \
        --h5ad experiments/results/baseline2_pbmc3k_seed0_annotated.h5ad \
        --condition-name baseline2_pbmc3k_sanitycheck
"""

import argparse
import sys
from pathlib import Path

import scanpy as sc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.eval.score import compute_task_metrics, compute_per_class_f1


# Canonical identities for this exact clustering (seed=0, resolution=0.6,
# data_utils.preprocess_and_cluster). Re-derive this mapping if you change
# the clustering parameters — cluster IDs and boundaries will shift.
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
    args = parser.parse_args()

    adata = sc.read_h5ad(args.h5ad)

    missing = set(adata.obs["leiden"].astype(str).unique()) - set(REFERENCE_LABELS.keys())
    if missing:
        print(
            f"WARNING: clusters {missing} not in REFERENCE_LABELS — this "
            "usually means your clustering produced a different number of "
            "clusters than the reference mapping expects (check seed/"
            "resolution match data_utils.py). Update REFERENCE_LABELS above."
        )

    adata.obs["ground_truth_cell_type"] = (
        adata.obs["leiden"].astype(str).map(REFERENCE_LABELS)
    )

    y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
    y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()

    metrics = compute_task_metrics(y_true, y_pred)
    per_class = compute_per_class_f1(y_true, y_pred)

    print(f"\n=== {args.condition_name} (SANITY CHECK ONLY — not paper numbers) ===")
    print("Task metrics:", metrics)
    print("Per-class F1:", per_class)
    print(
        "\nReminder: this reference mapping is derived from the same "
        "canonical marker-gene logic as Baseline 1's own method, so it is "
        "NOT an independent ground truth. Use GenoTEX for real results."
    )


if __name__ == "__main__":
    main()
