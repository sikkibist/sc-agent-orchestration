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
*(not yet run)*

---

## Orchestrated system (specialists + evaluator)
*(not yet run)*

---

## Orchestrated system, small model variant
*(not yet run)*
