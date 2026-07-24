# When Does Orchestration Help? An Empirical Study of LLM Agent Architectures for Single-Cell RNA-seq Cell-Type Annotation on Free, Local Models

## Abstract

Agentic AI systems for bioinformatics are increasingly common, but nearly
all published work evaluates them using frontier-tier models accessed via
paid APIs. It remains unclear whether orchestration — decomposing a task
across specialist components and reconciling their outputs — actually
helps when the underlying language model is small and runs for free on
consumer hardware. We study this question directly on a concrete task:
cell-type annotation from single-cell RNA-seq marker genes, evaluated
against genuine FACS-sorted ground truth. We compare five conditions — a
deterministic classical baseline, a single LLM call, a single LLM with a
self-correction loop, and two orchestrator designs (constrained-choice
arbitration and confidence-weighted tie-break) — across three small
open-weight models (3B, 1.5B, and 1B parameters) running entirely locally
via Ollama on an 8GB-RAM laptop, at zero monetary cost. We find that (1)
naive single-shot LLM annotation badly underperforms a free classical
marker-scoring method, with the dominant failure mode being output-format
non-compliance rather than a biological misunderstanding; (2)
orchestration substantially closes this gap but does not robustly exceed
the classical baseline on average; and (3) two concrete implementation
bugs, found only through empirical testing, generalize well beyond this
task — a label-vocabulary mismatch that silently corrupts exact-match
scoring, and an evaluator that can "validly" accept an internally
consistent but factually wrong answer. Our best single result (0.636
accuracy, exceeding the classical baseline's 0.576) comes from a
confidence-weighted orchestrator that also, in a different trial, shows a
clear failure caused by miscalibrated LLM self-reported confidence. We
argue that reconciliation *mechanism* — not model size or agent count —
is the primary lever available to small, resource-constrained agent
systems, and release our full pipeline, evaluation protocol, and results
log for reproducibility.

---

## 1. Introduction

Large language model agents are being applied across bioinformatics at a
rapid pace, from single-cell analysis pipelines to gene-set interpretation
and experimental design. Recent surveys count well over a hundred such
systems published in a two-year window, spanning genomics, proteomics,
and clinical applications. Representative systems such as CellAgent and
BioMaster automate multi-step single-cell RNA-seq workflows using
planner–executor–evaluator architectures, while general-purpose systems
like Biomni integrate retrieval-augmented planning with code execution
across a broad range of biomedical tasks.

Almost all of this work shares an implicit assumption: that the
underlying language model is a frontier-tier system accessed through a
paid API. This is a reasonable assumption for well-funded labs, but it
leaves an open question for the much larger population of students,
independent researchers, and resource-constrained groups: **does
orchestration — the core architectural idea behind agentic AI — actually
help when the model itself is small, free, and running locally?** If the
benefits of decomposition and multi-agent reconciliation depend on the
underlying model already being highly capable, then orchestration may be
far less useful in exactly the resource-constrained settings where it
would be most valuable.

We investigate this question directly, using a concrete, well-defined
bioinformatics task — cell-type annotation of single-cell RNA-seq
clusters from their marker genes — evaluated against genuine,
independently-verified ground truth. We deliberately constrain ourselves
throughout to zero monetary cost: every experiment in this paper runs on
a consumer laptop with 8GB of RAM, using open-weight models served
locally via Ollama, with no API keys and no cloud compute.

Our contributions are:

1. A systematic comparison of five annotation strategies — a
   deterministic classical baseline, a single LLM call, a single LLM with
   a self-correction loop, and two orchestrator designs — evaluated
   against real FACS-sorted ground truth.
2. A model-size sweep across three small open-weight models (3B, 1.5B,
   and 1B parameters), revealing that naive comparisons across model size
   can be misleading when a system's fallback logic can produce
   degenerate, uninformative "successes."
3. Two concrete implementation bugs, discovered empirically rather than
   anticipated in advance, both of which generalize as design principles
   for any LLM-agent evaluation: (a) semantic label-vocabulary drift can
   silently corrupt exact-match scoring even when a model's underlying
   reasoning is largely correct, and (b) an evaluator that only checks
   internal consistency between two options — rather than validating
   against the true output space — can "validly" accept a wrong answer.
4. A full open-source, reproducible pipeline and results log, runnable by
   anyone with a laptop and no budget.

---

## 2. Related Work

**Agentic AI in bioinformatics.** Recent survey work has cataloged agentic
AI systems across genomics, proteomics, spatial biology, and clinical
medicine, organizing them around common architectural patterns — most
notably planner–executor–evaluator loops and multi-agent ecosystems with
specialist and critic roles. Representative single-cell-focused systems
include CellAgent, which coordinates planner, executor, and evaluator
roles for scRNA-seq analysis, and BioMaster, which adds retrieval-
augmented planning and an explicit debugging/error-correction loop.
General-purpose biomedical agents such as Biomni integrate retrieval-
augmented reasoning with direct code execution across a broad span of
biomedical tasks, from gene prioritization to molecular cloning. Nearly
all of these systems are demonstrated using frontier-tier LLMs.

**GenoTEX and dataset scope.** We initially considered the GenoTEX
benchmark, a large, actively-maintained collection of gene-expression
analysis problems, as a candidate evaluation dataset. On inspection, its
task structure — identifying genes associated with a disease trait in
bulk cohort-level expression data via dataset selection, preprocessing,
and statistical regression — does not match single-cell clustering or
cell-type annotation. We therefore exclude it from our evaluation and
note it here only as an example of a related but structurally distinct
benchmark in the same broader space of LLM-agent bioinformatics
evaluation.

**Multi-agent orchestration patterns.** Beyond bioinformatics, hierarchical
multi-agent architectures — orchestrator/planner agents dispatching to
specialist workers, reconciled by an evaluator or critic — are a common
design pattern in general-purpose agent frameworks and have been applied
to clinical decision support with adaptive team sizing based on case
complexity. Our work is closest in spirit to this literature but narrows
the question specifically to resource-constrained, free-inference
settings, which — to our knowledge — has not been systematically studied.

---

## 3. Task, Data, and Ground Truth

**Task.** We define the task as cluster-level cell-type annotation: given
a set of Leiden clusters derived from a single-cell RNA-seq dataset and
each cluster's top differentially-expressed marker genes, assign the most
likely cell type from a fixed candidate label set.

**Dataset.** All reported results use `pbmc68k_reduced`, a peripheral
blood mononuclear cell dataset bundled directly with Scanpy, derived from
Zheng et al.'s FACS-sorted PBMC reference data. Critically, this dataset
carries genuine, independently-verified ground-truth cell-type labels
(the `bulk_labels` column) obtained via fluorescence-activated cell
sorting — not inferred computationally — across 10 real cell types and
700 cells. We deliberately avoided constructing our own reference labels
for evaluation; an earlier iteration of this project used a smaller,
unlabeled dataset (PBMC3k) with hand-derived reference labels for
pipeline development, but all *reported* results in this paper use only
the independently-verified `pbmc68k_reduced` ground truth.

**Shared preprocessing.** Every condition in this study uses an identical
preprocessing and clustering pipeline (standard QC filtering, library-size
normalization, log-transformation, PCA, and Leiden clustering at
resolution 0.6), so that any performance difference between conditions
reflects the annotation method alone, not differences in the underlying
cluster structure.

---

## 4. Methods

### 4.1 Conditions

- **Baseline 1 (Classical).** A deterministic, LLM-free method: each
  candidate cell type's marker genes are scored per cluster via Scanpy's
  `score_genes`, and the highest-scoring type is assigned. Free and
  instantaneous.
- **Baseline 2 (Single LLM).** One LLM call annotates all clusters at
  once, given their top marker genes and the full candidate label list.
  No orchestration, no retry.
- **Baseline 3 (Self-loop).** The same single LLM, but given up to three
  self-check passes: it reviews its own prior output against the exact
  candidate label list and may revise it.
- **Orchestrator (Arbitration).** The classical and LLM specialists run
  independently per cluster. A programmatic evaluator checks agreement
  after normalizing the LLM's label; disagreements trigger one batched,
  constrained-choice arbitration call in which the LLM picks between
  exactly the two specialists' answers (not a full 10-way
  re-classification). If arbitration fails to produce a valid pick, the
  classical answer is kept.
