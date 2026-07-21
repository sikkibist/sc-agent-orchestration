"""
aggregate_results.py

Prints a clean mean +/- std results table for a condition, aggregating
across all trials/seeds saved via score.py's save_result(). This is what
becomes your paper's main results table row.

Usage:
    python src/eval/aggregate_results.py --condition baseline2_llama3.2-3b
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.eval.score import summarize, RESULTS_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, help="condition name, matches the CSV filename (without .csv)")
    args = parser.parse_args()

    csv_path = Path(RESULTS_DIR) / f"{args.condition}.csv"
    if not csv_path.exists():
        print(f"No results file found at {csv_path}")
        print("Available conditions:")
        for f in Path(RESULTS_DIR).glob("*.csv"):
            print(f"  - {f.stem}")
        return

    summary = summarize(str(csv_path))

    print(f"\n=== {args.condition} — {summary['n_runs']} trial(s) ===\n")
    print(f"{'metric':<20} {'mean':>10} {'std':>10} {'n':>5}")
    print("-" * 47)
    for key, val in summary.items():
        if key == "n_runs":
            continue
        metric_name = key.replace("metric_", "")
        print(f"{metric_name:<20} {val['mean']:>10.4f} {val['std']:>10.4f} {val['n']:>5}")


if __name__ == "__main__":
    main()
