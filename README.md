# When Does Orchestration Help? Small-Model LLM Agents for scRNA-seq Cell-Type Annotation

> **Empirical research project:** Does multi-agent LLM orchestration
> actually help small, free, locally-run language models annotate
> single-cell RNA-seq cell types --- and can a model learn when it
> should trust itself versus defer to a deterministic specialist?

This repository contains a reproducible empirical study of **LLM
orchestration for single-cell RNA-seq (scRNA-seq) cell-type
annotation**, followed by a second study on **self-routing / selective
self-assessment**.

The project deliberately operates under severe resource constraints:
**free open-weight models, local inference, no paid API, no GPU, and an
8 GB RAM consumer laptop**. The goal is not to demonstrate that a large
language model can annotate cells, but to isolate **what orchestration
itself contributes**, where it fails, and whether a small model can
recognize when its own judgment should be trusted.

------------------------------------------------------------------------

## Research at a glance

### Study 1 --- Orchestration

**Question:**\
When a small LLM is weak at direct annotation, can a structured
multi-agent system recover the lost performance?

The system compares:

1.  A deterministic classical marker-gene baseline
2.  A single LLM with no orchestration
3.  A single LLM with a self-correction loop
4.  A multi-agent orchestrator using classical + LLM specialists and
    programmatic evaluation
5.  A confidence-weighted reconciliation variant

The central result is deliberately non-triumphalist:

> **Orchestration helps substantially compared with blind LLM use, but
> it does not robustly outperform the classical baseline on average. The
> reconciliation mechanism matters more than simply adding agents.**

### Study 2 --- Self-routing

**Question:**\
Can the LLM itself decide whether to trust its own annotation or defer
to the deterministic classical specialist?

The model receives marker genes and must choose:

-   `self` --- trust its own annotation
-   `defer` --- trust the classical specialist

Two variants were tested:

-   **Blind:** the model does not see the classical answer.
-   **Informed:** the model sees the classical answer as a second
    opinion, but it is not marked as correct.

Three small local models were evaluated:

-   `llama3.2:3b`
-   `llama3.2:1b`
-   `qwen2.5:1.5b`

The self-routing study found a consistent blind-setting pattern: all
three models showed a small amount of genuine discrimination in their
routing decisions, but all three still performed worse than simply
always deferring to the classical specialist.

The informed setting produced a more surprising result:

> **The 3B model became completely inert when shown the classical
> answer, while the two smaller models retained measurable independent
> routing behavior.**

A qualitative investigation identified a specific failure mode termed
**confabulated independence**: the model's explanation claimed to
disagree with the reference answer while its actual output reproduced
that answer.

------------------------------------------------------------------------

## Why this project exists

Agentic AI research often demonstrates increasingly elaborate
architectures --- planners, specialists, evaluators, loops and
arbitrators --- without isolating whether each component actually
contributes useful information.

This project takes the opposite approach.

The experimental system keeps the underlying biological problem fixed
and changes only the **decision architecture**.

That allows questions such as:

-   Does adding an LLM actually improve on a strong deterministic
    baseline?
-   Does a self-correction loop help, or merely spend more tokens?
-   Does adding multiple agents create useful independent information?
-   Does the evaluator correct errors or merely enforce formatting?
-   Is LLM confidence useful for reconciliation?
-   Can a model recognize when it is likely to be wrong?
-   Does showing a model another answer create useful evidence or simply
    cause anchoring?
-   Can an apparent model failure actually be a parser failure?

The project treats these as empirical questions rather than assumptions.

------------------------------------------------------------------------

# Dataset

The primary benchmark is:

**`pbmc68k_reduced`** from the Zheng et al. PBMC dataset, bundled with
Scanpy.

Properties:

-   700 cells
-   10 real cell types
-   FACS-sorted ground-truth labels
-   No external download required
-   Loaded with `sc.datasets.pbmc68k_reduced()`

The same dataset and preprocessing/clustering configuration are reused
across the experimental conditions.

