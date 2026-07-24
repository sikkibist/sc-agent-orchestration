"""
confidence_tiebreak.py

Alternative to evaluator.py's arbitration-based reconciliation (the
deferred ablation from the original orchestrator design discussion).
Instead of a second LLM call to arbitrate disagreements, each specialist
reports a confidence signal in its ORIGINAL call:
  - Classical: the margin between its top and runner-up marker score
    (already computed for free, see run_baseline1_classical.py).
  - LLM: a self-reported 0-100 confidence, requested in the same JSON
    response as its label (no extra call).

On disagreement, whichever specialist has "high" confidence wins; ties or
both-low default to classical (same safety bias as the arbitration
version). Confidence levels are relative, not absolute: classical margins
are bucketed by their own median within this run (no arbitrary constant
threshold), since raw margin scale isn't comparable to a 0-100 LLM score.

CRITICAL lesson carried over from evaluator.py's bug fix: even if the LLM
"wins" the tie-break, its label is NEVER accepted unless it's an exact
match to a real CANDIDATE_LABEL. High self-reported confidence in a
garbage label is still garbage — confidence is not a validity check.
"""

from __future__ import annotations

import json
from statistics import median


def build_confidence_prompt(cluster_markers: dict[str, list[str]], candidate_labels: list[str]) -> str:
    clusters_block = "\n".join(
        f"Cluster {cid}: top marker genes = {', '.join(genes)}"
        for cid, genes in cluster_markers.items()
    )
    return f"""You are annotating clusters from a PBMC single-cell RNA-seq
experiment. For each cluster, assign the most likely cell type AND rate
your confidence in that assignment from 0 (pure guess) to 100 (certain).

Candidate cell types — you MUST use one of these EXACT strings for the
label, character-for-character:
{chr(10).join(f'- "{label}"' for label in candidate_labels)}

Clusters:
{clusters_block}

Respond with ONLY a JSON object mapping cluster id to an object with
"label" and "confidence" keys. No preamble, no explanation, no markdown
code fences — just the raw JSON.

Example format: {{"0": {{"label": "CD4+/CD25 T Reg", "confidence": 72}}}}
"""


def parse_confidence_response(
    text: str, expected_clusters: list[str]
) -> dict[str, tuple[str, float]]:
    """Returns {cluster_id: (label, confidence)}. Malformed entries get
    ("PARSE_ERROR", 0) — zero confidence ensures they never win a tie-break."""
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
    for cid in expected_clusters:
        entry = parsed.get(cid)
        if isinstance(entry, dict) and "label" in entry:
            label = entry["label"]
            try:
                confidence = float(entry.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0
            result[cid] = (label, confidence)
        else:
            result[cid] = ("PARSE_ERROR", 0.0)
    return result


def reconcile_by_confidence(
    classical_results: dict[str, tuple[str, float]],  # {cid: (label, margin)}
    llm_results: dict[str, tuple[str, float]],         # {cid: (label, confidence)}
    candidate_labels: list[str],
) -> dict:
    """
    No LLM call here — pure comparison logic using confidence signals
    already gathered from each specialist's original call.
    """
    classical_margins = [m for _, m in classical_results.values()]
    margin_cutoff = median(classical_margins) if classical_margins else 0.0

    final_labels = {}
    n_agree = 0
    n_llm_won = 0
    n_classical_won_tiebreak = 0
    n_fallback_invalid_llm = 0

    for cid, (classical_label, margin) in classical_results.items():
        llm_label_raw, llm_confidence = llm_results.get(cid, ("PARSE_ERROR", 0.0))
        llm_label_normalized = llm_label_raw  # caller should pass already-normalized labels in

        if llm_label_normalized == classical_label:
            final_labels[cid] = classical_label
            n_agree += 1
            continue

        classical_high = margin >= margin_cutoff
        llm_high = llm_confidence >= 70

        if llm_high and not classical_high and llm_label_normalized in candidate_labels:
            final_labels[cid] = llm_label_normalized
            n_llm_won += 1
        else:
            # classical wins: either it was the confident one, both/neither
            # were confident (tie -> classical default), or the LLM's pick
            # isn't even a real candidate label (confidence is not a
            # validity check — see module docstring)
            final_labels[cid] = classical_label
            n_classical_won_tiebreak += 1
            if llm_high and llm_label_normalized not in candidate_labels:
                n_fallback_invalid_llm += 1

    return {
        "final_labels": final_labels,
        "n_agree": n_agree,
        "n_llm_won": n_llm_won,
        "n_classical_won_tiebreak": n_classical_won_tiebreak,
        "n_fallback_invalid_llm": n_fallback_invalid_llm,
        "margin_cutoff": margin_cutoff,
    }
