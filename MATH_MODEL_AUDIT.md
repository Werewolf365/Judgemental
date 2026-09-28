# Judging Mathematical Model — Audit Report (read-only, no code changed)

Scope: `crowd_bt_architecture_poc_corrected.md` (math reference) vs implementation
`backend/app/modules/judging/{pairwise.py, crowd_bt.py, reliability.py, service.py, results.py, judge.py}`,
tests `test_pairwise.py` / `test_crowd_bt.py`, migration `0008_judging`.
Date: 2026-09-26. No model code was modified for this audit.

## 1. What it claims to implement

Pipeline (prompt_T2 §9–§14, JUDGING.md):

```text
S_ij = Σ_k w_k · score_ijk   (judge-local weighted score, normalized organizer weights)
  → within-judge all-pairs ordering, ties skipped, weight = 1
  → P_j(A>B) = sigmoid(r_j·(θ_A − θ_B)), r_j = exp(log r_j) > 0
  → log r_j ~ Normal(μ_j, σ_j²)  [neutral (0, 0.60) or historical posterior mean]
  → θ_i ~ Normal(0, 2²), one θ fixed at 0 (identifiability)
  → MAP via BFGS from zeros → θ ranking + r diagnostics
```

Headline invariant (correctly stated everywhere): **raw score margins never become
evidence weights**. This is the §6 correction (`w = 1 + |Δ|` deleted), and the repo
enforces it in three layers: `pairwise.generate_pairs` hardcodes `1.0`,
`pairwise_observations` has `CHECK (weight = 1)`, tests assert it.

## 2. Does the model "work"?

Yes, narrowly: it converges, is deterministic, and reproduces the doc's
**evidence table (13 rows, §14) and both orderings** (projects, judges) exactly.
The implementation team's own finding (context.md §25, test file header) is
confirmed by inspection: **the doc's §15/§16 magnitudes (≈ +1.042, r ≈ 1.716)
do NOT come from the corrected model** — they reproduce only under the removed
`w = 1 + |margin|` weighting, and the doc's Appendix A cannot run as printed
(wrong keys `project_id`/`judge_id`/`score`/`name` vs real `project`/`judge`/
`criteria`/`title`). So: ordering signal works, printed magnitudes are stale
reference values and must not be used as regression targets. The tests correctly
pin their own optimum instead.

What "works" does NOT mean: unbiased, calibrated, uncertainty-quantified, or
strategy-proof. See §4–§6.

## 3. Why these choices (defensible parts)

| Choice | Logic | Verdict |
|---|---|---|
| Pairwise conversion | Removes additive judge strictness/leniency offsets; strict 5v3 and lenient 85v70 give same direction | Sound, standard |
| Unit weights | Prevents wide-scale judges dominating purely via larger margins | Sound, correctly enforced |
| BT with reliability multiplier `sigmoid(r·Δ)` | `r→0` = random judge, `r` large = decisive; positivity via `exp` | One valid Crowd-BT variant (see flaw F2/F6) |
| Reference θ=0 | Fixes BT translation ambiguity (all θ + c identical likelihood) | Necessary but **insufficient** (flaw F1) |
| Connectivity refusal | Disconnected graphs have no common scale; refusing beats hallucinating ranks | Correct, well implemented |
| Snapshot `weighted_score` at submit | Later rubric edits can't reinterpret history | Correct |
| Tie epsilon 1e-9 | 0.35/0.40 weights aren't binary-exact; avoids crowning winners on float dust | Reasonable |
| Same-event exclusion in history | Recalculation can't feed on its own output | Correct |

## 4. Logic flaws (load-bearing)

**F1 — Scale non-identifiability (serious).** Fixing one θ=0 fixes *translation*
but the model has a second degeneracy: `θ → k·θ, r → r/k` leaves every
`r·Δ` invariant. Only the two weak priors (σ_θ=2, σ_r=0.60) anchor scale.
Under sparse data the MAP rides a ridge; thetas and reliabilities trade off
against each other and both magnitudes are prior-driven. Fix requires a scale
constraint or informative/estimated scale (see §7).