### Development-only dataset

`PBMC3k` was used during early pipeline development and debugging.

It is **not** used for paper-reportable evaluation because it does not
provide the required independently verified cell-type ground truth for
this study.

### Excluded dataset

GenoTEX was initially considered but excluded after task inspection
because its problem is bulk gene-trait association rather than
single-cell cell-type annotation.

------------------------------------------------------------------------

# Experimental design

A critical design constraint is that all comparable conditions operate
on the **same clusters**.

The shared preprocessing pipeline is:

``` text
Expression matrix
      │
      ▼
    QC
      │
      ▼
Normalization
      │
      ▼
Log transform
      │
      ▼
PCA
      │
      ▼
Leiden clustering
(resolution = 0.6)
      │
      ▼
Top marker genes per cluster
      │
      ├───────────────┬────────────────┐
      ▼               ▼                ▼
 Classical          LLM              Other
 specialist       specialist        conditions
```

The clustering is fixed across trials. Only the
annotation/reconciliation mechanism changes.

This prevents differences in upstream clustering from contaminating
comparisons between annotation systems.

------------------------------------------------------------------------

# Study 1 --- Orchestration conditions

## Condition 1 --- Classical baseline

A deterministic marker-gene scoring system assigns each cluster a
cell-type label.

This provides the non-LLM reference point.

It is important because the research question is not:

> "Can an LLM annotate cells?"

It is:

> "Does orchestration provide useful information beyond an existing
> deterministic method?"

------------------------------------------------------------------------

## Condition 2 --- Single LLM

A single local LLM receives the cluster marker genes and directly
predicts cell-type labels.

No:

-   specialist decomposition
-   evaluator
-   arbitration
-   self-loop
-   external correction

This isolates the raw contribution of the LLM.

------------------------------------------------------------------------

## Condition 3 --- Single LLM + self-loop

The same LLM is allowed to inspect and revise its own output.

This tests whether iterative self-correction alone explains any
improvement that might otherwise be attributed to multi-agent
orchestration.

Observed behavior showed that self-correction can repair some formatting
errors, but it is inconsistent and can also introduce new errors.

------------------------------------------------------------------------

## Condition 4 --- Multi-agent orchestrator

Two specialists operate independently:

``` text
                 ┌─────────────────────┐
                 │   Cluster markers   │
                 └──────────┬──────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
      ┌──────────────────┐    ┌──────────────────┐
      │ Classical        │    │ LLM specialist   │
      │ marker scorer     │    │                  │
      └─────────┬────────┘    └────────┬─────────┘
                │                      │
                └──────────┬───────────┘
                           ▼
                 ┌────────────────────┐
                 │ Programmatic       │
                 │ evaluator          │
                 └─────────┬──────────┘
                           │
                  agreement / disagreement
                           │
              ┌────────────┴─────────────┐
              ▼                          ▼
          Agreement                 Disagreement
              │                          │
              ▼                          ▼
          accept label          constrained arbitration
                                         │
                                         ▼
                                  final label + gate
```

When both specialists agree, the system accepts the agreement.

When they disagree, the evaluator can invoke a constrained arbitration
step.

The arbitration prompt is not allowed to invent a completely new answer:
it chooses between the specialist outputs.

A programmatic validity gate prevents invalid or off-list labels from
becoming final answers.

------------------------------------------------------------------------

# Condition 5 --- Confidence-weighted reconciliation

A second orchestrator variant removes the separate arbitration call.

The classical specialist provides a confidence signal based on the
margin between its top and runner-up marker scores.

The LLM provides self-reported confidence on a 0--100 scale.

The LLM is allowed to override the classical answer only when:

-   the classical prediction has low confidence,
-   the LLM reports sufficiently high confidence,
-   the LLM label is a valid candidate label.

Otherwise the system defaults to the classical prediction.

This is intentionally conservative and classical-biased.

------------------------------------------------------------------------

# Study 1 --- Main results

