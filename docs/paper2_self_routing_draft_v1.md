# Can a Small Language Model Know When to Trust Itself? Self-Routing in Free, Local LLM Orchestration for Single-Cell Annotation

## Abstract

In a companion study ("When Does Orchestration Help?"), we found that
orchestrating a classical marker-scoring specialist with a small,
free, locally-run LLM narrows — but does not close — the gap to a
purely classical baseline on single-cell RNA-seq cell-type annotation,
and that the *reconciliation mechanism* between specialists matters
more than model size or agent count. In that study, the researcher
decided the reconciliation rule; the model itself never chose its own
role. Here we ask the natural next question: can a small, free LLM
decide *for itself* whether to trust its own annotation or defer to a
deterministic specialist? We test this directly with a self-routing
task across three small open-weight models (3B, 1.5B, and 1B
parameters), in two variants — blind (no reference answer shown) and
informed (a second opinion shown, not marked correct) — evaluated
against genuine FACS-sorted ground truth, entirely on free, local
infrastructure. We find a universal pattern in the blind setting: every
model shows a small amount of genuine self-awareness (routing to
"self" somewhat more often when actually correct), yet every model
still substantially underperforms simply always deferring to the
classical specialist, because self-routing happens far more often than
warranted by actual reliability. In the informed setting we find a
sharper, model-dependent, and counterintuitive result: the *largest*
model tested (3B) shows complete routing collapse — its routing
decision never once changed the final outcome across 40 cluster-trials
— while the two smaller models retain real, if modest, independent
judgment. A hand-coding pass traces the 3B collapse to a specific,
nameable failure we term *confabulated independence*: the model's
stated reasoning explicitly claims to override the shown reference
answer, while its output reproduces that answer exactly, in every
traced instance. We also report a methodological finding of
independent interest: an initial result suggesting the smallest model
(1B) was a "degenerate router" was itself an artifact of that model
producing content-correct but structurally invalid JSON, corrected
with a more robust parser and verified against the exact malformed
outputs that caused it.

---

## 1. Introduction

Agentic AI systems for bioinformatics are typically evaluated with a
fixed, researcher-designed architecture: a fixed set of specialists,
a fixed reconciliation rule, a fixed loop budget. Our companion study
found that for a small, free, locally-run LLM annotating single-cell
RNA-seq clusters, this kind of orchestration recovers most of the
performance lost by using the LLM alone, but does not reliably exceed
a free classical baseline — and traced this shortfall to two
mechanistic causes: constrained-choice arbitration is format-compliant
but not always content-correct, and self-reported LLM confidence is
not a reliable tie-breaking signal.

Both of those findings raise a more basic question that the original
study's architecture could not answer, because the researcher — not
the model — decided how disagreements were resolved: **does the model
itself have any genuine insight into when its own judgment should be
trusted?** This is the question of *selective self-assessment* — can a
small, resource-constrained LLM recognize its own reliability well
enough to make a good routing decision, or does it need an external
mechanism (like the evaluator studied previously) to do this for it?

We study this directly with a self-routing task: given cluster marker
genes, the LLM predicts a label, decides whether to trust that label
("self") or defer to a classical specialist ("defer"), and reports a
confidence score and a stated reason — all in a single call. We test
two variants (blind and informed) across three small open-weight
models, entirely on free, local infrastructure, evaluated against the
same genuine FACS-sorted ground truth used throughout this line of
work.

**Contributions:**
1. A direct, quantified test of whether small LLMs can self-assess
   their own reliability on a concrete bioinformatics task, using
   metrics (discrimination via Delta_route, oracle-ceiling recovery,
   prevalence-matched baselines) adapted from the selective-prediction
   literature to this setting.
2. A model-dependent, counterintuitive finding: the largest model
   tested anchors completely on a shown reference answer, while
   smaller models retain more independent judgment — the opposite of
   what capability scaling alone would predict.
3. A precisely traced failure mode, *confabulated independence*,
   distinguished from simple anchoring by direct evidence that the
   model's stated reasoning and its actual output diverge.
4. A methodological correction, documented transparently: an initial
   "degenerate router" finding for the smallest model was a JSON
   parsing artifact, not real model behavior — fixed and verified
   against the exact data that caused it.

