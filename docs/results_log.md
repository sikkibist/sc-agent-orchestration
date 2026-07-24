# Results Log

Running record of results as they're produced. Copy exact numbers here as
soon as a condition is finalized — don't rely on reconstructing them from
terminal scrollback later.

---

## Baseline 1 — Classical (marker-gene scoring, no LLM)
Dataset: pbmc68k_reduced, seed=0

| accuracy | macro_f1 | weighted_f1 | ari | nmi |
|---|---|---|---|---|
| 0.576 | 0.299 | 0.455 | 0.515 | 0.658 |

Per-class F1 highlights: CD19+ B = 0.953, CD56+ NK = 0.892, Dendritic = 0.766,
CD8+/CD45RA+ Naive Cytotoxic = 0.379. All other subtypes (T-cell subtypes,
CD34+, CD14+ Monocyte) = 0.0 — marker dict doesn't disambiguate these well.

---

## Baseline 2 — Single LLM (llama3.2:3b via Ollama, no orchestration)
Dataset: pbmc68k_reduced, seed=0 (clustering fixed), 5 trials

**Strict (exact-match) scoring:**

| metric | mean | std |
|---|---|---|
| accuracy | 0.054 | 0.096 |
| macro_f1 | 0.033 | 0.067 |
| weighted_f1 | 0.061 | 0.095 |
| ari | 0.458 | 0.053 |
| nmi | 0.636 | 0.037 |

**Semantically-normalized scoring** (see score.py CANONICAL_SYNONYMS,
frozen after this pilot batch):

| metric | mean | std |
|---|---|---|
| accuracy | 0.151 | 0.109 |
| macro_f1 | 0.084 | 0.059 |
| weighted_f1 | 0.148 | 0.101 |
| ari | 0.443 | 0.050 |
| nmi | 0.614 | 0.026 |

**Key finding:** Baseline 1 (classical) outperforms Baseline 2 (LLM, even
normalized) on every metric. Off-list vocabulary-compliance failures are
frequent (5-8 of 8 clusters per trial in most trials) and are the dominant
source of Baseline 2's poor strict-accuracy — ARI/NMI (label-invariant)
stay much higher and relatively stable, showing the model's *clustering-
level* biological understanding is reasonable even when its *output
format compliance* isn't. This directly motivates the evaluator/loop
architecture (Baseline 3 and the full orchestrator).

Easiest classes across both methods: CD19+ B, CD56+ NK (distinctive
markers). Hardest: all T-cell subtypes (CD4/CD8, Treg/Naive/Memory,
Cytotoxic variants) — genuinely overlapping marker profiles, not a bug.

---

## Baseline 3 — Single LLM + self-loop
Dataset: pbmc68k_reduced, seed=0 (clustering fixed), 5 trials, max_iterations=3

**Strict (exact-match) scoring:**

| metric | mean | std |
|---|---|---|
| accuracy | 0.165 | 0.169 |
| macro_f1 | 0.075 | 0.084 |
| weighted_f1 | 0.162 | 0.162 |
| ari | 0.472 | 0.027 |
| nmi | 0.656 | 0.034 |

**Semantically-normalized scoring:**

| metric | mean | std |
|---|---|---|
| accuracy | 0.227 | 0.209 |
| macro_f1 | 0.113 | 0.111 |
| weighted_f1 | 0.232 | 0.214 |
| ari | 0.472 | 0.027 |
| nmi | 0.656 | 0.034 |

**Comparison to Baseline 2:** self-loop improves mean strict accuracy
(0.054 → 0.165) and normalized accuracy (0.151 → 0.227), but at ~5x the
token cost (~700 → ~1300-1400 tokens/trial) and ~3x the wall-clock time
(~50-160s → 200-315s per trial). Gains are real but small relative to the
gap with Baseline 1 (0.576) and highly inconsistent across trials — std
is nearly as large as the mean for strict accuracy.