Mean accuracy across the original experimental conditions:

  Condition                                   Accuracy
  ------------------------------------ ---------------
  Classical baseline                         **0.576**
  Single LLM, strict                     0.054 ± 0.096
  Single LLM, semantic normalization     0.151 ± 0.109
  Single LLM + self-loop, strict         0.165 ± 0.169
  Single LLM + self-loop, normalized     0.227 ± 0.209
  Orchestrator, arbitration              0.529 ± 0.069
  Orchestrator, confidence tie-break     0.545 ± 0.097

The orchestration variants dramatically outperform blind single-LLM use,
but neither reliably exceeds the classical baseline on average.

### Important result

The best individual result was:

**0.636 accuracy**

from a confidence-weighted orchestration trial, exceeding the classical
baseline of 0.576.

However, this did not translate into a robust average improvement.

This distinction matters: **a best-case result is not the same thing as
a reliable system-level advantage.**

------------------------------------------------------------------------

# What Study 1 actually discovered

## 1. Raw LLM failure was largely a format problem

The single LLM often produced labels outside the allowed vocabulary.

This caused very poor exact-match accuracy even when label-invariant
metrics such as ARI and NMI remained substantially higher.

In other words:

> The model sometimes had a biologically plausible clustering
> interpretation but failed to express the answer in the required label
> space.

This is why exact-match accuracy alone can be misleading.

------------------------------------------------------------------------

## 2. Self-correction is not automatically reliable

The self-loop sometimes fixed errors.

It also sometimes:

-   failed to notice invalid labels,
-   repeated identical wrong outputs,
-   introduced new formatting errors.

The extra loop increased token usage and wall-clock time without closing
the gap to the classical baseline.

------------------------------------------------------------------------

## 3. Arbitration can be format-correct but factually wrong

The constrained arbitration mechanism solved an important structural
problem: it could select one of the offered labels.

But format compliance did not guarantee biological correctness.

In some trials, arbitration replaced a correct classical prediction with
an incorrect LLM prediction.

This exposed an important distinction:

``` text
Output compliance ≠ factual correctness
```

------------------------------------------------------------------------

## 4. Classical confidence was more useful than LLM confidence

The classical specialist's marker-score margin behaved as a useful
uncertainty signal.

The LLM's self-reported confidence did not.

The same high confidence values could precede both correct and incorrect
predictions.

This motivated the second study.

------------------------------------------------------------------------

# Study 2 --- Self-routing

The second study removes the externally imposed reconciliation decision.

Instead, the LLM must choose its own role.

For each cluster it returns:

``` text
predicted_label
routing_decision
reason
confidence
```

where:

``` text
routing_decision ∈ {self, defer}
```

The central question becomes:

> Does the model know when it should trust itself?

------------------------------------------------------------------------

# Self-routing variants

## Blind routing

The model sees only:

-   marker genes
-   candidate label space
-   its own task

It does **not** see the classical specialist's answer.

This tests whether the model can assess its own reliability
independently.

### Result

All three models showed a positive `Delta_route`:

``` text
Delta_route =
P(route = self | LLM correct)
-
P(route = self | LLM wrong)
```

So there is a small genuine signal.

But the signal is not strong enough to compensate for the model's high
error rate.

All three models performed worse than the simple:

``` text
always defer to classical
```

strategy.

  Model            Actual accuracy   Always-defer accuracy
  -------------- ----------------- -----------------------
  llama3.2:3b                0.400                   0.625
  llama3.2:1b                0.425                   0.625
  qwen2.5:1.5b               0.450                   0.625

The important distinction is:

> **The models were not completely unaware of their own reliability.
> Their self-assessment signal existed, but it was too weak to be
> operationally useful.**

------------------------------------------------------------------------

# Informed routing

In the informed condition, the model sees:

``` text
LLM's own prediction
+
Classical specialist prediction
```

but is not told which answer is correct.

The model must decide whether to:

``` text
self
```

or:

``` text
defer
```

### Result