---

## 2. Related Work

This study reuses the same literature grounding as our companion paper:
recent surveys document a rapidly growing population of agentic AI
systems in bioinformatics, organized around planner-executor-evaluator
and specialist-reconciliation patterns, with representative systems
such as CellAgent, BioMaster, and Biomni. As in the companion study,
we note that essentially all of this prior work assumes access to a
frontier-tier model; the resource-constrained, free-inference setting
studied here and in the companion paper remains comparatively
unexamined.

This study's specific question — can a model's own stated confidence
or routing decision be trusted — connects to a broader machine
learning literature on selective prediction, calibration, and
abstention. *(Note: specific citations to that literature to be added
after independent verification before submission — not included here
to avoid citing unverified sources, consistent with the verification
process used for the companion paper's reference list.)*

---

## 3. Task, Data, and Method

**Dataset and preprocessing**: identical to the companion study —
`pbmc68k_reduced` (Zheng et al., bundled with Scanpy), genuine
FACS-sorted ground truth, 10 real cell types, 700 cells, shared
QC/normalization/clustering pipeline (Leiden, resolution 0.6).

**Classical specialist**: the same deterministic marker-gene-scoring
method from the companion study, extended to report a confidence
signal (the margin between its top and runner-up marker score).

**Self-routing task**: in a single LLM call, given cluster marker
genes, the model returns per cluster: a predicted label, a routing
decision ("self" or "defer"), a one-sentence stated reason, and a
0–100 confidence score.

**Two variants**:
- *Blind*: the model sees only its own marker-gene input — no
  classical output is shown.
- *Informed*: the model additionally sees the classical specialist's
  label for that cluster (not marked as correct).

**Validity gate**: if the model routes to "self" but its own label is
not a genuine candidate label, the routing choice is forced to
"defer" regardless of stated confidence — the same principle
established in the companion study's evaluator design, applied here.

**Models**: llama3.2:3b, llama3.2:1b, qwen2.5:1.5b, all served locally
via Ollama, zero monetary cost, run on an 8GB-RAM consumer laptop — no
frontier-tier or paid-API model evaluated, consistent with the
resource-constrained scope of this line of work.

**Metrics**: alongside standard classification metrics, we report:
accuracy conditioned on routing choice; a 2×2 correctness table
(classical × LLM, both right / both wrong / only one right) to
identify how often the routing decision could plausibly matter;
**Delta_route** = P(route=self | LLM correct) − P(route=self | LLM
wrong), the central discrimination metric — a model with genuine
self-awareness should route to "self" disproportionately when it is
actually correct; an **oracle ceiling** (accuracy if routing were
always correct, when at least one specialist is right); and a
**prevalence-matched random baseline** (expected accuracy if routing
were random at the model's own observed self-rate, isolating
discrimination skill from routing frequency).

**Trials**: 5 trials per model per variant, clustering held fixed,
LLM sampling varied — identical protocol to the companion study.

**Parser robustness (methodological note)**: llama3.2:1b was found to
consistently produce content-correct but structurally invalid JSON
(unclosed outer braces, or per-cluster objects incorrectly wrapped and
comma-joined rather than nested as keys of one object). An initial
strict-JSON parser silently defaulted every malformed response to
"defer," producing what looked like a fully degenerate router. This
was corrected with a parser that falls back to regex-based per-cluster
extraction when strict parsing fails or is incomplete, verified
against the exact malformed strings that caused the original failure;
well-formed responses are unaffected (verified with no regression on
llama3.2:3b's output). This is reported as a substantive methodological
finding, not just a bugfix: **evaluating a weaker model's reasoning
requires a parser at least as robust as the strongest model tested**,
or format failures will masquerade as reasoning failures.

---

## 4. Results

### 4.1 Blind self-routing — universal pattern across all three models

| Model | Acc(self) | Acc(defer) | Actual | Always-defer | Delta_route | Self-rate | Discordant |
|---|---|---|---|---|---|---|---|
| llama3.2:3b | 0.176 | 0.565 | 0.400 | 0.625 | +0.088 | 42.5% | 57.5% |
| llama3.2:1b | 0.125 | 0.625 | 0.425 | 0.625 | +0.632 (n=2, noisy) | 40.0% | 57.5% |
| qwen2.5:1.5b | 0.200 | 0.700 | 0.450 | 0.625 | +0.196 | 50.0% | 57.5% |

Every model shows a positive Delta_route — a small amount of genuine
signal about its own reliability exists — yet **every model
substantially underperforms simply always deferring to classical**
(0.400–0.450 actual vs. 0.625 always-defer). Confidence–correctness
correlation is negative for all three models (−0.139, −0.305, −0.323),
replicating the companion study's label-confidence miscalibration
finding at this meta level: self-reported confidence should not be
trusted as a reliability signal, regardless of model.

The mechanism is consistent across models: self-routing occurs far
more often (40–50% of clusters) than is actually warranted by
reliability (12.5–20% accuracy when self-routed) — a small amount of
real discrimination is present but swamped by systematic
over-confidence in one's own judgment.

### 4.2 Informed self-routing — a model-dependent, counterintuitive result

| Model | Acc(self) | Acc(defer) | Actual | Always-defer | Delta_route | Self-rate | Discordant |
|---|---|---|---|---|---|---|---|
| llama3.2:3b | 0.556 | 0.682 | 0.625 | 0.625 | −0.133 (inverted) | 45.0% | **0.0%** |
| llama3.2:1b | 0.647 | 0.609 | 0.625 | 0.625 | +0.250 | 42.5% | 12.5% |
| qwen2.5:1.5b | 0.577 | 0.500 | 0.550 | 0.625 | +0.135 | 65.0% | 15.0% |

**llama3.2:3b's routing decision never once changed the final outcome
across all 40 cluster-trials** (0% discordant) and its discrimination
is inverted. Both smaller models show real discordance (12.5%, 15.0%)
and positive discrimination; only llama3.2:1b's informed routing beats
its own prevalence-matched baseline (+0.053) — qwen2.5:1.5b does not
(−0.010), because it self-routes very frequently (65%) while
recovering only 20% of available oracle headroom.

**This inverts the naive prediction that a larger model would show
more robust independent judgment.** The opposite occurred.

### 4.3 Qualitative hand-coding: confabulated independence

A hand-coding pass (see companion document, `self_routing_qualitative
_coding.md`) traced the llama3.2:3b informed collapse to a specific
mechanism. For every "self"-routed cluster across all 5 trials, the
model's own predicted label was **identical, character-for-character,
to the classical label it had just been shown** — while its stated
reason explicitly claimed independence (e.g. "strong B-cell markers...
**despite the other method's guess**," where the "other method's
guess" and the model's own answer are the same string). We term this
**confabulated independence**: the model's narrated reasoning and its
verifiable output diverge in a specific, traceable way. This is a
stronger and more precise claim than generic "anchoring," though we
note a caveat — the affected clusters (Dendritic, CD19+ B, CD56+ NK)
are also the most biologically distinctive clusters in this dataset,
so genuine independent convergence cannot be fully ruled out as a
partial contributor alongside the templated justification pattern
observed.

A secondary finding from the same pass: at least one instance of an
**invented marker-gene association** was found (qwen2.5:1.5b citing
IRF8 as "a general stress response gene," when it is in fact a
transcription factor central to dendritic/myeloid lineage commitment).
This is structurally indistinguishable from genuine marker citation —
both name a real gene confidently — but is biologically incorrect,
illustrating that format-level heuristics (does the reasoning cite
genes?) cannot substitute for actual biological verification when
judging LLM-generated justifications.

---

## 5. Discussion

Two distinct, model-dependent failure mechanisms explain why
self-routing does not yet provide reliable value on this task. In the
blind setting, the failure is *universal but partial*: every model
tested has some real, measurable insight into its own reliability
(positive Delta_route in every case), but this signal is too weak
relative to a high base error rate on self-generated answers, so
routing more often than warranted erases the benefit. In the informed
setting, the failure is *model-dependent and structurally different*:
the largest model collapses into confabulated independence, while
smaller models retain partial genuine judgment.

This second finding is the more novel and more concerning one from a
systems-design perspective: **it suggests that giving a larger,
nominally more capable model a reference answer to consider can make
its judgment less independent, not more** — the opposite of what a
naive "bigger model, better reasoning" assumption would predict. If
this generalizes beyond this specific task and dataset, it has a
direct practical implication for anyone building LLM-based
reconciliation systems: showing a reference answer to a capable model
as a "second opinion" may not add the intended value, and could
instead just produce a confident restatement of that reference,
narrated as independent confirmation.

---

## 6. Limitations

- **Single dataset, single tissue, small scale**, identical to the
  companion study's limitations — 700 cells, one PBMC reference
  dataset.
- **No frontier-model comparison**, a deliberate scope decision
  consistent with the resource-constrained setting of this entire
  line of work, not an oversight.
- **Single-coder qualitative pass** (Section 4.3) — no formal
  inter-rater reliability was computed; a second independent coder
  would strengthen this section before formal submission.
- **Small subgroup sample sizes** in places — e.g. llama3.2:1b's
  blind "LLM correct" subgroup has only n=2, making that specific
  Delta_route figure (+0.632) unreliable in isolation; we report it
  but do not lean on it as a standalone claim.
- **Confound in the anchoring finding**: the clusters showing
  confabulated independence are also the most biologically
  unambiguous clusters in the dataset, so genuine independent
  convergence cannot be fully excluded as a partial contributor.
- **No formal statistical significance testing** given small per-cell
  sample sizes throughout (5 trials × 8 clusters per condition);
  results are reported descriptively with explicit sample sizes
  rather than p-values.

---

## 7. Future Work

Rather than expanding this study's scope further, we name three
directions explicitly, deliberately left for future work rather than
pursued here:

1. **Difficulty-aware evaluation**: test whether self-routing (and
   orchestration generally) provides increasing benefit as annotation
   ambiguity increases — e.g. via marker-gene dropout or corruption,
   or by stratifying clusters by known biological difficulty rather
   than treating all clusters as equally hard.
2. **Agent diversity and correlated errors**: determine whether
   multiple LLM specialists (same model, different prompts; or
   different model families) provide genuinely independent evidence,
   or reproduce correlated errors from shared training biases —
   directly relevant to whether "more agents" would help beyond what
   this and the companion study tested.
3. **Direct anchoring test**: deliberately show the informed variant
   an *incorrect* classical label and measure whether llama3.2:3b
   still reproduces it — a small, targeted experiment that would
   upgrade the confabulated-independence finding from strongly
   suggestive to directly demonstrated causally, without requiring
   the larger architectural changes explored in early brainstorming
   for this line of work.

---

## 8. Conclusion

Small, free, locally-run LLMs show a small amount of genuine insight
into their own reliability, but this signal is consistently too weak
to produce net value over simply deferring to a free classical
baseline. When given a reference answer to consider, this picture
becomes more specific and more concerning: the largest model tested
collapses into a traceable pattern we term confabulated independence —
narrating independent judgment while exactly reproducing the shown
answer — while smaller models retain more genuine independent
judgment, inverting the naive expectation that capability scales with
robustness to anchoring. Alongside a corrected methodological lesson
about parser robustness in evaluating weaker models, this study extends
our companion work's central finding — that reconciliation *mechanism*
matters more than model size or agent count — to the harder, more
basic question of whether a model can be trusted to choose its own
role in that mechanism at all.

---

## Reproducibility Statement

All code, the design document (including the pre-registered hypothesis
table filled in with actual outcomes), the qualitative coding pass, and
a full results log are available at
[github.com/sikkibist/sc-agent-orchestration]. Every experiment is
runnable at zero monetary cost on consumer hardware using open-weight
models served locally via Ollama.

---

## References

*(Reusing the verified reference list from the companion paper, since
this study shares its dataset and infrastructure. See that paper's
reference list for full details on: agentic AI survey papers,
CellAgent, BioMaster, Biomni, Zheng et al. 2017 [PBMC68k dataset],
Wolf et al. 2018 [Scanpy], Traag et al. 2019 [Leiden]. Additional
citations to the selective-prediction/calibration literature to be
added and independently verified before formal submission.)*
