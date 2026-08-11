# Paper Outline v1

**Working title:** When Does Orchestration Help? An Empirical Study of
LLM Agent Architectures for Single-Cell RNA-seq Cell-Type Annotation on
Free, Local Models

---

## Abstract (~200 words)
- Motivation: agentic AI in bioinformatics mostly evaluated with frontier
  models; open question whether orchestration helps small, free/local
  models on a real task
- Task: scRNA-seq cell-type annotation, real FACS ground truth
  (pbmc68k_reduced)
- Method: 5 conditions — classical marker-scoring baseline, single LLM,
  single LLM + self-loop, orchestrator (specialist reconciliation via
  arbitration), orchestrator (confidence-weighted tie-break), tested
  across 3 small open-weight models (llama3.2:3b, llama3.2:1b,
  qwen2.5:1.5b), fully reproducible on an 8GB-RAM laptop
- Key findings (3 bullets): (1) naive LLM annotation badly underperforms
  a free classical method; format-compliance, not biology, is the
  dominant failure; (2) orchestration closes most of the gap but doesn't
  robustly beat the classical baseline; (3) two real implementation bugs
  were found empirically (label-vocabulary mismatch, evaluator accepting
  invalid arbitration picks) — both are general lessons for LLM-agent
  evaluation, not just this task
- One-line takeaway: mechanism design (how disagreements get resolved)
  matters more than model size or agent count

## 1. Introduction
- Rise of agentic AI in bioinformatics (cite survey papers found early
  in this project: Nature Biotechnology 2026 survey, Briefings in
  Bioinformatics surveys, Biomni/CellAgent/BioMaster as example systems)
- Gap: most published agent systems assume frontier-model API access;
  little empirical work on whether orchestration helps when the
  underlying model is small/free
- Research questions (from evaluation_protocol_v1.md): RQ1 (efficiency),
  RQ3 (loop/mechanism behavior)
- Contributions list (bullet points, 4-5 items)

## 2. Related Work
- LLM agents for bioinformatics: CellAgent, BioMaster, Biomni, GenoTEX
  (paraphrase only, cite generically — no verbatim text)
- Multi-agent orchestration patterns generally (planner-executor-evaluator)
- Note explicitly: GenoTEX was initially considered as an evaluation
  dataset but excluded — its task (bulk gene-trait association) doesn't
  match single-cell annotation; mention briefly as a related-but-distinct
  benchmark, not a citation error to dwell on
- Position this paper: first (to our knowledge) systematic small-model,
  free-inference comparison across baseline/self-loop/orchestrator
  designs on a real cell-type annotation task

## 3. Task, Data, and Ground Truth
- Task definition: cluster-level cell-type annotation from top marker
  genes
- Dataset: pbmc68k_reduced (Zheng et al. 2017, bundled with Scanpy),
  genuine FACS-sorted ground truth, 10 real cell types, 700 cells
- Note on PBMC3k: used only for pipeline development/sanity-checking,
  never for reported results (no ground truth available)
- Preprocessing/clustering pipeline (shared across all conditions —
  important for fair comparison)

## 4. Methods
### 4.1 Conditions
- Baseline 1: classical marker-gene scoring (deterministic, free)
- Baseline 2: single LLM call, no orchestration
- Baseline 3: single LLM + self-correction loop (max 3 iterations)
- Orchestrator (arbitration): classical + LLM specialists, programmatic
  agreement check, constrained 2-choice arbitration for disagreements,
  fallback to classical
- Orchestrator (confidence tie-break): same specialists, disagreements
  resolved via confidence comparison instead of a second LLM call
### 4.2 Evaluator design and the validity-gate lesson
- Describe the bug found (arbitration accepting off-list echoed labels)
  and the fix, as a methods contribution, not just a bug fix — general
  principle: fallback/safety logic must validate against ground-truth
  structure, not just internal consistency
### 4.3 Metrics
- Accuracy, macro-F1, ARI, NMI; strict vs. semantically-normalized
  scoring; orchestration-specific metrics (iterations, escalation,
  fallback rate)
### 4.4 Models and infrastructure
- llama3.2:3b, llama3.2:1b, qwen2.5:1.5b via Ollama, fully local, no
  API cost; 8GB RAM consumer laptop; reproducibility statement

## 5. Results
- Main table (all conditions x all models, from results_log.md)
- Per-class F1 breakdown discussion (easy: B cell, NK; hard: T-cell
  subtypes)
- Model-size sweep finding, with the llama3.2:1b degenerate-fallback
  caveat explained clearly (critical to not overclaim here)
- Confidence tie-break: best single trial (0.636) + calibration finding
  (classical margin well-calibrated, LLM self-reported confidence isn't)
- Cost/efficiency comparison (tokens, wall-clock) across conditions

## 6. Discussion
- Why orchestration doesn't clearly beat classical here: two decomposed,
  mechanistically distinct reasons (format non-compliance in Baseline 2/3;
  miscalibrated confidence in the tie-break ablation) — not a single
  cause
- What generalizes beyond this task: validity-gating fallback logic;
  distrust of self-reported LLM confidence without external calibration
- When orchestration would likely help more: harder tasks where the
  classical baseline has no strong prior, or larger/more diverse label
  spaces

## 7. Limitations
- Single dataset, single tissue type, 700 cells (small)
- No frontier-model comparison (resource constraint, stated as a
  deliberate scope choice, not an oversight)
- Single clustering seed for the "real" ground-truth results (multiple
  LLM-sampling trials, but clustering itself not multi-seeded on this
  dataset)
- Classical marker dictionary is hand-curated, not learned

## 8. Conclusion
- Restate 3 key findings
- One-sentence call to action for future work (confidence calibration,
  larger datasets, frontier-model comparison if resources allow)

## Reproducibility Statement
- Link to GitHub repo, note MIT license, note all experiments runnable
  for $0 on consumer hardware

## References
- To be compiled from search results already gathered in this
  conversation (survey papers, CellAgent, BioMaster, Biomni, GenoTEX,
  Zheng et al. 2017 for the dataset)
