"""
run_baseline2_single_llm.py

Baseline 2 (protocol Section 4): a single local LLM call annotates all
clusters at once, given their top marker genes.

No orchestration, no multi-agent decomposition, no loop/retry.

This isolates:
    "Can a small local LLM perform the annotation task?"
from:
    "Does orchestration improve the result?"

The gap between Baseline 2 and the orchestrated conditions is a core
experimental comparison in this project.

The script uses the SAME preprocessing and clustering pipeline as
Baseline 1 via data_utils.py, so differences in accuracy come from
the annotation method rather than different upstream clusters.

LLM inference is performed locally through Ollama.

Supported experimental models:
    - llama3.2:3b
    - llama3.2:1b
    - qwen2.5:1.5b

Example:
    ollama pull llama3.2:3b
    python src/eval/run_baseline2_single_llm.py \
        --dataset pbmc68k_reduced \
        --seed 0 \
        --trial 0 \
        --model llama3.2:3b
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

from src.eval.data_utils import (
    get_cluster_marker_genes,
    load_dataset,
    preprocess_and_cluster,
)
from src.eval.score import (
    CostLog,
    OrchestrationLog,
    RunResult,
    compute_per_class_f1,
    compute_task_metrics,
    normalize_label,
    save_result,
)


# ---------------------------------------------------------------------------
# Ollama LLM call
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, model: str) -> tuple[str, int, int]:
    """
    Run one local Ollama inference call.

    Returns:
        response_text
        input_tokens
        output_tokens
    """
    import ollama

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response["message"]["content"]

    # Ollama reports evaluation counts. These are used as compute/token
    # proxies for experiment logging rather than API billing.
    input_tokens = response.get("prompt_eval_count", 0)
    output_tokens = response.get("eval_count", 0)

    return text, input_tokens, output_tokens


# ---------------------------------------------------------------------------
# Prompt construction + response parsing
# ---------------------------------------------------------------------------

CANDIDATE_LABELS = [
    "CD14+ Monocyte",
    "CD19+ B",
    "CD34+",
    "CD56+ NK",
    "Dendritic",
    "CD4+/CD25 T Reg",
    "CD4+/CD45RA+/CD25- Naive T",
    "CD4+/CD45RO+ Memory",
    "CD8+ Cytotoxic T",
    "CD8+/CD45RA+ Naive Cytotoxic",
]


def build_prompt(cluster_markers: dict[str, list[str]]) -> str:
    """Build the single-shot cell-type annotation prompt."""

    clusters_block = "\n".join(
        f"Cluster {cid}: top marker genes = {', '.join(genes)}"
        for cid, genes in cluster_markers.items()
    )

    return f"""You are annotating clusters from a PBMC (peripheral blood
mononuclear cell) single-cell RNA-seq experiment.

For each cluster below, you are given its top differentially expressed
marker genes. Assign the single most likely cell type to each cluster.

Candidate cell types — you MUST use one of these EXACT strings for every
cluster, character-for-character, including the "CD4"/"CD14+" prefixes.

Do not invent new labels, abbreviate, or paraphrase them.

{chr(10).join(f'- "{label}"' for label in CANDIDATE_LABELS)}

Clusters:
{clusters_block}

Respond with ONLY a JSON object mapping each cluster ID to its predicted
cell-type label.

Use the EXACT strings from the candidate list.

No preamble.
No explanation.
No markdown code fences.
Only the raw JSON object.

