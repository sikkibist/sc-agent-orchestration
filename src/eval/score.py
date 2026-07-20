"""
score.py

Central scoring module for all experimental conditions (Baseline 1, Baseline 2,
Baseline 3, Orchestrated system, small-model variant).

Every run script should produce a `RunResult` and call `save_result()`.
`summarize()` aggregates multiple seeded runs into the mean +/- std table
used in the paper's main results table.

Write this once, test it on hand-checked examples, then don't touch the
scoring logic again mid-experiment (see evaluation_protocol_v1.md, Section 8).
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Optional

from sklearn.metrics import (
    f1_score,
    accuracy_score,
    adjusted_rand_score,
    normalized_mutual_info_score,
)


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def compute_task_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    """
    Task-performance metrics (protocol Section 5.1).

    y_true / y_pred: parallel lists of cell-type labels (one per cell or
    per cluster, depending on your granularity — be consistent across
    conditions so comparisons are fair).
    """
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"Label length mismatch: {len(y_true)} true vs {len(y_pred)} pred"
        )

    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "ari": adjusted_rand_score(y_true, y_pred),
        "nmi": normalized_mutual_info_score(y_true, y_pred),
    }


def compute_per_class_f1(y_true: list[str], y_pred: list[str]) -> dict:
    """
    Per-cell-type F1 breakdown (protocol Section 5.1). This is what surfaces
    rare-cell-type failures that macro-F1 alone can hide.
    """
    labels = sorted(set(y_true) | set(y_pred))
    scores = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    return dict(zip(labels, scores.tolist()))


# ---------------------------------------------------------------------------
# Orchestration-specific metrics (protocol Section 5.2) — fill these in from
# your orchestrator's logs. For Baseline 1/2 these are trivially 0/1/None.
# ---------------------------------------------------------------------------

@dataclass
class OrchestrationLog:
    iterations_used: int = 0          # loop cycles before evaluator accepted
    max_iterations: int = 1           # loop budget for this run
    escalated: bool = False           # did it need to escalate to a stronger model
    converged: bool = True            # False if it hit max_iterations without acceptance
    per_iteration_correct: list[bool] = field(default_factory=list)
    # ^ optional: track whether the answer was correct after each iteration,
    # to plot the loop-accuracy curve (protocol Section 5.3)


# ---------------------------------------------------------------------------
# Cost metrics (protocol Section 5.3)
# ---------------------------------------------------------------------------

@dataclass
class CostLog:
    input_tokens: int = 0
    output_tokens: int = 0
    wall_clock_seconds: float = 0.0
    # Fill in current per-1M-token pricing for whatever model you used at
    # experiment time — pricing changes, so don't hardcode a stale constant
    # here; pass it in explicitly per run.
    estimated_cost_usd: Optional[float] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    input_price_per_million: float,
    output_price_per_million: float,
) -> float:
    """Compute $ cost given current published API pricing (pass explicitly —
    do not hardcode, prices change)."""
    return (
        input_tokens / 1_000_000 * input_price_per_million
        + output_tokens / 1_000_000 * output_price_per_million
    )


# ---------------------------------------------------------------------------
# Unified run result
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    condition: str            # e.g. "baseline1_classical", "orchestrated_gpt4"
    dataset: str               # e.g. "pbmc3k", "genotex"
    seed: int
    task_metrics: dict
    orchestration_log: OrchestrationLog = field(default_factory=OrchestrationLog)
    cost_log: CostLog = field(default_factory=CostLog)
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: str = ""

    def to_flat_dict(self) -> dict:
        """Flatten nested fields for CSV writing."""
        flat = {
            "condition": self.condition,
            "dataset": self.dataset,
            "seed": self.seed,
            "timestamp_utc": self.timestamp_utc,
            "notes": self.notes,
        }
        flat.update({f"metric_{k}": v for k, v in self.task_metrics.items()})
        flat.update(
            {
                "orch_iterations_used": self.orchestration_log.iterations_used,
                "orch_max_iterations": self.orchestration_log.max_iterations,
                "orch_escalated": self.orchestration_log.escalated,
                "orch_converged": self.orchestration_log.converged,
                "cost_input_tokens": self.cost_log.input_tokens,
                "cost_output_tokens": self.cost_log.output_tokens,
                "cost_total_tokens": self.cost_log.total_tokens,
                "cost_wall_clock_seconds": self.cost_log.wall_clock_seconds,
                "cost_estimated_usd": self.cost_log.estimated_cost_usd,
            }
        )
        return flat


# ---------------------------------------------------------------------------
# Saving / loading results
# ---------------------------------------------------------------------------

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "experiments",
    "results",
)


def save_result(result: RunResult, results_dir: str = RESULTS_DIR) -> str:
    """Append one run's result to a per-condition CSV file."""
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, f"{result.condition}.csv")
    flat = result.to_flat_dict()

    file_exists = os.path.isfile(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(flat)

    # Also keep a full JSON record (per-class F1, per-iteration logs, etc.)
    # since CSV can't hold nested structures cleanly.
    json_path = os.path.join(
        results_dir, f"{result.condition}_seed{result.seed}_{int(datetime.now().timestamp())}.json"
    )
    with open(json_path, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)

    return path


def summarize(condition_csv_path: str) -> dict:
    """
    Aggregate multiple seeded runs (protocol Section 5.4): mean +/- std
    across runs for each metric column. This is what goes in the paper's
    main results table.
    """
    rows = []
    with open(condition_csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"No rows found in {condition_csv_path}")

    metric_cols = [c for c in rows[0].keys() if c.startswith("metric_")]
    summary = {"n_runs": len(rows)}
    for col in metric_cols:
        vals = [float(r[col]) for r in rows if r[col] not in ("", None)]
        if not vals:
            continue
        summary[col] = {
            "mean": mean(vals),
            "std": stdev(vals) if len(vals) > 1 else 0.0,
            "n": len(vals),
        }
    return summary


if __name__ == "__main__":
    # quick smoke test — run this file directly to sanity-check the metrics
    # before trusting it in a real experiment
    y_true = ["T cell", "T cell", "B cell", "NK cell", "B cell"]
    y_pred = ["T cell", "B cell", "B cell", "NK cell", "B cell"]

    metrics = compute_task_metrics(y_true, y_pred)
    print("Task metrics:", metrics)
    print("Per-class F1:", compute_per_class_f1(y_true, y_pred))

    result = RunResult(
        condition="smoke_test",
        dataset="dummy",
        seed=0,
        task_metrics=metrics,
        notes="sanity check run, not a real experiment",
    )
    path = save_result(result)
    print(f"Saved smoke-test result to {path}")
    print("Summary:", summarize(path))
