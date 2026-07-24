# When Does Orchestration Help? Small-Model LLM Agents for scRNA-seq Cell-Type Annotation

Research project studying whether an orchestrator + specialist-agent
architecture helps small, free, locally-run LLMs annotate single-cell
RNA-seq clusters accurately, and how the reconciliation mechanism
(arbitration vs. confidence-weighted tie-break) affects accuracy, cost,
and failure modes — evaluated against real FACS-sorted ground truth.

**Read the paper draft:** [`docs/paper_draft_v1.md`](docs/paper_draft_v1.md)

All experiments run at **zero monetary cost** on a consumer laptop (8GB
RAM, no GPU) using open-weight models served locally via Ollama.

## Status
✅ Core empirical study complete — 5 conditions × 3 models, all results
logged and reproducible. First paper draft written. See
[`docs/results_log.md`](docs/results_log.md) for every number reported in
the paper, and [`docs/evaluation_protocol_v1.md`](docs/evaluation_protocol_v1.md)
for the protocol, written and frozen **before** any results were generated.

## Key findings
- A free, deterministic classical baseline (marker-gene scoring)
  substantially outperforms naive single-LLM annotation — the dominant
  LLM failure mode is output-format non-compliance, not biology.
- Orchestration (specialist reconciliation) closes most of this gap but
  doesn't robustly beat the classical baseline on average.
- Two real implementation bugs were found through empirical testing, both
  generalizable beyond this task: a label-vocabulary mismatch that
  silently corrupts exact-match scoring, and an evaluator that can
  "validly" accept an internally-consistent but wrong answer.
- Best single result (0.636 accuracy, beating the classical baseline)
  comes from a confidence-weighted orchestrator — which also reveals a
  distinct failure mode from miscalibrated LLM self-reported confidence.

## Repo structure

```
src/eval/
  score.py                        # core metrics: F1, ARI, NMI, cost, normalization
  data_utils.py                   # shared dataset loading + clustering (identical across all conditions)
  run_baseline1_classical.py      # Baseline 1: deterministic marker-gene scoring
  run_baseline2_single_llm.py     # Baseline 2: single LLM call, no orchestration
  run_baseline3_self_loop.py      # Baseline 3: single LLM + self-check loop
  evaluator.py                    # orchestrator evaluator: agreement check + arbitration
  run_orchestrator.py             # Orchestrator (arbitration variant)
  confidence_tiebreak.py          # orchestrator evaluator: confidence-weighted tie-break
  run_orchestrator_confidence.py  # Orchestrator (confidence tie-break variant)
  aggregate_results.py            # mean/std summary table across trials
docs/
  evaluation_protocol_v1.md       # protocol, written before results
  results_log.md                  # every result, as it was produced
  paper_outline_v1.md             # paper structure
  paper_draft_v1.md               # full paper draft
data/
  README.md                       # dataset notes (no raw data committed)
experiments/results/              # per-condition CSVs + per-trial JSON logs (small, committed)
```

## Dataset
**`pbmc68k_reduced`** (Zheng et al. 2017, bundled with Scanpy) — genuine
FACS-sorted ground truth, 10 real cell types, 700 cells, no download
needed (`sc.datasets.pbmc68k_reduced()`). This is the only dataset used
for reported results.

PBMC3k (10x Genomics) was used only for early pipeline development — it
has no ground-truth labels and no results from it are reported in the
paper.

*Note: GenoTEX was initially considered but excluded — its task (bulk
gene-trait association) doesn't match single-cell annotation. See the
paper's Related Work section.*

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# free, local model inference — no API key needed
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

## Reproducing the results
```bash
python src/eval/run_baseline1_classical.py --seed 0

for t in 0 1 2 3 4; do
    python src/eval/run_baseline2_single_llm.py --seed 0 --trial $t
    python src/eval/run_baseline3_self_loop.py --seed 0 --trial $t
    python src/eval/run_orchestrator.py --seed 0 --trial $t
    python src/eval/run_orchestrator_confidence.py --seed 0 --trial $t
done

python src/eval/aggregate_results.py --condition <condition_name>
```

## License
MIT — see LICENSE.

## Citation
See `CITATION.cff` (to be finalized before submission/release).
