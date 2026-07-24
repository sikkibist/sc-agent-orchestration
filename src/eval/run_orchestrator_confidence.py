"""
run_orchestrator_confidence.py

The confidence-weighted tie-break ablation (deferred from the original
orchestrator design discussion): same classical + LLM specialists as
run_orchestrator.py, but disagreements are resolved by comparing
confidence signals from each specialist's ORIGINAL call, instead of a
second arbitration LLM call. Cheaper (one LLM call per trial instead of
up to two) — worth comparing both cost and accuracy against
run_orchestrator.py's arbitration approach.

Usage (default — free, local Ollama):
    python src/eval/run_orchestrator_confidence.py --seed 0 --trial 0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.eval.score import (
    RunResult,
    OrchestrationLog,
    CostLog,
    compute_task_metrics,
    compute_per_class_f1,
    normalize_label,
    save_result,
)
from src.eval.data_utils import load_dataset, preprocess_and_cluster, get_cluster_marker_genes
from src.eval.run_baseline1_classical import PBMC_MARKERS, annotate_clusters_with_confidence
from src.eval.run_baseline2_single_llm import PROVIDERS, CANDIDATE_LABELS
from src.eval.confidence_tiebreak import (
    build_confidence_prompt,
    parse_confidence_response,
    reconcile_by_confidence,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="pbmc68k_reduced")
    parser.add_argument("--data-path", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trial", type=int, default=0)
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="ollama")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--input-price", type=float, default=None)
    parser.add_argument("--output-price", type=float, default=None)
    args = parser.parse_args()

    np.random.seed(args.seed)
    t0 = time.time()

    print(f"[orch-conf] loading dataset={args.dataset} seed={args.seed}")
    adata = load_dataset(args.dataset, args.data_path)

    print(f"[orch-conf] preprocessing + clustering ({adata.n_obs} cells)")
    adata = preprocess_and_cluster(adata, seed=args.seed, already_normalized=(args.dataset == "pbmc68k_reduced"))
    n_clusters = adata.obs["leiden"].nunique()
    print(f"[orch-conf] found {n_clusters} clusters")

    cluster_markers = get_cluster_marker_genes(adata, n_genes=10)
    expected_clusters = list(cluster_markers.keys())

    call_fn = PROVIDERS[args.provider]

    print("[orch-conf] running classical specialist (with confidence)")
    classical_results = annotate_clusters_with_confidence(adata, PBMC_MARKERS)
    for cid, (label, margin) in sorted(classical_results.items()):
        print(f"    cluster {cid}: {label} (margin={margin:.4f})")

    print("[orch-conf] running LLM specialist (with self-reported confidence)")
    prompt = build_confidence_prompt(cluster_markers, CANDIDATE_LABELS)
    response_text, in_tok, out_tok = call_fn(prompt, args.model)
    llm_results_raw = parse_confidence_response(response_text, expected_clusters)

    llm_results_normalized = {
        cid: (normalize_label(label, CANDIDATE_LABELS), conf)
        for cid, (label, conf) in llm_results_raw.items()
    }
    for cid, (label, conf) in sorted(llm_results_normalized.items()):
        print(f"    cluster {cid}: {label} (confidence={conf:.0f})")

    print("[orch-conf] reconciling by confidence")
    result = reconcile_by_confidence(classical_results, llm_results_normalized, CANDIDATE_LABELS)
    print(
        f"[orch-conf] agree={result['n_agree']}, llm_won={result['n_llm_won']}, "
        f"classical_won_tiebreak={result['n_classical_won_tiebreak']}, "
        f"invalid_llm_high_conf={result['n_fallback_invalid_llm']}, "
        f"margin_cutoff={result['margin_cutoff']:.4f}"
    )
    print(f"    final labels: {result['final_labels']}")

    final_labels = result["final_labels"]
    adata.obs["predicted_cell_type"] = adata.obs["leiden"].astype(str).map(final_labels)
    total_elapsed = time.time() - t0

    estimated_cost = None
    if args.input_price is not None and args.output_price is not None:
        estimated_cost = (
            in_tok / 1_000_000 * args.input_price + out_tok / 1_000_000 * args.output_price
        )

    if "ground_truth_cell_type" in adata.obs.columns:
        y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
        y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()
        metrics = compute_task_metrics(y_true, y_pred)
        per_class = compute_per_class_f1(y_true, y_pred)
        print("[orch-conf] final task metrics:", metrics)
        print("[orch-conf] per-class F1:", per_class)

        orch_log = OrchestrationLog(
            iterations_used=1,
            max_iterations=1,
            converged=True,
            escalated=(result["n_llm_won"] > 0),
        )

        run_result = RunResult(
            condition=f"orchestrator_confidence_{args.provider}_{args.model}",
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics,
            orchestration_log=orch_log,
            cost_log=CostLog(
                input_tokens=in_tok,
                output_tokens=out_tok,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=estimated_cost,
            ),
            notes=(
                f"agree={result['n_agree']}, llm_won={result['n_llm_won']}, "
                f"classical_won={result['n_classical_won_tiebreak']}, "
                f"invalid_llm_high_conf={result['n_fallback_invalid_llm']}"
            ),
        )
        save_result(run_result)
        print("[orch-conf] saved result")
    else:
        print("[orch-conf] WARNING: no ground truth column — skipping scoring")

    print(f"[orch-conf] tokens: {in_tok} in / {out_tok} out | total time: {total_elapsed:.1f}s")

    out_path = (
        Path(__file__).resolve().parents[2]
        / "experiments" / "results"
        / f"orchestrator_confidence_{args.dataset}_trial{args.trial}_annotated.h5ad"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    print(f"[orch-conf] wrote annotated AnnData to {out_path}")


if __name__ == "__main__":
    main()