**F2 — Reliability = agreement with consensus (herding).** `r_j` is estimated
from fit to the *same* consensus thetas it weights. A consistent minority judge
who disagrees with the majority gets shrunk as "unreliable"; a correlated
majority bloc reinforces itself. There is no external ground truth, no
spam/collusion/outlier model (cf. Raykar flip-noise, Welinder-D Perona, or
robust BT). Adversarial implication: a 2–3 judge bloc outvotes an honest
singleton and the model certifies it via higher `r`.

**F3 — Quadratic dominance / transitive double-counting.** All-pairs generation
means a judge scoring `n` projects contributes `n(n−1)/2` observations. In the
POC itself `jdg_26` (4 projects → 6 pairs) is 46% of all evidence; a judge
scoring 10 projects would contribute 45× a judge scoring 2. Worse, pairs are
treated as independent when they are logically redundant (A>B, B>C ⟹ A>C
counted 3×). Effective sample size is inflated, posteriors overconfident.
Standard fixes: rank-likelihood / Plackett-Luce, adjacent-in-rank pairs, or
explicit `(2/n)`-style weighting — each with tradeoffs, all better documented
than silent all-pairs.

**F4 — Single-observation reliabilities are fiction.** `jdg_22`, `jdg_24`
(1 pair each) get MAP `r ≈ 1.10/1.09` reported to 6 decimals. With one bit of
data the posterior is ~prior; presenting per-judge `r` without uncertainty or
shrinkage invites over-reading. Needs partial pooling or minimum-evidence
suppression.

**F5 — MAP-only, no uncertainty, yet ranks presented as definitive.**
`posterior_sigma` is stored NULL (honestly noted). Consequence: tied/near-tied
thetas (e.g. the verified all-zero contradictory-evidence case) still render as
ranked list; organizers cannot distinguish "decisive win" from "coin flip".
Competition-"1224" rank sharing with `abs_tol=1e-9` is a numerical tie rule,
not a statistical one.

**F6 — Strictness only partially removed.** Pairwise differencing removes
*additive* offsets, not *multiplicative* scale use (a judge using only 8–9 vs
0–10 has compressed within-judge gaps → more near-ties dropped) nor
criterion-level scale effects (linear `Σw·score` assumes interval scale,
no per-criterion standardization, variance differences implicitly reweight).

**F7 — History transfer is not hierarchical Bayes.** Only the posterior *mean*
propagates; σ resets to neutral 0.60 always; latest-single-row wins (no
precision weighting, no decay, no cross-judge pooling). A judge with 1 past
observation and one with 500 get identical prior strength. Worse,
cross-event transfer assumes `r` is on a common scale, but per-event θ-scales
are arbitrary (F1) plus reference = lex-smallest project (data-dependent
origin), so `r` magnitudes are not comparable across events.

**F8 — Discarded ties = discarded similarity evidence.** Skipping ties is
defensible vs forcing winners, but ties carry "these are equal" signal.
BT tie extensions (Rao–Kupper, Davidson) exist; silent dropping biases toward
judges/tasks that avoid ties.

**F9 — Optimizer fragility.** Single BFGS run from zeros, numerical gradients,
no multi-start in production (tests verified uniqueness offline on one
dataset only), no stored diagnostics beyond `success` bool, no iteration/
gradient-norm tolerances in config. Crowd-BT with free `r` is non-convex;
separable/unanimous data pushes thetas toward ±∞ with only the weak prior as
brake. Failure path truncates error to 500 chars with no traceback.

## 5. Pen-test / integrity notes (implementation, not pure math)

1. **Synchronous unbounded fit (DoS).** `POST …/results/calculate` runs BFGS
   in-request, cost ~O(J·K²) pairs with no cap/timeout. Post-first-success,
   recalculation is unlimited (5-min guard covers only RUNNING). Organizer
   (or compromised organizer session) can CPU-spin the API container.
   Recommend async/off-request or at minimum row/pair caps + rate limit.
