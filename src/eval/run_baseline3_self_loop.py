"""
run_baseline3_self_loop.py

Baseline 3 (protocol Section 4): same single LLM as Baseline 2, but now
given a self-check pass — it reviews its own output against the exact
candidate-label list and corrects any off-list labels, looping up to
--max-iterations times. Still ONE model, no specialist decomposition, no
separate evaluator agent — this isolates "does looping alone help" from
"does multi-agent decomposition help" (that's what the full orchestrator,
condition 4/5, adds on top of this).

Reuses Baseline 2's provider abstraction, prompt builder, and candidate
label list so the two conditions are directly comparable.

Usage (default — free, local Ollama):
    python src/eval/run_baseline3_self_loop.py --seed 0 --trial 0 --max-iterations 3
"""

from __future__ import annotations

import argparse
import json
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
from src.eval.run_baseline2_single_llm import (
    PROVIDERS,
    CANDIDATE_LABELS,
    build_prompt,
    parse_response,
)


def build_self_check_prompt(cluster_to_label: dict[str, str]) -> str:
    current_answer = json.dumps(cluster_to_label, indent=2)
    return f"""You previously annotated single-cell RNA-seq clusters with this
JSON mapping of cluster id to cell type label:

{current_answer}

The ONLY valid labels are these exact strings:
{chr(10).join(f'- "{label}"' for label in CANDIDATE_LABELS)}

Check every value in your mapping above. For any cluster whose label is
NOT character-for-character identical to one of the valid strings, replace
it with the closest matching valid label. If a label is already exactly
correct, leave it unchanged.

Respond with ONLY the corrected JSON object, same keys, same format as
above. No preamble, no explanation, no markdown code fences. If every
label was already valid, respond with exactly: ALL_VALID
"""


