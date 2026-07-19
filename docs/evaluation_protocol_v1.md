# Evaluation Protocol v1
## Orchestrated Multi-Agent LLM System for scRNA-seq Cell-Type Annotation

---

## 1. Research Questions

- **RQ1 (Efficiency):** Does an orchestrator + specialist-agent architecture allow small open-weight models (e.g., Llama 3 8B, Qwen 2.5 7B) to match the cell-type annotation accuracy of a single strong closed model (e.g., GPT-4-class, Claude-class), when both are given the same tools and data?
- **RQ2 (Value of orchestration):** How much of the performance gain comes from orchestration/looping itself, versus just the underlying model's raw capability? (i.e., orchestration ablation)
- **RQ3 (Loop behavior):** How does accuracy change as a function of loop iterations, and where is the point of diminishing/negative returns (agents "overthinking" and degrading a correct answer)?
- **RQ4 (Cost-performance tradeoff):** What is the accuracy achieved per unit of cost (API tokens/$, wall-clock time) across configurations?

Pick 2 of these as your primary focus for a first paper — I'd suggest **RQ1 + RQ3** as the core story, with RQ2 and RQ4 as supporting ablations.

---

## 2. Task Definition

**Primary task: Cell-type annotation from scRNA-seq clustering output.**

Given:
- A pre-processed gene expression matrix (or pre-computed clusters with top marker genes per cluster)

The system must output:
- A predicted cell-type label per cluster (or per cell, depending on dataset granularity)

This is the recommended starting scope (not the full QC→clustering→annotation pipeline) because:
- It has clean, objective ground truth (published cell-type labels)
- It isolates the LLM-reasoning-heavy step, which is where orchestration should matter most
- It avoids compounding errors from earlier pipeline stages, keeping evaluation clean

**Optional extension (Phase 2, only if time allows):** Full pipeline including QC and clustering, with cascading-error analysis.

---

## 3. Datasets

| Dataset | Purpose | Notes |
|---|---|---|
| **GenoTEX benchmark** (arXiv:2406.15341) | Primary — use their exact task splits and gold labels so results are directly comparable to prior agent papers | Use as-is, do not modify splits |
| **PBMC3k / PBMC68k** (10x Genomics standard) | Secondary — widely-used, well-characterized reference with known cell types | Good for sanity-checking pipeline before full runs |
| **A Tabula Sapiens subset** (optional, if time allows) | Tests generalization to a broader/harder tissue diversity than PBMC | Only if RQ scope expands |

**Rule:** Never hand-label your own ground truth. Use only datasets with existing, published, expert-verified cell-type annotations. This keeps your evaluation objective and reviewer-defensible.

---

## 4. Systems / Conditions to Compare

| Condition | Description |
|---|---|
| **Baseline 1 — No LLM** | Standard non-agentic pipeline (Scanpy + marker-gene reference lookup, e.g., CellTypist) — the "classical bioinformatics" floor |
| **Baseline 2 — Single LLM, no orchestration** | One LLM call given clusters + marker genes, asked to annotate directly, no loop, no specialist decomposition |
| **Baseline 3 — Single LLM + self-loop (no specialists)** | Same LLM, but allowed to iterate/self-critique in a loop, no multi-agent decomposition — isolates the effect of looping alone |
| **Your System — Orchestrator + Specialists + Evaluator loop** | Full proposed architecture |
| **Your System — small model variant** | Same architecture, swap in Llama 3 8B / Qwen 2.5 instead of GPT-4/Claude-class model |

Running all five conditions on the same dataset is what lets you answer RQ1–RQ3 cleanly. This is your core results table.

---

## 5. Metrics

### 5.1 Task performance (primary)
- **Macro-F1** across cell types (handles class imbalance, which is common — some cell types are rare)
- **Accuracy** (overall, for interpretability alongside F1)
- **Adjusted Rand Index (ARI)** and **Normalized Mutual Information (NMI)** — standard clustering-agreement metrics if you evaluate at the clustering stage too
- Report **per-cell-type breakdown**, not just aggregate — rare cell types are usually where systems fail, and this is where the interesting failure analysis lives

