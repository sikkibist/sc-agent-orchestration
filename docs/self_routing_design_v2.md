# Follow-Up Study Design — RESULTS UPDATE

## Self-Routing in Free, Local LLM Orchestration: Does the Model Know Which Specialist to Trust?

Companion to: *"When Does Orchestration Help?"* (v1). Same task, dataset, and infrastructure; new independent variable.

**Status: Core experiment complete.** llama3.2:3b, 5 trials, both variants, pbmc68k_reduced. Results below replace the pre-registered predictions in Section 6 with actual outcomes.

---

# 1. Core Research Question

In the original paper, I decided the reconciliation rule — arbitration, or confidence-margin comparison. The model never chose its own role in the pipeline.

This follow-up flips that: the LLM is given a routing decision to make itself, and I study the basis on which it makes it — not whether the final annotation is correct, but whether the model's choice of "who to trust" tracks anything real.

**RQ1:** When given the option to defer to a classical baseline or answer itself, on what basis does a small local LLM choose — and does that basis correlate with actual correctness?

**RQ2:** Does self-routing behavior degrade the same way arbitration did for the 1B model in the original paper (§5.3) — i.e., does a weak model produce a degenerate, uninformative routing pattern rather than a genuinely discriminating one?

**RQ3:** Does self-reported routing confidence carry the same miscalibration problem found in §5.4 of the original paper, or is it a distinct failure mode?

---

# 2. What Stayed the Same (reused from v1)

- Dataset: pbmc68k_reduced (Scanpy), FACS-sorted ground truth, 10 cell types, 700 cells.
- Preprocessing/clustering: identical pipeline (QC → normalization → log-transform → PCA → Leiden, resolution 0.6).
- Classical specialist: Scanpy score_genes, unchanged, now also returning a confidence margin.
- Model: llama3.2:3b (primary; 1B and qwen2.5:1.5b not yet run for this study — see Future Work).
- 5 trials, clustering fixed, LLM sampling varied.

---

# 3. The Self-Router Condition (as built)

## 3.1 Prompt design

One call per trial. The LLM receives cluster marker genes and returns, per cluster: a predicted label, a routing decision ("self" or "defer"), a one-sentence stated reason, and a 0–100 confidence score.

**Validity gate**: if the model routes to "self" but its own label isn't a genuine candidate label, the routing choice is forced to "defer" regardless of stated confidence — same principle as v1's evaluator fix. This fired correctly in real runs (e.g. blind trial 3: a 97%-confidence invalid label "Fake Type" was overridden to defer).

## 3.2 Two variants run

| Variant | What the model sees | Result summary |
|---|---|---|
| Blind | Only its own marker-gene input; no classical output visible | Real discrimination failure — net harmful |
| Informed | Its own label + classical's label (not marked correct) | Routing mechanically inert — zero discordant cases |

---

# 4. RESULTS (complete: all 3 models)

**Important correction during this study**: an initial parser bug caused
llama3.2:1b's responses to be almost entirely misread as PARSE_ERROR (the
model produces content-correct but structurally invalid outer JSON —
unclosed braces, or each cluster wrapped in its own stray extra braces
instead of being keys inside one object). This initially looked like a
"degenerate router always defers" finding, matching the naive prediction
from v1's arbitration study — but it was a parsing artifact, not real
model behavior. Fixed with a regex-based per-cluster fallback parser
(tries strict JSON first, falls back to scanning for each
`"<cluster_id>": {...}` block independently if strict parsing fails or is
incomplete), verified against the exact malformed strings that caused the
original failure. **This is itself a citable finding**: weaker models
don't necessarily route worse, they may simply format worse, and any
LLM-agent evaluation pipeline needs a parser robust to this before
drawing conclusions about "model behavior."

## 4.1 Blind self-routing — all three models

| Model | Acc(self) | Acc(defer) | Actual | Always-defer | Delta_route | Self-rate | Discordant |
|---|---|---|---|---|---|---|---|
| llama3.2:3b | 0.176 | 0.565 | 0.400 | 0.625 | +0.088 | 42.5% | 57.5% |
| llama3.2:1b | 0.125 | 0.625 | 0.425 | 0.625 | +0.632 (n=2, noisy) | 40.0% | 57.5% |
| qwen2.5:1.5b | 0.200 | 0.700 | 0.450 | 0.625 | +0.196 | 50.0% | 57.5% |

**Universal pattern across all three models**: Delta_route is positive
for every model (weak genuine self-awareness signal exists), but **every
single model still substantially underperforms simply always deferring
to classical** (0.400–0.450 actual vs. 0.625 always-defer). The
confidence–correctness correlation is negative for all three models
(−0.139, −0.305, −0.323) — self-reported confidence should not be
trusted as a proxy for correctness, regardless of model size or family.

**Interpretation**: models have a small amount of genuine signal about
their own reliability, but self-route far too often (40–50% of the time)
relative to how rarely they're actually right when they do (12.5–20%
accuracy when self-routed) — the discrimination exists but isn't strong
enough to overcome a high base error rate on self-generated answers.

## 4.2 Informed self-routing — all three models

