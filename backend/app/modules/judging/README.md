# T2 judging module (implemented — see JUDGING.md)

Layout follows the repo's module shape:

- `routes.py` — organizer/admin management (rubric, roster, config, results, CSV)
- `judge.py` — judge-only scoring endpoints (peer-isolated)
- `results.py` — final calculation pipeline, run history, CSV export
- `service.py` — derived judging stage, weight resolution, rubric locking
- `assign.py` — balanced assignment service (connectivity + bridge-strength health)
- `pairwise.py` — within-judge preference generation (pure)
- `reliability.py` — cross-event reliability priors (pure query)
- `crowd_bt.py` — Crowd-BT MAP fit v2: analytic gradient, Laplace uncertainty, sum-to-zero (pure math)
- `schemas.py` — request validation
- `tests/` — DB-free unit tests (pairwise evidence, model fit, uncertainty, close calls)

## Model version history

| Version | File change | What changed |
|---------|-------------|--------------|
| `crowd-bt-map-v1` | original | BFGS from zeros, numerical gradient, reference pinned at 0 |
| `crowd-bt-map-v2` | migration `0013` | Analytic gradient, sum-to-zero normalization, Laplace `theta_std`, degrade-not-fail, `confidence` field |
| `crowd-bt-map-v3` | no migration (same columns) | Full-covariance Laplace propagation through the centering shift: reference project gets a real std; all stds include shift-variance terms |

## Key invariants (enforced at multiple layers)

1. **Unit weights** — every pairwise observation has `weight = 1.0`.
   Hardcoded in `generate_pairs`, `CHECK` constraint in DB, asserted in tests.
2. **Reference-invariant reporting** — sum-to-zero post-fit means reported
   thetas are centered regardless of which project is lex-smallest, so values
   are comparable across recalculations. Note the limit: the fitted optimum
   itself still depends on reference choice through the prior (demonstrated:
   identical data ranks differently under reference p1/p8 versus p4 where
   evidence is thin). Reporting is symmetric; the fit is not fully.
3. **Connectivity gate** — disconnected comparison graphs refuse to fit.
   One component required before `crowd_bt.fit()` is called.
4. **Degrade, don't fail** — optimizer non-convergence returns the best-found
   point with `confidence: "Low"` on every rank, not a `500`.