### 5.2 Orchestration-specific metrics (this is what makes the paper novel, not just "another agent")
- **Iterations-to-convergence**: mean/median number of loop cycles before the evaluator agent accepts the output
- **Escalation rate**: % of cases where the small model needed to escalate to a stronger model (if you build that mechanism) or simply failed after max iterations
- **Loop accuracy curve**: accuracy as a function of iteration number (plot this — it's your evidence for RQ3, showing where returns diminish or reverse)
- **Unresolved/failure rate**: % of cases where the loop hit max iterations without evaluator acceptance

### 5.3 Cost / efficiency metrics
- **Total tokens consumed** per task (input + output, summed across all agent calls in the loop)
- **Estimated $ cost** per task, using current published API pricing at time of writing
- **Wall-clock time** per task
- **Accuracy-per-dollar** and **accuracy-per-1000-tokens** — plot as a Pareto frontier across your five conditions; this chart alone is often the single most compelling figure in resource-efficiency papers

### 5.4 Robustness (LLMs are stochastic — this matters for reviewers)
- Run every condition **n ≥ 5 times** with different random seeds/temperature
- Report **mean ± standard deviation**, not single-run numbers
- Where possible, run a significance test (e.g., paired t-test or Wilcoxon signed-rank across matched examples) when claiming System > Baseline

### 5.5 Qualitative failure analysis (cheap to do, high value for the paper)
- Manually inspect a sample (e.g., 30–50) of failure cases
- Build a small **failure taxonomy**, e.g.:
  - Wrong marker-gene interpretation
  - Confusion between closely related cell subtypes
  - Evaluator agent accepting an incorrect answer (false negative in the loop)
  - Evaluator agent rejecting a correct answer, causing wasted iterations (false positive rejection)
  - Orchestrator mis-routing the task to the wrong specialist
- Report frequency of each failure type per condition — this section is often what reviewers cite as most interesting, because it explains *why* the numbers look the way they do, not just *what* the numbers are

---

## 6. Ablations (secondary experiments once the core system works)

1. **Team size ablation**: 1 agent vs. 3 specialists vs. 5 specialists — does more decomposition help or just add cost?
2. **Loop budget ablation**: max 1 / 3 / 5 / 10 iterations — where's the elbow in the accuracy curve?
3. **Evaluator strictness ablation**: vary the evaluator's acceptance threshold — tests sensitivity of the whole system to this one design choice
4. **Model-swap ablation**: same architecture, different backbone models — isolates architecture's contribution from raw model capability (this is your RQ2 answer)

---

## 7. Reporting Template (what your results section should contain)

1. **Main results table** — all 5 conditions × all task-performance metrics (Section 5.1), mean ± std over 5 runs
2. **Cost-performance Pareto plot** — accuracy vs. $ cost, one point per condition
3. **Loop-iteration accuracy curve** — accuracy vs. iteration number, for your full system
4. **Ablation table** — team size / loop budget / evaluator strictness results
5. **Failure taxonomy table** — failure type × frequency × condition
6. **2–3 qualitative examples** — actual transcripts of an interesting success and an interesting failure, annotated

---

## 8. Practical notes

- **Start with Baseline 1 and 2 first** — get your data pipeline and evaluation scoring working on the simplest possible systems before building the orchestrator. This de-risks the project: if your eval pipeline is broken, better to find out early.
- **Fix your evaluation script before running any experiments seriously** — write the scoring code once, test it on hand-checked examples, then never touch it again. Changing metrics mid-way invalidates comparisons.
- **Log everything** — every agent call, every loop decision, every token count — from day one. You'll need this for both the quantitative tables and the qualitative failure analysis, and it's much harder to reconstruct retroactively.
- **Keep a fixed random seed set** (e.g., same 5 seeds) across all conditions so comparisons are as fair as possible.

---

*Next steps: (1) confirm dataset access and do a dry run of Baseline 1 on GenoTEX, (2) write the evaluation scoring script, (3) then start building the orchestrator architecture from the previous sketch.*