Example format:
{{"0": "CD4+/CD45RO+ Memory", "1": "CD19+ B"}}
"""


def parse_response(
    text: str,
    expected_clusters: list[str],
) -> dict[str, str]:
    """
    Parse and validate the LLM JSON response.

    Markdown fences are removed if the model adds them despite the prompt.

    Missing or malformed cluster outputs are recorded as PARSE_ERROR rather
    than silently discarded. This preserves output-format failure as an
    observable property of the single-LLM baseline.
    """

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]

        if cleaned.startswith("json"):
            cleaned = cleaned[4:]

        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)

    except json.JSONDecodeError as error:
        print(
            f"[baseline2] WARNING: failed to parse LLM response as JSON: "
            f"{error}"
        )
        print(f"[baseline2] raw response was:\n{text}")
        parsed = {}

    result: dict[str, str] = {}

    for cluster_id in expected_clusters:
        label = parsed.get(cluster_id, "PARSE_ERROR")

        if label not in CANDIDATE_LABELS and label != "PARSE_ERROR":
            print(
                f"[baseline2] WARNING: cluster {cluster_id} received "
                f"off-list label '{label}'. "
                "This can affect strict exact-match scoring."
            )

        result[cluster_id] = label

    return result


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Baseline 2: single local Ollama LLM call for "
            "scRNA-seq cluster annotation."
        )
    )

    parser.add_argument(
        "--dataset",
        default="pbmc68k_reduced",
    )

    parser.add_argument(
        "--data-path",
        default=None,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help=(
            "Clustering seed. Keep fixed across LLM trials so every "
            "trial uses identical clusters."
        ),
    )

    parser.add_argument(
        "--trial",
        type=int,
        default=0,
        help=(
            "Repeat index for this LLM run. Distinct from --seed; "
            "use this to collect multiple samples from identical clusters."
        ),
    )

    parser.add_argument(
        "--model",
        default="llama3.2:3b",
        help=(
            "Local Ollama model. Experimental models: "
            "llama3.2:3b, llama3.2:1b, qwen2.5:1.5b"
        ),
    )

    args = parser.parse_args()

    np.random.seed(args.seed)

    total_start = time.time()

    # ------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------

    print(
        f"[baseline2] loading dataset={args.dataset} "
        f"seed={args.seed}"
    )

    adata = load_dataset(
        args.dataset,
        args.data_path,
    )

    # ------------------------------------------------------------------
    # Preprocessing + clustering
    # ------------------------------------------------------------------

    print(
        f"[baseline2] preprocessing + clustering "
        f"({adata.n_obs} cells)"
    )

    adata = preprocess_and_cluster(
        adata,
        seed=args.seed,
        already_normalized=(
            args.dataset == "pbmc68k_reduced"
        ),
    )

    n_clusters = adata.obs["leiden"].nunique()

    print(
        f"[baseline2] found {n_clusters} clusters"
    )

    # ------------------------------------------------------------------
    # Marker extraction
    # ------------------------------------------------------------------

    print(
        "[baseline2] extracting top marker genes per cluster"
    )

    cluster_markers = get_cluster_marker_genes(
        adata,
        n_genes=10,
    )

    for cluster_id, genes in cluster_markers.items():
        print(
            f"    cluster {cluster_id}: {genes}"
        )

    # ------------------------------------------------------------------
    # Build prompt
    # ------------------------------------------------------------------

    prompt = build_prompt(cluster_markers)

    print(
        f"[baseline2] calling Ollama/{args.model} "
        "(single call, no orchestration)"
    )

    # ------------------------------------------------------------------
    # LLM inference
    # ------------------------------------------------------------------

    llm_start = time.time()

    response_text, input_tokens, output_tokens = call_ollama(
        prompt,
        args.model,
    )

    llm_elapsed = time.time() - llm_start

    print(
        f"[baseline2] raw response:\n{response_text}\n"
    )

    # ------------------------------------------------------------------
    # Parse response
    # ------------------------------------------------------------------

    cluster_to_label = parse_response(
        response_text,
        list(cluster_markers.keys()),
    )

    for cluster_id, label in cluster_to_label.items():
        n_cells = (
            adata.obs["leiden"] == cluster_id
        ).sum()

        print(
            f"    cluster {cluster_id} "
            f"({n_cells} cells) -> {label}"
        )

    adata.obs["predicted_cell_type"] = (
        adata.obs["leiden"].map(cluster_to_label)
    )

    total_elapsed = time.time() - total_start

    n_parse_errors = sum(
        label == "PARSE_ERROR"
        for label in cluster_to_label.values()
    )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    if "ground_truth_cell_type" in adata.obs.columns:

        y_true = (
            adata.obs["ground_truth_cell_type"]
            .astype(str)
            .tolist()
        )

        y_pred = (
            adata.obs["predicted_cell_type"]
            .astype(str)
            .tolist()
        )

        # Strict exact-match evaluation.
        metrics = compute_task_metrics(
            y_true,
            y_pred,
        )

        per_class = compute_per_class_f1(
            y_true,
            y_pred,
        )

        print(
            "[baseline2] task metrics "
            "(strict, exact-match):",
            metrics,
        )

        print(
            "[baseline2] per-class F1 (strict):",
            per_class,
        )

        # --------------------------------------------------------------
        # Semantic normalization
        # --------------------------------------------------------------
        #
        # This secondary metric separates:
        #
        #   biological interpretation
        #          from
        #   exact output-format compliance.
        #
        # Both strict and normalized metrics should be retained in
        # reporting; normalized scoring must not replace strict scoring.
        # --------------------------------------------------------------

        y_pred_normalized = [
            normalize_label(
                prediction,
                CANDIDATE_LABELS,
            )
            for prediction in y_pred
        ]

        metrics_normalized = compute_task_metrics(
            y_true,
            y_pred_normalized,
        )

        per_class_normalized = compute_per_class_f1(
            y_true,
            y_pred_normalized,
        )

        print(
            "[baseline2] task metrics "
            "(semantically normalized):",
            metrics_normalized,
        )

        print(
            "[baseline2] per-class F1 (normalized):",
            per_class_normalized,
        )

        # --------------------------------------------------------------
        # Save strict result
        # --------------------------------------------------------------

        result = RunResult(
            condition=(
                f"baseline2_single_llm_ollama_{args.model}"
            ),
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics,
            orchestration_log=OrchestrationLog(
                iterations_used=1,
                max_iterations=1,
                converged=(n_parse_errors == 0),
            ),
            cost_log=CostLog(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=0.0,
            ),
            notes=(
                "single local Ollama LLM call, no orchestration, "
                f"{n_parse_errors} parse errors "
                "(strict scoring)"
            ),
        )

        result_path = save_result(result)

        print(
            f"[baseline2] saved strict result to "
            f"{result_path}"
        )

        # --------------------------------------------------------------
        # Save normalized result
        # --------------------------------------------------------------

        result_normalized = RunResult(
            condition=(
                f"baseline2_single_llm_ollama_{args.model}"
                "_semantic_normalized"
            ),
            dataset=args.dataset,
            seed=args.trial,
            task_metrics=metrics_normalized,
            orchestration_log=OrchestrationLog(
                iterations_used=1,
                max_iterations=1,
                converged=(n_parse_errors == 0),
            ),
            cost_log=CostLog(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                wall_clock_seconds=total_elapsed,
                estimated_cost_usd=0.0,
            ),
            notes=(
                "same local Ollama run, scored with semantic "
                f"label normalization; {n_parse_errors} raw parse errors"
            ),
        )

        normalized_path = save_result(
            result_normalized
        )

        print(
            f"[baseline2] saved normalized result to "
            f"{normalized_path}"
        )

    else:

        print(
            "[baseline2] WARNING: no "
            "'ground_truth_cell_type' column found — "
            "skipping scoring."
        )

    # ------------------------------------------------------------------
    # Runtime summary
    # ------------------------------------------------------------------

    print(
        f"[baseline2] tokens: "
        f"{input_tokens} in / "
        f"{output_tokens} out | "
        f"LLM call time: {llm_elapsed:.1f}s | "
        f"total time: {total_elapsed:.1f}s | "
        f"parse errors: "
        f"{n_parse_errors}/{n_clusters}"
    )

    # ------------------------------------------------------------------
    # Save annotated AnnData
    # ------------------------------------------------------------------

    output_path = (
        Path(__file__).resolve().parents[2]
        / "experiments"
        / "results"
        / (
            f"baseline2_{args.dataset}_"
            f"trial{args.trial}_annotated.h5ad"
        )
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    adata.write_h5ad(output_path)

    print(
        f"[baseline2] wrote annotated AnnData to "
        f"{output_path}"
    )


if __name__ == "__main__":
    main()