This produced a striking model-dependent effect.

  Model            Actual accuracy   Always-defer   Delta_route   Discordant
  -------------- ----------------- -------------- ------------- ------------
  llama3.2:3b                0.625          0.625        -0.133           0%
  llama3.2:1b                0.625          0.625        +0.250        12.5%
  qwen2.5:1.5b               0.550          0.625        +0.135        15.0%

The 3B model never changed the final outcome in 40 cluster-trials.

The two smaller models retained measurable independent routing behavior.

This is counterintuitive because a simple capability-scaling assumption
would predict the larger model to make the better routing decision.

------------------------------------------------------------------------

# Confabulated independence

The informed 3B behavior led to a more specific qualitative failure
analysis.

The model sometimes produced reasoning that explicitly claimed to
disagree with the displayed reference answer.

But its actual selected label reproduced the reference answer exactly.

Conceptually:

``` text
Reasoning:
"I disagree with the classical specialist because ..."

Output:
same label as classical specialist
```

This is called **confabulated independence** in the paper draft.

It differs from ordinary anchoring because the model does not merely
follow the reference silently; its verbal explanation presents an
apparent independent disagreement that is not reflected in the actual
decision.

This is one of the central findings of the second paper.

------------------------------------------------------------------------

# Parser robustness was itself a research finding

During the self-routing study, the 1B model initially appeared to be a
degenerate router.

The model was producing responses that were often
biologically/content-correct but structurally invalid JSON.

Examples included:

-   unclosed outer JSON objects
-   cluster objects wrapped incorrectly
-   malformed object structure despite valid per-cluster content

A strict parser converted these outputs into `PARSE_ERROR` and
effectively defaulted them to `defer`.

This created a false conclusion:

``` text
Observed:
"1B always defers"

Actual:
"1B often produces malformed JSON"
```

A fallback parser was therefore implemented:

``` text
Strict JSON parser
       │
       ├── success ──► normal extraction
       │
       └── failure
             │
             ▼
      per-cluster fallback
      extraction / recovery
```

The malformed outputs that caused the original result were explicitly
re-tested after the parser change.

The corrected results showed that the 1B model was **not** a degenerate
router.

This leads to a broader methodological lesson:

> In LLM-agent experiments, parser failure can masquerade as reasoning
> failure.

------------------------------------------------------------------------

# Evaluation metrics

The project uses multiple complementary metrics.

## Classification metrics

-   Accuracy
-   Macro F1
-   Weighted F1
-   Adjusted Rand Index (ARI)
-   Normalized Mutual Information (NMI)

## Self-routing metrics

### Accuracy conditional on routing

How often is the model correct when it chooses:

``` text
self
```

versus:

``` text
defer
```

### Delta-route

``` text
Delta_route =
P(self | correct)
-
P(self | wrong)
```

Positive values indicate some discrimination.

### Always-defer baseline

The accuracy obtained if every routing decision is replaced with:

``` text
defer
```

This is essential because a router can have positive discrimination
while still making the overall system worse.

### Prevalence-matched random baseline

A routing baseline that preserves the model's observed self/defer
frequency while randomizing which clusters receive each decision.

This separates:

-   useful discrimination from
-   merely choosing `self` too frequently or too rarely.

### Oracle ceiling

The best possible routing performance if the system always chooses the
correct specialist whenever at least one specialist is correct.

This estimates how much potential remains in the disagreement cases.

------------------------------------------------------------------------

# Implementation safeguards

The project deliberately includes programmatic safeguards rather than
trusting LLM outputs blindly.

### Candidate-label validation

A model cannot introduce arbitrary cell-type labels into the final
result.

### Validity gate

If an LLM routes to `self` but its label is invalid, the routing
decision is overridden to `defer`.

### Semantic normalization

For exploratory comparison, known synonymous labels can be normalized
before scoring.

Strict and normalized results are kept separate.

### Robust parsing

Malformed LLM output is handled explicitly rather than silently treated
as biological failure.

### Fixed clustering

All comparable annotation conditions operate on the same cluster
assignments.