2. **`fit()` honors any `weight` passed** (`w·log p`) while the invariant lives
   in callers + DB CHECK. A future caller passing ≠1 silently reintroduces the
   deleted scale dependence. `fit()` should `assert` unit weights.
3. **CSV formula injection.** `export_csv` quotes `,"` but doesn't neutralize
   leading `= + - @` in titles/team/track names → Excel/LibreOffice formula
   execution on organizer machines. Prefix-sanitize.
4. **Silent drop of NULL `weighted_score`.** `results.py` filters
   `weighted_score is not None` without counting/logging; a legacy NULL row
   vanishes from evidence. Should hard-error or audit-count.
5. **Concurrent cross-event history race.** Two simultaneous calculations in
   different events for the same judge both read the same prior, both append
   history; ordering undefined. Low severity; needs unique ordering or
   transaction serialization if history matters.
6. **Reference = lex-smallest ID is organizer-visible/predictable.**
   No ranking exploit (translation-invariant), but origin jumps when projects
   are added between recalcs → theta time-series incomparable. Prefer
   sum-to-zero constraint for stability.
7. **Positive findings (keep):** server-side weight snapshot (client can't
   inject totals), stage-gated calculate (409 while OPEN), versioned runs
   (never mutate), peer isolation 403 without oracle, weight CHECK constraint,
   same-event history exclusion. All verified by read.

## 6. Arbitrary / undefended numbers

| Constant | Value | Status |
|---|---|---|
| `THETA_SIGMA = 2.0` | 95% Δθ prior ≈ ±5.6 → p ∈ [0.004, 0.996] | No calibration, no sensitivity run stored |
| `NEUTRAL (μ=0, σ=0.60)` | 95% prior r ∈ [0.31, 3.25] | POC inheritance, no empirical Bayes |
| `TIE_EPSILON = 1e-9`, rank `abs_tol=1e-9` | Numerical tie rule | Reasonable but conflated with "statistical tie" in UI |
| All-pairs + weight 1 | Evidence multiplicity | Arbitrary multiplicity (F3); unit value right, count wrong |
| Lex-smallest reference | Origin choice | Arbitrary; sum-zero strictly more stable |
| BFGS-from-zeros, default tolerances | Optimizer config | Arbitrary; no multi-start/diagnostics |

None is fatal alone; jointly (F1+F4+F7) they mean **reported magnitudes
(θ to 6 decimals, r to 6 decimals) vastly overstate epistemic precision**.

## 7. Suggested replacements (no code changed; ranked)

1. **Fix scale identification:** add sum-to-zero (`Σθ = 0`) or fix θ variance
   (e.g. σ_θ = 1 anchored) instead of / in addition to single-point fixing;
   report only *differences/contrasts*, never raw θ.
2. **Replace all-pairs-independent likelihood** with Plackett–Luce rank
   likelihood (one observation per judge ranking) or adjacent-pair breaking;
   if keeping all-pairs, weight judge contribution by `2/n_j` or use
   cluster-robust SEs and say so.
3. **Real hierarchical reliability:** partial pooling
   `log r_j ~ Normal(μ_pop, τ²)` with estimated `μ_pop, τ`; propagate
   precision-weighted history (inverse-variance, time-decayed), not
   latest-mean-only. Suppress or pool judges with <3–5 pairs.
4. **Uncertainty by default:** Laplace approximation around the MAP (cheap:
   inverse Hessian from BFGS) or short MCMC/VI; show 95% intervals on θ and
   P(A>B); mark ranks with overlapping intervals as "statistical ties".
5. **Tie model:** Davidson / Rao–Kupper tie parameter instead of dropping;
   at minimum report tie rate per judge as a diagnostic.
6. **Robust / collusion-aware likelihood:** mixture flip-noise
   (`P = (1−ε_j)·σ(rΔ) + ε_j/2`) or heavy-tail / outlier downweighting so a
   minority judge isn't shrunk purely for disagreeing; add judge-pair
   agreement diagnostics to detect blocs.
7. **Calibrate priors, don't inherit them:** empirical-Bayes or
   cross-validated grid over (σ_θ, σ_r); store chosen values + sensitivity
   (held-out pair prediction accuracy) in `model_runs.config`.