**Three failure mechanisms observed directly in trial logs (useful for
the paper's failure-taxonomy section, Section 5.5):**

1. **Self-check works well** — trial 0: self-check turned 0/8 clusters
   correct into a mapping scoring 0.44 accuracy in a single pass. The
   model can genuinely recognize and fix its own vocabulary violations.
2. **Self-check does nothing** — trial 4: three consecutive iterations
   produced *identical* output. The model was asked to check its own
   labels against the exact candidate list and did not recognize
   anything wrong, despite 6/8 labels being off-list. Self-verification
   is not reliable even when directly prompted.
3. **Self-check introduces a new failure class** — trial 1: the self-check
   response embedded the literal string `"ALL_VALID"` as a JSON *value*
   for one cluster (`{"6": "ALL_VALID"}`) instead of following the
   instruction to respond with `ALL_VALID` alone when everything's
   correct. This created an off-list label that hadn't existed in the
   previous iteration — self-checking can add errors, not just remove
   them.

**Takeaway for the full orchestrator design:** blind self-looping (same
model checking its own work with a generic prompt) gives inconsistent,
sometimes-negative returns at meaningfully higher cost. This motivates a
smarter, decomposed evaluator — e.g. one that checks specific structural
properties (valid JSON, exact label match) programmatically rather than
asking the LLM to self-diagnose in natural language.

---

## Orchestrated system (specialists + evaluator)
Dataset: pbmc68k_reduced, seed=0 (clustering fixed), 5 trials
Classical specialist (Baseline 1 logic) + LLM specialist (Baseline 2 logic),
reconciled by evaluator.py: programmatic agreement check, constrained
2-choice arbitration only for disagreements, fallback to classical if
arbitration response is invalid.

| metric | mean | std |
|---|---|---|
| accuracy | 0.529 | 0.069 |
| macro_f1 | 0.249 | 0.070 |
| weighted_f1 | 0.432 | 0.033 |
| ari | 0.502 | 0.030 |
| nmi | 0.647 | 0.021 |

**Comparison to all conditions:** orchestrator (0.529) massively outperforms
Baseline 2 (0.054-0.151) and Baseline 3 (0.165-0.227) — clear evidence that
decomposition + programmatic evaluation beats blind self-looping. But it
does NOT clearly beat Baseline 1 alone (0.576).

**Mechanism, visible directly in per-trial logs — this is the key finding:**
- 3/5 trials: arbitration produced no valid pick for any disagreement
  (fell back to classical every time) → result exactly equals Baseline 1
  (0.576). Fallback logic works exactly as designed.
- 2/5 trials: arbitration DID produce format-valid picks (0 fallbacks) —
  but accuracy dropped BELOW Baseline 1 (0.424, 0.491). The arbitrator
  followed the constrained 2-choice format correctly but chose the wrong
  content in these cases, overriding a correct classical answer with an
  incorrect LLM one.

**Conclusion:** format compliance and correctness are separate axes —
solving the compliance problem (which the constrained arbitration prompt
clearly does, unlike Baseline 2/3's open-ended prompts) doesn't
automatically solve the correctness problem. This is strong motivation for
the deferred ablation (confidence-weighted tie-break instead of always
trusting arbitration's pick) — worth running as a follow-up condition.

**Timing anomaly:** trial 3 took 2842s vs. ~230-250s for all other trials,
despite near-identical token counts (1402 in / 158 out vs. similar for
others) — likely a local system hiccup (sleep/thermal throttle), not
systematic. Noted for disclosure, not investigated further.

---

## Confidence-weighted tie-break ablation
Dataset: pbmc68k_reduced, seed=0, 5 trials, llama3.2:3b.
Deferred from the original orchestrator design discussion: instead of a
second arbitration LLM call, each specialist reports confidence in its
ORIGINAL call — classical uses its marker-score margin (top vs runner-up),
LLM self-reports 0-100 confidence in the same JSON response. On
disagreement, LLM only overrides if classical is below-median confidence
AND LLM is >=70 AND the label is a genuine candidate label (validity gate
carried over from the evaluator.py fix). Only 1 LLM call per trial instead
of up to 2.

| metric | mean | std |
|---|---|---|
| accuracy | 0.545 | 0.097 |
| macro_f1 | 0.279 | 0.070 |
| weighted_f1 | 0.474 | 0.075 |
| ari | 0.501 | 0.031 |
| nmi | 0.628 | 0.039 |

**Best single result across the entire project:** trial 1 hit 0.636
accuracy (beats Baseline 1's 0.576 outright) — two low-confidence
classical clusters were correctly overridden by confident, correct LLM
labels (CD14+ Monocyte F1 went from 0 to 0.73).

**But also the clearest evidence of a NEW failure mode, distinct from the
arbitration version's bug:** trial 2's LLM confidently (88/100) mislabeled
a low-margin cluster, combining with a correct call elsewhere to cause
over-prediction of that class (CD56+ NK F1 dropped from Baseline 1's 0.89
to 0.24). The validity gate correctly rejected invalid labels in the same
run (`invalid_llm_high_conf=3` in trial 1) — this isn't the same bug as
before. This is pure miscalibration: **the LLM's self-reported confidence
number doesn't reliably track whether it's actually right.**

**Calibration finding worth its own callout:** classical's confidence
signal (marker-score margin) IS empirically well-calibrated — the
clusters it flags as low-margin are consistently the ones that turn out
hardest across every condition tested in this project. The LLM's
self-reported confidence is not equally trustworthy — same stated
confidence level (e.g. ~85-90) sometimes preceded a correct override,
sometimes an incorrect one, with no obvious distinguishing signal.

---

## Full comparison, all conditions

| Condition | Accuracy |
|---|---|
| Baseline 1 (classical) | 0.576 |
| Baseline 2 (LLM, strict) | 0.054 ± 0.096 |
| Baseline 2 (LLM, normalized) | 0.151 ± 0.109 |
| Baseline 3 (self-loop, strict) | 0.165 ± 0.169 |
| Baseline 3 (self-loop, normalized) | 0.227 ± 0.209 |
| Orchestrator (arbitration), llama3.2:3b | 0.529 ± 0.069 |
| Orchestrator (arbitration), llama3.2:1b | 0.576 ± 0.000 (degenerate) |
| Orchestrator (arbitration), qwen2.5:1.5b | 0.534 ± 0.094 |
| Orchestrator (confidence tie-break), llama3.2:3b | 0.545 ± 0.097 |

**Overall project narrative:** decomposition + programmatic validation
(any orchestrator variant) dramatically outperforms blind LLM use
(Baseline 2/3). Among orchestrator variants, none robustly and clearly
beats the free classical baseline alone on average — but the confidence
tie-break variant shows the clearest evidence of genuine, mechanistically
understandable upside (trial 1) alongside a well-characterized failure
mode (trial 2), at the lowest cost of any LLM-involving condition. This is
a more informative and honest conclusion than either "orchestration wins"
or "orchestration doesn't help" — the mechanism matters, and confidence
calibration (not raw LLM capability) is the open problem worth pursuing
next.
Dataset: pbmc68k_reduced, seed=0, 5 trials each. Tested as a model-size
sweep (no large/frontier model was ever run — no API budget by design —
so this compares llama3.2:3b against smaller models, not small-vs-large).

| Model | Accuracy |
|---|---|
| llama3.2:3b | 0.529 ± 0.069 |
| llama3.2:1b | 0.576 ± 0.000 (degenerate — see below) |
| qwen2.5:1.5b | 0.534 ± 0.094 (post evaluator-fix, see below) |

**Critical non-obvious finding: llama3.2:1b's apparent parity with Baseline
1 is a degenerate case, not genuine competence.** Every single trial log
shows `8/8 disagreed, 8/8 fell back to classical` — the 1b model never
once produced a valid arbitration pick, so the orchestrator's fallback
safety net fired 100% of the time, making it mathematically identical to
running Baseline 1 alone. Zero variance across trials confirms this. The
model contributed nothing; it simply failed in a way the safety net
neutralizes perfectly. **Do not report this as "smaller models work
better" without this caveat** — the real lesson is about failure MODE,
not model size.

**Bug found and fixed via this run:** qwen2.5:1.5b's LLM specialist
frequently invented garbage labels (e.g. "Basophils/NK Cells", "Mono-ADCC",
"IRF8+ Memory T") that aren't real candidate labels. The evaluator's
arbitration check only verified the response exactly matched one of the
two OFFERED strings — it never checked that the offered LLM option was
itself a real label. So when qwen2.5 "validly" echoed the garbage option
back verbatim, the evaluator accepted it as a legitimate arbitration
result, guaranteeing that cluster scores 0. Fixed in evaluator.py:
`parse_arbitration_response` now also requires the chosen label to be in
the actual candidate label list. Verified with a unit test reproducing
the exact failure.

Pre-fix (buggy) qwen2.5:1.5b result: 0.382 ± 0.148 — INVALID, do not use.
Post-fix qwen2.5:1.5b result: 0.534 ± 0.094 (n=5) — the real number.

**Second lesson from this same round, about experiment hygiene, not the
model:** the first attempt at aggregating the post-fix run showed "10
trials" instead of 5 — `save_result()` appends to a per-condition CSV
rather than overwriting, so the pre-fix run's 5 rows were still in the
file and got silently blended with the post-fix run's 5 new rows,
producing a contaminated in-between number (0.458 ± 0.142, also invalid).
**Rule going forward: after any code fix that changes what a condition
measures, either delete that condition's old CSV before re-running, or
give the corrected run a distinct condition name/version suffix** — don't
silently re-use the same file.

**Takeaway for the paper (now on solid footing):** once the evaluator bug
was fixed, all three non-degenerate model configurations converge to
roughly the same accuracy (~0.53), regardless of which small model powers
the LLM specialist — the fallback-to-classical safety net makes the
orchestrator's performance robust to LLM-specialist choice. This is a
stronger, more general point than either baseline comparison alone: an
orchestrator's fallback/safety logic must validate against ground-truth
structure (the real label set), not just internal consistency (matching
one of its own offered options) — internal consistency can be satisfied
by two mutually "valid" wrong answers, and once that's fixed, the
architecture is genuinely robust across models.
