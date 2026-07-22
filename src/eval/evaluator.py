"""
evaluator.py

The orchestrator's evaluator: a PROGRAMMATIC agreement check (no LLM call
needed when specialists already agree), plus a constrained-choice
arbitration prompt for genuine disagreements — the LLM picks between
exactly the two specialists' answers, rather than re-doing the full
10-way classification. This is deliberately narrower than Baseline 3's
self-loop, which asked the model to freely re-diagnose everything; a
constrained 2-way choice should be far easier to comply with.

Design decision (see conversation): on unresolved disagreement (arbitration
response doesn't exactly match either offered option), fall back to the
classical specialist's label. This is the simplest option — flagged as an
ablation to revisit later (confidence-weighted tie-break instead), not
treated as final.
"""

from __future__ import annotations

import json


def find_disagreements(
    classical_labels: dict[str, str],
    llm_labels_normalized: dict[str, str],
) -> dict[str, tuple[str, str]]:
    """
    Returns {cluster_id: (classical_label, llm_label)} for clusters where
    the two specialists disagree after the LLM label has already been
    semantically normalized (score.py's normalize_label). Classical labels
    are always valid by construction (PBMC_MARKERS keys == CANDIDATE_LABELS),
    so no normalization needed on that side.
    """
    disagreements = {}
    for cid, classical_label in classical_labels.items():
        llm_label = llm_labels_normalized.get(cid, "PARSE_ERROR")
        if llm_label != classical_label:
            disagreements[cid] = (classical_label, llm_label)
    return disagreements


def build_arbitration_prompt(
    disagreements: dict[str, tuple[str, str]],
    cluster_markers: dict[str, list[str]],
) -> str:
    blocks = []
    for cid, (classical_label, llm_label) in disagreements.items():
        genes = ", ".join(cluster_markers.get(cid, []))
        blocks.append(
            f'Cluster {cid} (marker genes: {genes}):\n'
            f'  Option A: "{classical_label}"\n'
            f'  Option B: "{llm_label}"'
        )
    blocks_text = "\n\n".join(blocks)

    return f"""Two independent methods disagree on the cell type for these
single-cell RNA-seq clusters. For each cluster, pick whichever option is
better supported by the marker genes shown.

{blocks_text}

Respond with ONLY a JSON object mapping cluster id to your chosen label.
Your answer for each cluster MUST be copied EXACTLY, character-for-
character, from either "Option A" or "Option B" for that cluster — do not
modify, abbreviate, or combine them, and do not propose a third option.

No preamble, no explanation, no markdown code fences — just the raw JSON.
"""


def parse_arbitration_response(
    text: str,
    disagreements: dict[str, tuple[str, str]],
) -> dict[str, str]:
    """
    Parses the arbitration response. For any cluster whose chosen label
    isn't exactly one of the two offered options, falls back to the
    classical specialist's label (see module docstring — this is the
    simple fallback, flagged for a future ablation).
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {}

    result = {}
    fallback_count = 0
    for cid, (classical_label, llm_label) in disagreements.items():
        chosen = parsed.get(cid)
        if chosen in (classical_label, llm_label):
            result[cid] = chosen
        else:
            result[cid] = classical_label  # fallback: classical wins
            fallback_count += 1
    return result, fallback_count


def reconcile(
    classical_labels: dict[str, str],
    llm_labels_normalized: dict[str, str],
    cluster_markers: dict[str, list[str]],
    call_fn,
    model: str,
) -> dict:
    """
    Full evaluator pipeline: check agreement, arbitrate disagreements in
    one batched call, apply fallback for anything still unresolved.

    Returns a dict with: final_labels, n_agree, n_disagree, n_fallback,
    arbitration_input_tokens, arbitration_output_tokens, escalated (bool).
    """
    disagreements = find_disagreements(classical_labels, llm_labels_normalized)
    final_labels = dict(classical_labels)  # start from classical, override agreements/arbitration below
    for cid in classical_labels:
        if cid not in disagreements:
            final_labels[cid] = classical_labels[cid]  # both agreed

    n_agree = len(classical_labels) - len(disagreements)
    arb_input_tokens = 0
    arb_output_tokens = 0
    n_fallback = 0

    if disagreements:
        prompt = build_arbitration_prompt(disagreements, cluster_markers)
        response_text, in_tok, out_tok = call_fn(prompt, model)
        arb_input_tokens += in_tok
        arb_output_tokens += out_tok
        arbitrated, n_fallback = parse_arbitration_response(response_text, disagreements)
        final_labels.update(arbitrated)

    return {
        "final_labels": final_labels,
        "n_agree": n_agree,
        "n_disagree": len(disagreements),
        "n_fallback": n_fallback,
        "arbitration_input_tokens": arb_input_tokens,
        "arbitration_output_tokens": arb_output_tokens,
        "escalated": len(disagreements) > 0,
    }
