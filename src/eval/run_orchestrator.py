"""
run_orchestrator.py

The full orchestrated system (protocol condition 4): classical specialist
+ LLM specialist run per-cluster, reconciled by a programmatic evaluator
(evaluator.py). Only genuine disagreements trigger a second, CONSTRAINED
LLM call (pick between exactly two options) — not a full re-diagnosis
like Baseline 3's self-loop.

Reuses Baseline 1's classical annotation logic and Baseline 2's LLM/
provider abstraction directly, so the comparison across all conditions
stays methodologically consistent.

Usage (default — free, local Ollama):
    python src/eval/run_orchestrator.py --seed 0 --trial 0
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
from src.eval.run_baseline1_classical import PBMC_MARKERS, annotate_clusters
from src.eval.run_baseline2_single_llm import (
    PROVIDERS,
    CANDIDATE_LABELS,
    build_prompt,
    parse_response,
)
from src.eval.evaluator import reconcile


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

    print(f"[orchestrator] loading dataset={args.dataset} seed={args.seed}")
    adata = load_dataset(args.dataset, args.data_path)

    print(f"[orchestrator] preprocessing + clustering ({adata.n_obs} cells)")
    adata = preprocess_and_cluster(adata, seed=args.seed, already_normalized=(args.dataset == "pbmc68k_reduced"))
    n_clusters = adata.obs["leiden"].nunique()
    print(f"[orchestrator] found {n_clusters} clusters")

    cluster_markers = get_cluster_marker_genes(adata, n_genes=10)
    expected_clusters = list(cluster_markers.keys())

    call_fn = PROVIDERS[args.provider]
    total_input_tokens = 0
    total_output_tokens = 0

    # --- Classical specialist (deterministic, no LLM call, no tokens) ---
    print("[orchestrator] running classical specialist")
    classical_labels = annotate_clusters(adata, PBMC_MARKERS)
    print(f"    {classical_labels}")

    # --- LLM specialist (one call, same as Baseline 2's initial call) ---
    print("[orchestrator] running LLM specialist")
    prompt = build_prompt(cluster_markers)
    response_text, in_tok, out_tok = call_fn(prompt, args.model)
    total_input_tokens += in_tok
    total_output_tokens += out_tok
    llm_labels_raw = parse_response(response_text, expected_clusters)
    llm_labels_normalized = {
        cid: normalize_label(label, CANDIDATE_LABELS) for cid, label in llm_labels_raw.items()
    }
    print(f"    raw: {llm_labels_raw}")
    print(f"    normalized: {llm_labels_normalized}")

    # --- Evaluator: programmatic agreement check + constrained arbitration ---
    print("[orchestrator] running evaluator")
    eval_result = reconcile(
        classical_labels, llm_labels_normalized, cluster_markers, call_fn, args.model
    )
    total_input_tokens += eval_result["arbitration_input_tokens"]
    total_output_tokens += eval_result["arbitration_output_tokens"]

    print(
        f"[orchestrator] evaluator: {eval_result['n_agree']} agreed, "
        f"{eval_result['n_disagree']} disagreed, "
        f"{eval_result['n_fallback']} fell back to classical after arbitration"
    )
    print(f"    final labels: {eval_result['final_labels']}")

    final_labels = eval_result["final_labels"]
    adata.obs["predicted_cell_type"] = adata.obs["leiden"].astype(str).map(final_labels)
    total_elapsed = time.time() - t0

    iterations_used = 2 if eval_result["escalated"] else 1  # specialists-round + arbitration-round if needed

    estimated_cost = None
    if args.input_price is not None and args.output_price is not None:
        estimated_cost = (
            total_input_tokens / 1_000_000 * args.input_price
            + total_output_tokens / 1_000_000 * args.output_price
        )

    if "ground_truth_cell_type" in adata.obs.columns:
        y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
        y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()
        metrics = compute_task_metrics(y_true, y_pred)
        per_class = compute_per_class_f1(y_true, y_pred)
        print("[orchestrator] final task metrics:", metrics)
        print("[orchestrator] per-class F1:", per_class)

        orch_log = OrchestrationLog(
            iterations_used=iterations_used,
            max_iterations=2,
            converged=(eval_result["n_fallback"] == 0),
            escalated=eval_result["escalated"],
        )

        result = RunResult(
            condition=f"orchestrator_{args.provider}_{args.model}",
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics,
            orchestration_log=orch_log,
            cost_log=CostLog(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=estimated_cost,
            ),
            notes=(
                f"agree={eval_result['n_agree']}, disagree={eval_result['n_disagree']}, "
                f"fallback={eval_result['n_fallback']}"
            ),
        )
        save_result(result)
        print("[orchestrator] saved result")
    else:
        print("[orchestrator] WARNING: no ground truth column — skipping scoring")

    print(
        f"[orchestrator] tokens: {total_input_tokens} in / {total_output_tokens} out | "
        f"total time: {total_elapsed:.1f}s | iterations_used: {iterations_used}"
    )

    out_path = (
        Path(__file__).resolve().parents[2]
        / "experiments" / "results"
        / f"orchestrator_{args.dataset}_trial{args.trial}_annotated.h5ad"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    print(f"[orchestrator] wrote annotated AnnData to {out_path}")


if __name__ == "__main__":
    main()