def is_valid_mapping(cluster_to_label: dict[str, str]) -> bool:
    return all(label in CANDIDATE_LABELS for label in cluster_to_label.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="pbmc68k_reduced")
    parser.add_argument("--data-path", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trial", type=int, default=0)
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="ollama")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--input-price", type=float, default=None)
    parser.add_argument("--output-price", type=float, default=None)
    args = parser.parse_args()

    np.random.seed(args.seed)
    t0 = time.time()

    print(f"[baseline3] loading dataset={args.dataset} seed={args.seed}")
    adata = load_dataset(args.dataset, args.data_path)

    print(f"[baseline3] preprocessing + clustering ({adata.n_obs} cells)")
    adata = preprocess_and_cluster(adata, seed=args.seed, already_normalized=(args.dataset == "pbmc68k_reduced"))
    n_clusters = adata.obs["leiden"].nunique()
    print(f"[baseline3] found {n_clusters} clusters")

    cluster_markers = get_cluster_marker_genes(adata, n_genes=10)
    expected_clusters = list(cluster_markers.keys())

    call_fn = PROVIDERS[args.provider]
    total_input_tokens = 0
    total_output_tokens = 0

    y_true = None
    if "ground_truth_cell_type" in adata.obs.columns:
        y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()

    per_iteration_accuracy = []  # research-only diagnostic, not the production stopping criterion

    def score_current(cluster_to_label: dict[str, str]) -> float | None:
        if y_true is None:
            return None
        pred = adata.obs["leiden"].astype(str).map(cluster_to_label).tolist()
        return compute_task_metrics(y_true, pred)["accuracy"]

    # --- Iteration 1: initial annotation, same as Baseline 2 ---
    print(f"[baseline3] iteration 1/{args.max_iterations}: initial annotation")
    prompt = build_prompt(cluster_markers)
    response_text, in_tok, out_tok = call_fn(prompt, args.model)
    total_input_tokens += in_tok
    total_output_tokens += out_tok
    cluster_to_label = parse_response(response_text, expected_clusters)
    print(f"    result: {cluster_to_label}")
    acc = score_current(cluster_to_label)
    per_iteration_accuracy.append(acc)
    if acc is not None:
        print(f"    accuracy so far: {acc:.3f} (diagnostic only, not the loop's stopping signal)")

    iterations_used = 1
    converged = is_valid_mapping(cluster_to_label)

    # --- Self-check loop ---
    while not converged and iterations_used < args.max_iterations:
        iterations_used += 1
        print(f"[baseline3] iteration {iterations_used}/{args.max_iterations}: self-check")
        self_check_prompt = build_self_check_prompt(cluster_to_label)
        response_text, in_tok, out_tok = call_fn(self_check_prompt, args.model)
        total_input_tokens += in_tok
        total_output_tokens += out_tok

        if response_text.strip() == "ALL_VALID":
            print("    model reports all labels already valid")
            converged = is_valid_mapping(cluster_to_label)
        else:
            corrected = parse_response(response_text, expected_clusters)
            # only accept corrections for clusters the model actually returned;
            # if parsing failed entirely, keep the previous mapping rather than
            # overwriting good labels with PARSE_ERROR
            for cid, label in corrected.items():
                if label != "PARSE_ERROR":
                    cluster_to_label[cid] = label
            converged = is_valid_mapping(cluster_to_label)

        print(f"    result: {cluster_to_label}")
        acc = score_current(cluster_to_label)
        per_iteration_accuracy.append(acc)
        if acc is not None:
            print(f"    accuracy so far: {acc:.3f}")

    print(f"[baseline3] loop ended: converged={converged}, iterations_used={iterations_used}")

    adata.obs["predicted_cell_type"] = adata.obs["leiden"].astype(str).map(cluster_to_label)
    total_elapsed = time.time() - t0

    estimated_cost = None
    if args.input_price is not None and args.output_price is not None:
        estimated_cost = (
            total_input_tokens / 1_000_000 * args.input_price
            + total_output_tokens / 1_000_000 * args.output_price
        )

    if y_true is not None:
        y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()
        metrics = compute_task_metrics(y_true, y_pred)
        per_class = compute_per_class_f1(y_true, y_pred)
        print("[baseline3] final task metrics (strict):", metrics)
        print("[baseline3] per-class F1 (strict):", per_class)

        y_pred_normalized = [normalize_label(p, CANDIDATE_LABELS) for p in y_pred]
        metrics_normalized = compute_task_metrics(y_true, y_pred_normalized)
        print("[baseline3] final task metrics (semantically normalized):", metrics_normalized)

        orch_log = OrchestrationLog(
            iterations_used=iterations_used,
            max_iterations=args.max_iterations,
            converged=converged,
            per_iteration_correct=[a is not None and a > 0 for a in per_iteration_accuracy],
        )

        result = RunResult(
            condition=f"baseline3_self_loop_{args.provider}_{args.model}",
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
            notes=f"self-loop, {iterations_used}/{args.max_iterations} iterations, converged={converged}",
        )
        save_result(result)

        result_norm = RunResult(
            condition=f"baseline3_self_loop_{args.provider}_{args.model}_semantic_normalized",
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics_normalized,
            orchestration_log=orch_log,
            cost_log=CostLog(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=estimated_cost,
            ),
            notes=f"self-loop, semantic normalization applied, {iterations_used}/{args.max_iterations} iterations",
        )
        save_result(result_norm)
        print("[baseline3] saved strict and normalized results")
    else:
        print("[baseline3] WARNING: no ground truth column — skipping scoring")

    print(
        f"[baseline3] tokens: {total_input_tokens} in / {total_output_tokens} out (cumulative across {iterations_used} iterations) | "
        f"total time: {total_elapsed:.1f}s"
    )
    print(f"[baseline3] per-iteration accuracy trace: {per_iteration_accuracy}")

    out_path = (
        Path(__file__).resolve().parents[2]
        / "experiments" / "results"
        / f"baseline3_{args.dataset}_trial{args.trial}_annotated.h5ad"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    print(f"[baseline3] wrote annotated AnnData to {out_path}")


if __name__ == "__main__":
    main()