8. **Optimizer hardening:** multi-start (≥5) + keep best NLP, store
   `success/nit/njev/grad_norm`, assert unit weights inside `fit()`,
   cap pairs / move fit off-request.
9. **Export hygiene:** CSV formula-prefix sanitization; audit-count dropped
   NULL snapshots; include per-pair `weight` (=1) + evidence counts per judge
   in results payload so dominance (F3) is visible.

## 8. Bottom line

The core correction the architecture demanded — unit-weighted pairwise
evidence with reliability separated from scale — **is implemented and enforced
correctly**. The ranking *order* on the reference subset is reproduced. But the
numbers around it (magnitudes, per-judge reliabilities, history transfer,
printed doc values) rest on unidentified scale, quadratic vote-stuffing by
prolific judges, MAP-only certainty, and mean-only history. Treat current
output as a **reasonable ordinal heuristic**, not a calibrated Bayesian
measurement. Adopting §7 items 1–4 would promote it to the latter.

---

## 9. v2 update — what changed (crowd-bt-map-v2, migration 0013)

Date: 2026-09-27. Code changed: `crowd_bt.py` (complete rewrite),
`results.py`, `assign.py`, `models.py`, migration `0013_theta_std`.
42/42 tests pass.

### Flaws addressed

| Flaw | Was | Now |
|------|-----|-----|
| **F1 (scale non-identifiability)** | Partially: only translation fixed (reference=0) | **Improved**: sum-to-zero constraint applied post-fit. Mean of all θ (including reference) subtracted before returning. Thetas are now symmetric and recalc-stable. The θ→kθ, r→r/k ridge remains (weak priors only), but origin is no longer arbitrary. |
| **F5 (MAP-only, no uncertainty)** | `posterior_sigma` NULL, ranks presented as definitive | **Fixed**: Laplace approximation via `res.hess_inv` diagonal. `theta_std` per project stored in `model_project_results`. `rank()` computes `P(A>B) = σ(Δθ/√(σ²_A+σ²_B))`. Adjacent pairs with P < 90% flagged `confidence: "Low"` and `close_call_with_next: true`. |
| **F9 (optimizer fragility — convergence)** | `not out["success"]` → `RuntimeError` → 500, FAILED run | **Fixed**: best-found BFGS point used on non-convergence. `confidence: "Low"` on every rank. `convergence_warning` + `optimizer_diagnostics` (nit, njev, grad_norm) stored in `run.config`. Run status stays SUCCEEDED. |
| **F9 (optimizer fragility — gradient)** | Numerical finite-difference gradient (slow, ~O(n) extra evaluations per step) | **Fixed**: analytic gradient supplied via `jac=grad_only`. ~10–50× fewer function evaluations at competition scale. 40P/30J now tractable. |

### Flaws still open

| Flaw | Status | See |
|------|--------|-----|
| **F1 (θ→kθ scale ridge)** | Open — weak priors still the only anchor | FW-1 in JUDGING.md |
| **F2 (reliability herding)** | Open | FW-3 |
| **F3 (quadratic dominance)** | Open | FW-2 |
| **F4 (single-obs reliability)** | Open — minimum-evidence suppression not yet added | FW-3 |
| **F6 (multiplicative strictness)** | Open | — |
| **F7 (mean-only history)** | Open | FW-5 |
| **F8 (tie model)** | Open | FW-6 |
| **F9 (multi-start)** | Open | FW-4 |

### New health signal

`assignment_health` now includes a `bridge_strength` checklist item that
counts shared judges for every directly-connected project pair. Warns when any
pair shares only 1 judge (single-judge bridges → near-flat likelihood direction).
This is a read-only diagnostic; enforcement in assignment is FW-1.

### Remaining audit notes still valid

All pen-test items (§5) remain: synchronous DoS, unit-weight assertion inside
`fit()`, CSV formula injection, NULL score silent drop, concurrent history race.
Priority: medium (CSV injection is the most organizer-visible).