- **Orchestrator (Confidence tie-break).** The same two specialists, but
  reconciled without a second LLM call: classical reports a confidence
  signal (the margin between its top and runner-up marker score,
  available for free), and the LLM self-reports a 0–100 confidence
  alongside its label in its original call. On disagreement, the LLM's
  label wins only if classical's confidence is below the run's own
  median margin, the LLM's confidence is ≥70, and the label is a genuine
  candidate label; otherwise classical wins.

### 4.2 Evaluator design and the validity-gate principle

During development, we discovered that our first arbitration evaluator
had a real bug: it verified only that the arbitration response exactly
matched one of the two *offered* options, but never checked that the
offered LLM option was itself a genuine candidate label. When a weaker
model (qwen2.5:1.5b) invented an off-list label during the initial LLM
specialist call (e.g., "Basophils/NK Cells"), the evaluator could
"validly" echo that garbage label back during arbitration, guaranteeing
an incorrect result for that cluster while appearing internally
consistent. We fixed this by requiring the final chosen label to be a
member of the true candidate label set, regardless of which offered
option it matched, and verified the fix against the exact failure that
exposed it. We treat this as a general principle for any LLM-agent
evaluator design: **fallback and validation logic must check against the
true output space, not merely internal agreement between two of the
system's own components** — two components can be mutually "valid" and
both wrong.

