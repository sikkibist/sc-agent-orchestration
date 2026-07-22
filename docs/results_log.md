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

## Orchestrated system, small model variant
*(not yet run)*