| Model | Acc(self) | Acc(defer) | Actual | Always-defer | Delta_route | Self-rate | Discordant |
|---|---|---|---|---|---|---|---|
| llama3.2:3b | 0.556 | 0.682 | 0.625 | 0.625 | −0.133 (inverted) | 45.0% | **0.0%** |
| llama3.2:1b | 0.647 | 0.609 | 0.625 | 0.625 | +0.250 | 42.5% | 12.5% |
| qwen2.5:1.5b | 0.577 | 0.500 | 0.550 | 0.625 | +0.135 | 65.0% | 15.0% |

**The largest model (3b) shows complete anchoring collapse — routing
never once changed the outcome (0/40 discordant), and its discrimination
is actually inverted.** Both smaller models show real, if modest,
independent judgment: discordant cases exist (12.5%, 15.0%) and
Delta_route is positive for both. However, only llama3.2:1b's informed
routing actually beats its own prevalence-matched baseline (+0.053);
qwen2.5:1.5b does not (−0.010), despite positive discrimination — because
it self-routes very frequently (65%) while only recovering 20% of
available oracle headroom, i.e. it's confidently wrong often enough to
erase the benefit of the cases it gets right.

**This is a genuinely counterintuitive, non-obvious finding**: showing
the model a reference answer causes the *largest* model tested to anchor
on it completely, while the two *smaller* models retain more independent
judgment. This is the opposite of what model-capability scaling alone
would predict, and is worth its own discussion in the writeup — larger
models may be more susceptible to anchoring on a shown "second opinion,"
not less.

## 4.3 Summary across both variants and all models

| | Blind | Informed |
|---|---|---|
| Universal finding | Weak genuine self-awareness (Delta_route > 0 for all 3), but net harmful vs. always-defer for all 3 | Model-dependent: 3b anchors completely (0% discordant), smaller models retain real judgment |
| Confidence calibration | Negative correlation for all 3 models — self-reported confidence is not trustworthy | Not the primary lens here — routing frequency vs. discrimination strength is |
| Consistent across models? | Yes — same qualitative pattern, all 3 | No — 3b is qualitatively different from 1b/qwen2.5 |


---

# 5. Updated Hypothesis Table (was Section 6, "Predicted Outcomes")

| Hypothesis | Predicted confirm/refute | Actual outcome |
|---|---|---|
| H1: Small models can't self-assess reliably | Self-chosen accuracy ≈ defer-chosen accuracy | **Confirmed for blind, all 3 models** — self-chosen accuracy (0.125–0.200) far below defer-chosen (0.565–0.700) universally. **Model-dependent for informed** — 3b shows complete inertness (0/40 discordant), but 1b and qwen2.5 retain measurable independent judgment |
| H2: 1B model routes degenerately | Near-zero variance in routing choice | **Refuted, once the parser bug was fixed.** Initial data appeared to confirm this but was an artifact of malformed JSON being silently defaulted to "defer." After fixing the parser, llama3.2:1b shows self-rates of 40.0% (blind) and 42.5% (informed) — genuinely varied, not degenerate. **The real finding is the opposite of predicted**: the smallest model was NOT the most degenerate router; if anything, the *largest* model (3b) showed the most degenerate behavior in the informed variant (complete anchoring) |
| H3: Routing confidence is miscalibrated like label confidence | No monotonic relationship between confidence and routing correctness | **Confirmed for blind, all 3 models** (correlations −0.139, −0.305, −0.323 — consistently negative). **Mixed for informed** — routing frequency and discrimination strength matter more than confidence calibration specifically in this variant |

---

# 6. Remaining / Future Work

- **Qualitative hand-coding (§5.4 of original design)**: still needed to properly characterize the "other" category reasons across all 3 models — the automated heuristic is a starting point only.
- **Anchoring mechanism for informed 3b**: current data cannot fully distinguish "3b specifically anchors on shown labels" from "3b's independent judgment happens to coincide with classical's on this dataset" — the cross-model contrast (1b and qwen2.5 both show real discordance, 3b shows none) makes the anchoring explanation more plausible than before, but a targeted follow-up (e.g. deliberately showing an INCORRECT classical label and seeing whether 3b still follows it) would be a clean, cheap way to test this directly if pursued further.
- **Parser robustness note for methods section**: the JSON-parsing lesson (structurally invalid but content-correct responses from weaker models) is now a citable methodological point in its own right, alongside the two bugs from v1 (label-vocabulary mismatch, invalid-option arbitration).

---

# 7. Why This Is a Distinct Paper, Not Just an Extra Table

- v1 studies: given a fixed reconciliation rule, how well does the system perform?
- This studies: can the system's own component be trusted to pick the reconciliation rule? A question about model self-knowledge, not orchestration architecture.
- It directly extends v1's miscalibration finding (§5.4: is stated confidence about a *label* reliable) to a meta-level (is stated confidence about the model's own *reliability* reliable) — and finds the same problem shows up in two structurally different ways depending on what information the model has access to.

---

# 8. Reuse Checklist from v1 Codebase (confirmed working)

- Preprocessing/clustering script — reused as-is. ✅
- Classical score_genes specialist — reused, extended with confidence margin. ✅
- Validity-gate logic — reused, confirmed firing correctly in real runs. ✅
- Per-cluster analysis logging — new (`self_routing_percluster_log.csv`), tested and working. ✅
- New code built: `self_routing.py` (prompts, parser, gate), `run_self_routing.py` (CLI), `analyze_self_routing.py` (5.1/5.1b/5.2/5.3/5.4 analyses). ✅