### 4.3 Metrics

We report accuracy, macro-F1, weighted-F1, Adjusted Rand Index (ARI), and
Normalized Mutual Information (NMI). Because free-text LLM outputs
frequently deviate from an exact required label string even when
semantically correct, we report both **strict** (exact-match) and
**semantically-normalized** scoring for every LLM-involving condition
that has no built-in validity constraint. The normalization mapping was
derived from a pilot batch of outputs and then frozen before further
runs, to avoid post-hoc metric shopping. Orchestrator conditions do not
require this distinction, since their final outputs are validity-gated
by construction. All LLM-involving conditions are run for 5 trials with
clustering held fixed and only LLM sampling varying, reporting mean ±
standard deviation.

### 4.4 Models and infrastructure

We use three open-weight models served locally via Ollama: `llama3.2:3b`
(the primary model for most conditions), `llama3.2:1b`, and
`qwen2.5:1.5b` (used in a model-size sweep of the arbitration
orchestrator). All experiments run on a consumer laptop with 8GB of RAM
and no GPU acceleration, at zero API cost. We did not evaluate any
frontier-tier or paid-API model; this is a deliberate scope decision
reflecting the resource-constrained setting this paper investigates, not
an oversight (see Limitations).

---

## 5. Results

### 5.1 Main comparison

| Condition | Accuracy | Macro-F1 | ARI | NMI |
|---|---|---|---|---|
| Baseline 1 (Classical) | **0.576** | 0.299 | 0.515 | 0.658 |
| Baseline 2 (LLM, strict) | 0.054 ± 0.096 | 0.033 ± 0.067 | 0.458 ± 0.053 | 0.636 ± 0.037 |
| Baseline 2 (LLM, normalized) | 0.151 ± 0.109 | 0.084 ± 0.059 | 0.443 ± 0.050 | 0.614 ± 0.026 |
| Baseline 3 (Self-loop, strict) | 0.165 ± 0.169 | 0.075 ± 0.084 | 0.472 ± 0.027 | 0.656 ± 0.034 |
| Baseline 3 (Self-loop, normalized) | 0.227 ± 0.209 | 0.113 ± 0.111 | 0.472 ± 0.027 | 0.656 ± 0.034 |
| Orchestrator (Arbitration), llama3.2:3b | 0.529 ± 0.069 | 0.249 ± 0.070 | 0.502 ± 0.030 | 0.647 ± 0.021 |
| Orchestrator (Arbitration), llama3.2:1b | 0.576 ± 0.000\* | — | — | — |
| Orchestrator (Arbitration), qwen2.5:1.5b | 0.534 ± 0.094 | — | — | — |
| Orchestrator (Confidence tie-break), llama3.2:3b | **0.545 ± 0.097** | 0.279 ± 0.070 | 0.501 ± 0.031 | 0.628 ± 0.039 |

\*See §5.3 — this result is a degenerate case, not genuine model
competence.

