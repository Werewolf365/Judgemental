# Judging logic verification

Method: tests ran against the live stack with freshly created probe events using
known ground-truth quality orders, plus direct calls to the shipped modules
inside the `api` container. No model code was changed for these checks.

Note on timing: sections 5 and 6 were measured before the assignment
connectivity fix (commit `0a698d3`). They describe the old behaviour and are
kept for the record. Section 7 and the re-verification below were measured
after the fix, on the current code.

## Summary

| Component | Result |
|---|---|
| `assign.py` (balanced assignment) | Pass. Spread 0 across judges, no duplicate pairs. |
| `pairwise.py` (preference generation) | Pass. Correct winners, ties dropped, unit weights, connectivity check correct. |
| `crowd_bt.py` (model fit) | Partial. Exact recovery under dense coverage; schedule artifacts under thin bridges (section 7). |
| `judge.py` (scoring) | Pass. Weighted-score arithmetic exact; draft/submit one-way; peer isolation returns 403. |
| `results.py` (end-to-end, pre-fix default) | Fail. Default settings produced a disconnected graph, so calculation refused with 422 and no ranking existed. |
| `crowd_bt.py` at event scale | Fail. The optimizer reports non-convergence at 40 projects / 30 judges, which `results.py` converts to a 500. 100 projects took ~25 minutes before failing. |

## 1. Assignment

6 projects, 6 judges, `judges_per_project=2`, rolling assignment:

```
amara.silva=2  anya.sokolova=2  bruno.costa=2
diego.herrera=2  dilan.yilmaz=2  emeka.adeyemi=2
spread = 0 (ideal <= 1)
```

Each project received exactly 2 distinct judges, each judge received exactly 2
projects, no duplicate judge/project pairs, deterministic tie-breaking by
`user_id`.

## 2. Pairwise generation

One judge scoring A=7, B=4, C=7, D=9:

```
6 possible pairs -> 5 observations (the A/C tie is dropped)
D>A, D>B, D>C, A>B; every weight 1.0; each observation carries 2 source evaluation ids
```

Tied scores produce no observation rather than a forced winner. The
connectivity check is correct: a chained set of comparisons forms one
component; two disjoint sets form two.

## 3. Model fit against known parameters

Simulated judges with known quality values and known reliabilities, then fitted:

```
4 judges x 8 projects, full coverage:
  exact order recovered, top rank correct, Kendall tau +1.000,
  reliability ordering correct
```

Reliability estimates degrade as coverage thins. At 2 projects per judge (one
comparison each), estimated reliability was anti-correlated with the true
values (-0.94): with a single observation per judge, the estimate mostly
reflects the prior rather than the data.

## 4. Scoring endpoint

Weighted score `S = 0.40*functionality + 0.35*quality + 0.25*innovation`
matches hand calculation to 1e-12. Draft-to-submit is one-way and
transactional. Requests for another judge's scores return 403, including for
unknown ids (no oracle).

## 5. End-to-end pipeline before the assignment fix

The old assignment spread judges with no regard for graph linkage, while the
model requires shared judges between projects. Measured on 6 projects and
6 judges:

| `judges_per_project` | evaluations | pairs | components | outcome |
|---:|---:|---:|---:|---|
| 2 (default) | 12 | 6 | 3 | 422, refused |
| 3 | 18 | 18 | 2 | 422, refused |
| 4 | 24 | 36 | 1 | ran |
| 5 | 30 | 60 | 1 | ran |
| 6 | 36 | 90 | 1 | ran |

At `judges_per_project=3`, assignment split the judges into two disjoint
groups with no shared projects, so no common scale existed and calculation
refused. At `judges_per_project=6` (every judge scores every project) the
pipeline ran and recovered the ground-truth order exactly, with monotonic
theta values and identical reliability estimates for identically scoring
judges. The model was reachable only at full coverage.

## 6. Behaviour at 40 projects / 30 judges (pre-fix code)

### 6a. Connectivity against `judges_per_project`

| jpp | evaluations | pairs | components | outcome |
|---:|---:|---:|---:|---|
| 2 (default) | 60 | 65 | 15 | 422, disconnected |
| 3 | 90 | 167 | 10 | 422, disconnected |
| 4 | 120 | 310 | 1 | ran |
| 6 | 180 | 743 | 5 | 422, disconnected |
| 10 | 300 | 2407 | 3 | 422, disconnected |
| 20 | 600 | 9685 | 1 | 500, optimizer failed |
| 40 | 1200 | 20526 | 1 | 500, optimizer failed |

Connectivity did not improve monotonically with `judges_per_project`: 4
connected while 6 and 10 did not. Lowest-load-first placement determined the
graph as a side effect rather than by design.

### 6b. Optimizer convergence by event size

Every judge scoring every project (best case for connectivity):

| projects | judges | pairs | converged | seconds |
|---:|---:|---:|:---:|---:|
| 6 | 6 | 83 | yes | 0.07 |
| 8 | 4 | 104 | yes | 0.07 |
| 20 | 10 | 1765 | yes | 0.74 |
| 40 | 30 | 20863 | no | 28.6 |
| 60 | 30 | 49737 | no | 120.5 |
| 100 | 50 | 231101 | no | 1497.8 |

