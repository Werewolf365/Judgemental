# T2 judging module (implemented — see JUDGING.md).

Layout follows the repo's module shape:

- routes.py — organizer/admin management (rubric, roster, config, results, CSV)
- judge.py — judge-only scoring endpoints (peer-isolated)
- results.py — final calculation pipeline, run history, CSV export
- service.py — derived judging stage, weight resolution, rubric locking
- assign.py — balanced assignment service
- pairwise.py — within-judge preference generation (pure)
- reliability.py — cross-event reliability priors (pure query)
- crowd_bt.py — hierarchical Crowd-BT MAP fit (pure math)
- schemas.py — request validation
- tests/ — DB-free unit tests (pairwise evidence, model fit)