The gap between Baseline 2's strict and normalized scores (0.054 vs.
0.151) despite near-identical ARI/NMI is itself informative: clustering-
level semantic understanding is largely intact even when exact-match
accuracy collapses, indicating that **output-format non-compliance, not
biological misunderstanding, is the dominant failure mode** for a single
unconstrained LLM call on this task.

### 5.2 Per-class patterns

Across every condition, two cell types are consistently easy to identify
— CD19+ B cells (Baseline 1 F1 = 0.953) and CD56+ NK cells (F1 = 0.892) —
reflecting their distinctive, non-overlapping marker profiles (CD79A/
CD79B/MS4A1 and GNLY/NKG7/KLRD1, respectively). Conversely, fine-grained
T-cell subtypes (naive vs. memory, regulatory vs. cytotoxic) score at or
near zero F1 across every condition tested, including the classical
baseline. This is consistent with the genuine biological difficulty of
distinguishing these subtypes from bulk marker-gene expression alone,
rather than a specific weakness of any one method.

### 5.3 Model-size sweep and the fallback degenerate case

Sweeping the arbitration orchestrator across three model sizes produced
a result that requires careful interpretation. `llama3.2:1b` achieved
0.576 ± 0.000 accuracy — apparently tying the classical baseline exactly,
with zero variance across all five trials. Inspecting the per-trial logs
shows why: in every single trial, all disagreements between the two
specialists fell back to the classical answer, because the 1B model
never once produced a valid arbitration pick. The orchestrator's fallback
safety net perfectly neutralized a non-functional arbitrator, but the
model itself contributed nothing. We flag this explicitly: **a model
that fails safely can appear to match or exceed a stronger model's
result through fallback alone, without this reflecting genuine model
competence.** Any comparison across model sizes in an orchestrated system
must report and account for fallback rate, not accuracy alone.

By contrast, `qwen2.5:1.5b` (0.534 ± 0.094, after fixing the validity-gate
bug described in §4.2) shows real engagement with the arbitration
mechanism — non-trivial agreement rates and a mix of arbitration outcomes
— landing close to `llama3.2:3b`'s result despite having roughly half as
many parameters.

### 5.4 Confidence tie-break: best result and a distinct failure mode

