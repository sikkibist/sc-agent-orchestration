# Orchestrated Multi-Agent LLM System for scRNA-seq Cell-Type Annotation

Research project studying whether an orchestrator + specialist-agent architecture
lets small open-weight LLMs match closed frontier-model performance on
single-cell RNA-seq cell-type annotation, and how loop/orchestration design
affects accuracy, cost, and failure modes.

See [`docs/evaluation_protocol_v1.md`](docs/evaluation_protocol_v1.md) for the
full evaluation protocol, metrics, and experimental design — written and
committed **before** running experiments.

## Status
🚧 Early development — baselines not yet implemented.

## Repo structure

```
src/
  agents/
    orchestrator.py       # planner/dispatcher/loop controller
    evaluator.py           # critic agent, accept/reject + re-plan signal
    specialists/
      clustering_agent.py
      annotation_agent.py
      qc_agent.py           # phase 2 / optional
  eval/
    score.py                # scoring script — F1, ARI, NMI, cost, iterations
    run_baseline1_classical.py
    run_baseline2_single_llm.py
    run_condition_orchestrated.py
data/
  README.md                # dataset download instructions (no raw data committed)
docs/
  evaluation_protocol_v1.md
experiments/
  configs/                 # one YAML per run condition/seed
  results/                 # raw output logs, NOT committed if large — see .gitignore
```

## Datasets
- GenoTEX benchmark (arXiv:2406.15341) — primary
- PBMC3k (10x Genomics) — sanity-check dataset
See `data/README.md` for download instructions. No raw data is committed to this repo.

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## License
MIT — see LICENSE.

## Citation
See `CITATION.cff` (to be finalized before submission/release).