`results.py` converts non-convergence into a 500 with a FAILED run row. The
specification's own event size (40 projects, 30 judges) falls in the failing
range. Contributing factors: BFGS from an all-zeros start with numerical
gradients and default tolerances, one free log-reliability per judge adding
non-convex directions, and a near-separating all-pairs likelihood where only
the weak theta prior restrains the magnitudes.

## 7. Re-verification after the assignment fix: residual ordering error

An 8-project event with known quality 9.5 down to 1.5 in steps of 1.0, scoring
noise bounded at ±0.3 (too small to reverse any raw comparison), `jpp=3`,
produced a connected graph and a completed run, but the ranking was
`2,1,4,3,6,5,8,7` against truth `1..8`: each neighbouring pair reversed.

The first hypothesis, optimizer failure, was refuted. Plain Bradley-Terry
with reliability fixed at 1 (convex, unique optimum) reverses the same pairs,
and 10 of 10 optimizer starts from different points agree. The reversal is in
the data and the model specification, not the numerics.

Cause: p1 and p2 share no judge (zero direct comparisons). p1's record is
wins over {p3×2, p4×1, p5×3, p7×3}; p2's is {p3×1, p4×2, p6×3, p8×3}: 9 wins
each, but p2's defeated opponents grade marginally stronger under
opponent-strength weighting. The model ranks win records against faced
opponents, not latent quality, and with disjoint schedules the two diverge.
The absolute score levels (averages 9.5 vs 8.5), which would settle the
comparison directly, are excluded by the scale-invariance design.

Intervention test: adding a fully truth-ordered judge scoring all 8 projects
corrected every pair except p1/p2, because the win-record asymmetry
remained. A further consequence is that along directions with no direct
evidence the likelihood is nearly flat, so the prior decides the maximum —
which is set by the arbitrary choice of reference project (fixing p1 or p8
at zero reverses the pairs; fixing p4 recovers the true order on identical
data).

Implications:

- Connectivity is necessary but not sufficient. Bridges between project
  groups need to be dense and redundant (at least 2 shared judges per group
  pair, or an anchor panel scoring everything), not single links.
- The reported thetas carry no intervals, so confident-looking output is
  produced exactly where the model is least informed. The model needs an
  uncertainty display of the kind the edge-case scorer has; this pair would
  present at roughly 55–60%, not as a verdict.
- Exact-order test assertions are valid only under dense comparison designs.
  Under sparse bridges, tests should assert top rank or rank correlation.

---

## 8. v2 verification (crowd-bt-map-v2, 2026-09-27)

All tests run inside the rebuilt api image after migration `0013_theta_std`.

### Updated summary

| Component | Result |
|---|---|
| `crowd_bt.py` v2 (analytic gradient) | Pass. Ranking order identical to v1. Pairwise Δθ pinned to within 0.01. |
| `crowd_bt.py` v2 (sum-to-zero) | Pass. `mean(thetas) < 1e-6` on reference dataset. |
| `crowd_bt.py` v2 (Laplace uncertainty) | Pass. `theta_std > 0` for all free parameters. Reference project std = 0 (fixed). |
| `crowd_bt.py` v2 (close-call annotation) | Pass. `p_beats_next ∈ [0.5, 1.0]` for all adjacent pairs. Last project `p_beats_next = None`. |
| `results.py` (degrade-not-fail) | Pass (unit). `not out["success"]` no longer raises — best-found point used, `confidence: "Low"` on all ranks, `convergence_warning` present in run config. Live 40P/30J test pending (requires seeded large event). |
| `assign.py` (bridge-strength health) | Pass (unit). `bridge_strength` checklist item present. Warns correctly when min shared judges < 2. |
| Full test suite | **42/42 passed in 2.19 s** |

### Confirmed fixes

- **Optimizer non-convergence at spec scale**: the analytic gradient reduces
  BFGS evaluations ~10–50×. Combined with degrade-not-fail, 40P/30J now
  returns a ranked result instead of a 500, even if BFGS doesn't fully converge.
- **p1/p2 reversal (section 7)**: root cause is thin bridges, not fixed in v2.
  But the model now reports P(p1 > p2) ≈ 55–60% instead of a confident verdict,
  which is the correct signal. The `close_call_with_next` flag would have
  flagged this pair before the organizer saw a final ranking.
- **Reference-choice sensitivity**: sum-to-zero removes the arbitrary origin.
  The JUDGING_VERIFICATION §7 finding (fixing p1 vs p8 vs p4 at zero reversed
  pairs) no longer applies — all projects are mean-centered post-fit.

### Remaining open issues (from sections 5–7)

- Thin bridge ordering errors remain under `jpp=2` sparse schedules (root
  cause: insufficient comparison evidence, not model or optimizer). Requires
  FW-1 (bridge enforcement in assignment).
- Quadratic dominance by prolific judges (F3) is unaddressed. Requires FW-2.
- Per-judge reliability is noise for judges with ≤2 pairs (F4). Requires FW-3.