### Trial logging

Per-trial JSON logs are committed so reported results can be traced back
to individual model outputs.

------------------------------------------------------------------------

# Reproducibility

The project is designed to be reproducible without paid infrastructure.

## Hardware target

The experiments were designed around:

-   Consumer laptop
-   8 GB RAM
-   CPU inference
-   No GPU
-   No paid API

## Model serving

Models are served locally through **Ollama**.

Primary models include:

``` text
llama3.2:3b
llama3.2:1b
qwen2.5:1.5b
```

## Installation

``` bash
git clone https://github.com/sikkibist/sc-agent-orchestration.git
cd sc-agent-orchestration

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

Install Ollama separately and pull the required models:

``` bash
ollama pull llama3.2:3b
ollama pull llama3.2:1b
ollama pull qwen2.5:1.5b
```

------------------------------------------------------------------------

# Reproducing Study 1

Classical baseline:

``` bash
python src/eval/run_baseline1_classical.py --seed 0
```

Single LLM:

``` bash
for t in 0 1 2 3 4; do
    python src/eval/run_baseline2_single_llm.py --seed 0 --trial $t
done
```

Self-loop:

``` bash
for t in 0 1 2 3 4; do
    python src/eval/run_baseline3_self_loop.py --seed 0 --trial $t
done
```

Orchestrator:

``` bash
for t in 0 1 2 3 4; do
    python src/eval/run_orchestrator.py --seed 0 --trial $t
done
```

Confidence-weighted orchestrator:

``` bash
for t in 0 1 2 3 4; do
    python src/eval/run_orchestrator_confidence.py --seed 0 --trial $t
done
```

Aggregate results:

``` bash
python src/eval/aggregate_results.py --condition <condition_name>
```

------------------------------------------------------------------------

# Repository structure

``` text
sc-agent-orchestration/
│
├── data/
│   └── README.md
│
├── docs/
│   ├── architecture.md
│   ├── evaluation_protocol_v1.md
│   ├── results_log.md
│   ├── paper_outline_v1.md
│   ├── paper_draft_v1.md
│   ├── paper_draft_v1.docx
│   │
│   ├── self_routing_design_v2.md
│   ├── self_routing_design_v2.docx
│   ├── paper2_self_routing_draft_v1.md
│   └── paper2_self_routing_draft_v1.docx
│
├── experiments/
│   └── results/
│       ├── CSV summary files
│       └── per-trial JSON logs
│
├── src/
│   ├── agents/
│   │   ├── evaluator.py
│   │   ├── orchestrator.py
│   │   └── specialists/
│   │       ├── annotation_agent.py
│   │       └── clustering_agent.py
│   │
│   └── eval/
│       ├── aggregate_results.py
│       ├── confidence_tiebreak.py
│       ├── data_utils.py
│       ├── evaluator.py
│       ├── run_baseline1_classical.py
│       ├── run_baseline2_single_llm.py
│       ├── run_baseline3_self_loop.py
│       ├── run_condition_orchestrated.py
│       ├── run_orchestrator.py
│       ├── run_orchestrator_confidence.py
│       └── score.py
│
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

------------------------------------------------------------------------

# Documentation

## Study 1

-   `docs/evaluation_protocol_v1.md` --- frozen experimental protocol
-   `docs/architecture.md` --- system architecture and reconciliation
    mechanisms
-   `docs/results_log.md` --- running record of exact experimental
    results
-   `docs/paper_outline_v1.md` --- paper structure
-   `docs/paper_draft_v1.md` --- full Study 1 manuscript draft
-   `docs/paper_draft_v1.docx` --- Word version

## Study 2

-   `docs/self_routing_design_v2.md` --- self-routing design and
    completed results
-   `docs/paper2_self_routing_draft_v1.md` --- full Study 2 manuscript
    draft
-   `docs/paper2_self_routing_draft_v1.docx` --- Word version

The two studies are intentionally linked:

``` text
Study 1
"What happens when we orchestrate specialists?"
                 │
                 ▼
Finding:
"Reconciliation mechanism matters."
                 │
                 ▼
Study 2
"Can the model choose which specialist to trust?"
                 │
                 ▼
Finding:
"Self-routing has weak signal, but is not reliable;
reference exposure can produce anchoring/confabulated independence."
```

------------------------------------------------------------------------

# Current research status

### Study 1

-   [x] Dataset selected
-   [x] Evaluation protocol frozen
-   [x] Classical baseline
-   [x] Single LLM baseline
-   [x] Self-loop baseline
-   [x] Multi-agent arbitration orchestrator
-   [x] Confidence-weighted reconciliation
-   [x] Multiple model evaluations
-   [x] Per-trial result logging
-   [x] Failure-mode analysis
-   [x] Paper draft

### Study 2

-   [x] Self-routing task designed
-   [x] Blind variant
-   [x] Informed variant
-   [x] llama3.2:3b
-   [x] llama3.2:1b
-   [x] qwen2.5:1.5b
-   [x] Parser failure identified
-   [x] Parser fallback implemented
-   [x] Malformed outputs re-verified
-   [x] Routing metrics computed
-   [x] 3B informed collapse identified
-   [x] Confabulated independence investigated
-   [x] Paper 2 draft written
-   [ ] Independent literature verification for selective prediction /
    calibration references
-   [ ] Additional targeted experiments on the informed 3B anchoring
    mechanism
-   [ ] Larger/multiple independent datasets
-   [ ] Final manuscript submission version

------------------------------------------------------------------------

# Limitations

The conclusions should not be generalized beyond the tested setting
without further experiments.

### Single biological benchmark

The reported results are based on `pbmc68k_reduced`.

A larger and biologically diverse benchmark is needed to determine
whether the observed routing and orchestration behavior generalizes.

### Fixed clustering

The project evaluates annotation rather than the full:

``` text
QC → normalization → dimensionality reduction
→ clustering → annotation
```

pipeline.

This isolates the annotation problem but does not measure end-to-end
pipeline robustness.

### Small number of trials

The core experiments use five trials per condition/model with fixed
clustering and varied LLM sampling.

This is sufficient for mechanistic exploration but not a substitute for
large-scale statistical benchmarking.

### Small local models

No frontier-tier or paid API model is used.

The conclusions therefore concern **resource-constrained local models**,
not LLMs in general.

### Confidence is self-reported

The LLM confidence score is not a calibrated probability.

The experiments explicitly show why treating it as one is dangerous.

------------------------------------------------------------------------

# Research philosophy

This repository intentionally records failed ideas, bugs, parser
problems, negative results, and counterintuitive findings.

A result such as:

``` text
"orchestration did not beat the baseline"
```

is not treated as a failed project.

Likewise:

``` text
"the model is a degenerate router"
```

is not accepted until alternative explanations --- including
implementation and parsing artifacts --- have been eliminated.

The project therefore emphasizes:

-   controlled comparisons
-   frozen protocols
-   deterministic baselines
-   explicit ablations
-   programmatic validation
-   per-trial logs
-   failure-mode analysis
-   parser robustness
-   negative results
-   reproducibility on inexpensive hardware

The goal is not to prove that multi-agent systems are better.

The goal is to determine **when, why, and under what mechanisms
orchestration provides useful information --- and when it merely adds
complexity.**

------------------------------------------------------------------------

# License

MIT License. See [`LICENSE`](LICENSE).

------------------------------------------------------------------------

# Citation

The repository currently contains two manuscript drafts:

1.  **When Does Orchestration Help? Small-Model LLM Agents for scRNA-seq
    Cell-Type Annotation**
2.  **Can a Small Language Model Know When to Trust Itself? Self-Routing
    in Free, Local LLM Orchestration for Single-Cell Annotation**

A formal citation record will be finalized before publication.

------------------------------------------------------------------------

## Repository

https://github.com/sikkibist/sc-agent-orchestration
