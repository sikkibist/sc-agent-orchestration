"""
run_baseline2_single_llm.py

Baseline 2 (protocol Section 4): a single LLM call annotates all clusters
at once, given their top marker genes. No orchestration, no multi-agent
decomposition, no loop/retry. This isolates "can an LLM do this task at
all" from "does orchestration help" — the gap between Baseline 2 and your
full orchestrated system (condition 4/5) is your core result.

Uses the SAME preprocessing/clustering as Baseline 1 (via data_utils.py),
so any accuracy difference comes only from the annotation method.

Usage (default — fully free, runs locally via Ollama, ~2GB model good for 8GB RAM laptops):
    ollama pull llama3.2:3b
    python src/eval/run_baseline2_single_llm.py --dataset pbmc3k --seed 0

Optional — if you ever want to compare against a paid frontier model for
your Baseline 2 vs. small-model ablation, you can opt into that explicitly:
    export ANTHROPIC_API_KEY=sk-...
    python src/eval/run_baseline2_single_llm.py --provider anthropic --model claude-sonnet-5
"""

from __future__ import annotations

import argparse
import json
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
from src.eval.data_utils import load_dataset, preprocess_and_cluster, get_cluster_marker_genes


# ---------------------------------------------------------------------------
# LLM call abstraction — supports Anthropic, OpenAI, or local Ollama.
# Kept deliberately thin: one function per provider, all returning the same
# (text, input_tokens, output_tokens) shape so scoring code doesn't care
# which backend was used.
# ---------------------------------------------------------------------------

def call_anthropic(prompt: str, model: str) -> tuple[str, int, int]:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.usage.input_tokens, response.usage.output_tokens


def call_openai(prompt: str, model: str) -> tuple[str, int, int]:
    import openai

    client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens


def call_ollama(prompt: str, model: str) -> tuple[str, int, int]:
    import ollama

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    text = response["message"]["content"]
    # Ollama reports eval counts, not identical semantics to token billing,
    # but useful as a proxy for compute cost comparisons.
    input_tokens = response.get("prompt_eval_count", 0)
    output_tokens = response.get("eval_count", 0)
    return text, input_tokens, output_tokens


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "ollama": call_ollama,
}


# ---------------------------------------------------------------------------
# Prompt construction + response parsing
# ---------------------------------------------------------------------------

CANDIDATE_LABELS = [
    "CD4 T cell", "CD8 T cell", "B cell", "NK cell",
    "CD14+ Monocyte", "FCGR3A+ Monocyte", "Dendritic cell", "Platelet",
]


def build_prompt(cluster_markers: dict[str, list[str]]) -> str:
    clusters_block = "\n".join(
        f"Cluster {cid}: top marker genes = {', '.join(genes)}"
        for cid, genes in cluster_markers.items()
    )
    return f"""You are annotating clusters from a PBMC (peripheral blood mononuclear
cell) single-cell RNA-seq experiment. For each cluster below, you are given its
top differentially-expressed marker genes. Assign the single most likely cell
type to each cluster.

Candidate cell types — you MUST use one of these EXACT strings for every
cluster, character-for-character, including the "CD4"/"CD14+" etc. prefixes.
Do not invent new labels, abbreviate, or paraphrase them, even if a shorter
name feels more natural:
{chr(10).join(f'- "{label}"' for label in CANDIDATE_LABELS)}

Clusters:
{clusters_block}

Respond with ONLY a JSON object mapping cluster id (as given above, e.g. "0")
to your predicted cell type label, using the EXACT strings from the list
above. No preamble, no explanation, no markdown code fences — just the raw
JSON object.

Example format: {{"0": "CD4 T cell", "1": "B cell"}}
"""