The confidence-weighted tie-break orchestrator achieved the highest mean
accuracy among non-degenerate orchestrator conditions (0.545 ± 0.097)
while using only one LLM call per trial, compared to up to two for the
arbitration variant. Its best individual trial (0.636 accuracy) exceeds
the classical baseline outright: two clusters where classical reported
low confidence (marker-score margins of 0.41 and 0.93, both below that
run's median) were correctly overridden by confident, correct LLM labels,
recovering a cell type (CD14+ Monocyte) that classical alone missed
entirely.

A separate trial exposes a distinct failure mode from the arbitration
bug described in §4.2. Here, the LLM's self-reported confidence (88/100)
preceded an *incorrect* override on a low-margin classical cluster,
which combined with a correct call elsewhere to produce over-prediction
of a single class, reducing that class's F1 from 0.89 (classical alone)
to 0.24. Critically, this is not a repeat of the earlier validity-gate
bug — the label itself was a genuine, valid candidate label; the problem
is that the LLM's stated confidence did not reliably track whether it
was actually correct. We observed this pattern within the very same run
that also correctly rejected three other high-confidence *invalid*
labels via the validity gate, confirming the gate itself worked as
intended — the calibration problem is separate.

This yields a clean empirical comparison: **classical's confidence
signal (marker-score margin) is well-calibrated** — the clusters it
flags as low-margin are consistently the ones that prove hardest across
every condition in this study — **while the LLM's self-reported
confidence is not equally trustworthy**, with no obvious signal
distinguishing a justified override from an unjustified one at the
confidence-score level alone.

---

## 6. Discussion

Two independent, mechanistically distinct problems explain why
orchestration in our experiments closes most of the gap to the classical
baseline but does not robustly exceed it. First, in the arbitration
design, format non-compliance (not correctness) was the dominant issue in
Baseline 2/3, and while constraining arbitration to a 2-choice format
sharply reduced this problem, some fraction of "successful" arbitration
outcomes were format-valid but content-wrong. Second, in the confidence
tie-break design, the validity gate eliminated one class of error
(invalid labels) but exposed a second, unrelated one: miscalibrated
self-reported confidence. Neither problem is really about "the model
being too small" — both are about the *reconciliation mechanism*
trusting a signal (arbitrary format compliance, or self-reported
confidence) that does not reliably track correctness.

This suggests a generalizable design principle for resource-constrained
agent systems: when a strong, cheap, deterministic baseline already
exists for a task, an LLM specialist's role should be treated as a
*conditional* signal to be validated externally (against a real output
space, or against an independently-calibrated confidence source) rather
than trusted on its own terms, whether that trust is expressed as
format-compliance or self-reported confidence.

We would expect orchestration to show a clearer advantage in settings
where no comparably strong classical baseline exists, or where the
candidate label space is large and diverse enough that hand-curated
marker dictionaries cannot practically cover it — conditions under which
the LLM specialist's contribution is not competing against an
already-strong deterministic prior.

---

## 7. Limitations

- **Single dataset, single tissue type, small scale.** All results use
  700 cells from one PBMC reference dataset. Generalization to other
  tissues, larger cell counts, or rarer cell types is untested.
- **No frontier-model comparison.** We deliberately restrict this study
  to free, locally-run models under 4B parameters, reflecting the
  resource-constrained setting under investigation. We do not know how
  our orchestrator designs would perform with a substantially more
  capable underlying model, and we explicitly avoid claiming our
  findings generalize to that regime.
- **Single clustering configuration.** While LLM-involving conditions are
  run across 5 sampling trials, the underlying clustering itself uses a
  single seed and resolution for the `pbmc68k_reduced` results; clustering
  stability across seeds is not separately evaluated.
- **Hand-curated classical marker dictionary.** Baseline 1's marker gene
  sets were manually curated from canonical literature, not learned or
  systematically validated against a larger reference; its strong
  performance should be read as a property of this specific,
  well-characterized dataset and candidate label set, not a general claim
  about classical methods.

---

## 8. Conclusion

We show that, for small, free, locally-run language models on a concrete
cell-type annotation task, naive single-shot LLM annotation substantially
underperforms a free classical baseline, primarily due to output-format
non-compliance rather than biological misunderstanding. Orchestration —
decomposing the task and reconciling specialist outputs — closes most of
this gap, but the *mechanism* by which disagreements are resolved matters
more than either model size or the mere presence of multiple components.
We identify two concrete, generalizable lessons from bugs found only
through empirical testing: reconciliation logic must validate against the
true output space, not just internal consistency between components; and
self-reported LLM confidence is not a reliable substitute for an
externally-calibrated confidence signal. Both lessons plausibly apply
well beyond this specific task and dataset.

---

## Reproducibility Statement

All code, the evaluation protocol (written and frozen before results were
generated), and a full results log documenting every experiment,
including two bugs found and fixed during development, are available at
[github.com/sikkibist/sc-agent-orchestration]. Every experiment in this
paper is runnable at zero monetary cost on consumer hardware (tested on
an 8GB-RAM laptop) using open-weight models served locally via Ollama.

---

## References

*(Draft numbering — convert to your target venue's citation style before
submission.)*

1. Survey of agentic AI systems in biomedical research, *Nature
   Biotechnology*, 2026.
2. Survey of AI agents for biological research, *Briefings in
   Bioinformatics*, 2026.
3. Survey of agentic bioinformatics discovery systems, *Briefings in
   Bioinformatics*, 2025.
4. Xiao et al., CellAgent: an LLM-driven multi-agent framework for
   automatic scRNA-seq analysis, arXiv:2407.09811, 2024.
5. Su et al., BioMaster: a multi-agent framework for bioinformatics
   workflow automation, 2025.
6. Huang et al., Biomni: a general-purpose biomedical AI agent,
   bioRxiv/*Science*, 2025.
7. Liu et al., GenoTEX: a benchmark for automated gene expression data
   analysis, arXiv:2406.15341, 2024.
8. Zheng, G.X.Y. et al., Massively parallel digital transcriptional
   profiling of single cells, *Nature Communications*, 2017. [PBMC68k
   dataset]
9. Wolf, F.A. et al., SCANPY: large-scale single-cell gene expression
   data analysis, *Genome Biology*, 2018.
10. Traag, V.A. et al., From Louvain to Leiden: guaranteeing
    well-connected communities, *Scientific Reports*, 2019.