def parse_response(text: str, expected_clusters: list[str]) -> dict[str, str]:
    """Robust-ish JSON parsing: strips markdown fences if the model added
    them despite instructions, and validates all expected clusters got a
    label (fills 'PARSE_ERROR' for any that are missing, rather than
    crashing — a missing/malformed response is itself a data point about
    single-LLM reliability, not something to silently hide)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[baseline2] WARNING: failed to parse LLM response as JSON: {e}")
        print(f"[baseline2] raw response was:\n{text}")
        parsed = {}

    result = {}
    for cid in expected_clusters:
        label = parsed.get(cid, "PARSE_ERROR")
        if label not in CANDIDATE_LABELS and label != "PARSE_ERROR":
            print(
                f"[baseline2] WARNING: cluster {cid} got off-list label "
                f"'{label}' — not in CANDIDATE_LABELS, this WILL silently "
                f"break exact-match scoring (see accuracy-vs-ARI mismatch "
                f"issue). Consider tightening the prompt further or adding "
                f"a normalization step."
            )
        result[cid] = label
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="pbmc3k")
    parser.add_argument("--data-path", default=None)
    parser.add_argument("--seed", type=int, default=0, help="clustering seed — keep fixed at 0 across trials if using the PBMC3k REFERENCE_LABELS sanity-check mapping, which is tied to seed=0's specific clustering")
    parser.add_argument("--trial", type=int, default=0, help="repeat index for this run, distinct from --seed; use this to get multiple LLM samples against IDENTICAL clusters")
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="ollama")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument(
        "--input-price", type=float, default=None,
        help="$ per million input tokens, for cost logging — check current pricing, don't assume",
    )
    parser.add_argument(
        "--output-price", type=float, default=None,
        help="$ per million output tokens, for cost logging",
    )
    args = parser.parse_args()

    np.random.seed(args.seed)
    t0 = time.time()

    print(f"[baseline2] loading dataset={args.dataset} seed={args.seed}")
    adata = load_dataset(args.dataset, args.data_path)

    print(f"[baseline2] preprocessing + clustering ({adata.n_obs} cells)")
    adata = preprocess_and_cluster(adata, seed=args.seed)
    n_clusters = adata.obs["leiden"].nunique()
    print(f"[baseline2] found {n_clusters} clusters")

    print("[baseline2] extracting top marker genes per cluster")
    cluster_markers = get_cluster_marker_genes(adata, n_genes=10)
    for cid, genes in cluster_markers.items():
        print(f"    cluster {cid}: {genes}")

    prompt = build_prompt(cluster_markers)
    print(f"[baseline2] calling {args.provider}/{args.model} (single call, no loop)")

    call_fn = PROVIDERS[args.provider]
    llm_t0 = time.time()
    response_text, input_tokens, output_tokens = call_fn(prompt, args.model)
    llm_elapsed = time.time() - llm_t0

    print(f"[baseline2] raw response:\n{response_text}\n")

    cluster_to_label = parse_response(response_text, list(cluster_markers.keys()))
    for cid, label in cluster_to_label.items():
        n_cells = (adata.obs["leiden"] == cid).sum()
        print(f"    cluster {cid} ({n_cells} cells) -> {label}")

    adata.obs["predicted_cell_type"] = adata.obs["leiden"].map(cluster_to_label)

    total_elapsed = time.time() - t0
    n_parse_errors = sum(1 for v in cluster_to_label.values() if v == "PARSE_ERROR")

    estimated_cost = None
    if args.input_price is not None and args.output_price is not None:
        estimated_cost = (
            input_tokens / 1_000_000 * args.input_price
            + output_tokens / 1_000_000 * args.output_price
        )

    if "ground_truth_cell_type" in adata.obs.columns:
        y_true = adata.obs["ground_truth_cell_type"].astype(str).tolist()
        y_pred = adata.obs["predicted_cell_type"].astype(str).tolist()

        metrics = compute_task_metrics(y_true, y_pred)
        per_class = compute_per_class_f1(y_true, y_pred)
        print("[baseline2] task metrics:", metrics)
        print("[baseline2] per-class F1:", per_class)

        result = RunResult(
            condition=f"baseline2_single_llm_{args.provider}_{args.model}",
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics,
            orchestration_log=OrchestrationLog(
                iterations_used=1, max_iterations=1, converged=(n_parse_errors == 0)
            ),
            cost_log=CostLog(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=estimated_cost,
            ),
            notes=f"single LLM call, no orchestration, {n_parse_errors} parse errors",
        )
        path = save_result(result)
        print(f"[baseline2] saved result to {path}")
    else:
        print(
            "[baseline2] WARNING: no 'ground_truth_cell_type' column found — "
            "skipping scoring. Expected for raw PBMC3k; use GenoTEX for real metrics."
        )

    print(
        f"[baseline2] tokens: {input_tokens} in / {output_tokens} out | "
        f"LLM call time: {llm_elapsed:.1f}s | total time: {total_elapsed:.1f}s | "
        f"parse errors: {n_parse_errors}/{n_clusters}"
    )

    out_path = (
        Path(__file__).resolve().parents[2]
        / "experiments" / "results"
        / f"baseline2_{args.dataset}_trial{args.trial}_annotated.h5ad"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out_path)
    print(f"[baseline2] wrote annotated AnnData to {out_path}")


if __name__ == "__main__":
    main()
