# JUDGING (T2 — implemented)

Competition judging runs end to end: organizer-defined weighted rubrics,
judge rosters, balanced assignment (rolling or batch), deadline-gated
scoring, and a final ranking from a hierarchical Bayesian Crowd-Bradley–Terry
model. The math reference is `crowd_bt_architecture_poc_corrected.md`; the
workflow spec is `prompt_T2.md`. What follows is how this repo implements
them, not a restatement of the equations.

## Pipeline

```text
Rubric (organizer weights)
  → Judge roster + balanced assignment (connectivity + bridge-strength checked)
  → Scores within the judging window (S_ij = Σ w_k × score_ijk, judge-local)
  → Within-judge pairwise preferences, unit-weighted, ties skipped
  → Hierarchical Bayesian Crowd-BT MAP (v2):
      - Analytic gradient (fast BFGS convergence at scale)
      - Sum-to-zero normalized project strengths θ
      - Laplace uncertainty: θ_std per project from inverse-Hessian diagonal
      - Close-call annotation: P(A>B), confidence High/Low per rank
  → Ranked results + versioned model runs + CSV export
```

Edge case (one judge per project, no pairs possible): the BT calculation
refuses and points at the Bayesian scorer instead (`POST
/events/{id}/bayes/calculate`), which reports scores with uncertainty rather
than point estimates. See "Edge-case model" below.

The one invariant everything else serves: **raw score margins never become
evidence weights.** Every non-tied comparison enters the model with weight 1
(enforced in `pairwise.py`, in a DB `CHECK` constraint, and by test). Judge
reliability — not score range — decides how strongly a preference pattern
counts. Strictness and leniency are offsets the pairwise conversion removes,
not signals about trustworthiness.

## Model version: `crowd-bt-map-v3`

The current fitter in `crowd_bt.py` (migration `0013`) adds three properties
over the original v1:

### Analytic gradient (#8)
BFGS is supplied an exact gradient instead of using finite differences.
The gradient of the negative log-posterior is:

```
∂NLP/∂θ_i  = Σ_{k:win=i} w_k(p_k−1)r_j(k)  −  Σ_{k:los=i} w_k(p_k−1)r_j(k)  +  θ_i/σ_θ²
∂NLP/∂log r_j = Σ_{k:j(k)=j} w_k(p_k−1)z_k  +  (log r_j − μ_j)/σ_j²
```

where `p_k = σ(r_j(k)·(θ_win−θ_los))` and `z_k = r_j(k)·Δθ_k`. This
reduces optimizer evaluations by ~10–50× at competition scale, making 40P/30J
tractable where it previously timed out.

### Sum-to-zero normalization (#3)
After the MAP solve, `mean(all θ_i)` (including the reference at 0) is
subtracted from every θ. The BT likelihood depends only on differences, so
reported rankings are unchanged by the shift. Benefits and limits:
- Thetas are symmetric around 0 regardless of which project is lex-smallest.
- Values are comparable across recalculations (origin is no longer the
  arbitrary lex-smallest project).
- The reference project is no longer pinned at 0 in the output; it ranks
  wherever its quality places it.
- Limit: the shift symmetrizes *reporting* only. The fitted optimum still
  depends on reference choice through the prior — on thin-bridge data,
  identical comparisons rank differently under different references. Do not
  claim the fit itself is reference-invariant.

### Laplace uncertainty (#2)
BFGS already computes an approximate inverse Hessian (`res.hess_inv`).
The fitter takes its full theta-block covariance and propagates it through
the centering shift (`Var(θ′_i) = S_ii + Var(m) − 2·Cov(θ_i, m)` with
`m` the subtracted mean), so every project — reference included — gets an
honest marginal std. A diagonal-only read would miss the shift terms for all
projects and leave the reference at exactly 0, understating every pairwise
probability involving it. The fitter returns `theta_stds: {project_id: float}`
alongside thetas.

`rank()` uses these to annotate every adjacent pair:

```
P(A > B) = σ( (θ_A − θ_B) / √(σ²_A + σ²_B) )
```

Stated assumption: the two strengths are treated as independent Gaussians.
The posterior does not factor that way (shared reference pin and centering
shift induce covariance, which is dropped). Probabilities are therefore a
flagging heuristic, not calibrated odds.

Pairs where `P < 0.90` are flagged `close_call_with_next: true` and the
projects involved receive `confidence: "Low"`. All other ranks get
`confidence: "High"`. The values surface in the API response and in the
`model_project_results` table (`theta_std`, `confidence` columns added in
migration `0013`).

### Degrade-not-fail (#7)
Non-convergence is a degraded result, not a fatal error. If BFGS does not
converge, the best-found point is used, every project receives
`confidence: "Low"`, and `run.config` stores:
- `converged: false`
- `convergence_warning: "<human-readable message>"`
- `optimizer_diagnostics: {nit, njev, message, grad_norm}`

The endpoint returns `200` with a valid ranking instead of a `500`. The
frontend can surface the warning to the organizer.

## Roles

- **Organizer/admin** (event-scoped as usual): rubric CRUD, judge roster,
  judging settings (window, judges per project, rolling on/off), batch
  assignment, final calculation, results, CSV export. On Bayesian-scored
  events additionally: run the scorer, interchange ranks on close calls,
  revert to the model order, and assign extra judging to named pool judges.
- **Judge**: sees only assigned projects; scores each criterion 0–10;
  submits final evaluations; reads only their own scores
  (`GET /judge/scores?judge=<someone-else>` is 403, which is also what the
  acceptance checker probes).
- **Participant**: no judging surface at all.

## Lifecycle (derived, not stored)

`NOT_STARTED → OPEN → CLOSED → RESULTS_READY`, derived from the judging
window plus what exists. No window means "judge whenever". Scoring only in
OPEN; new assignments stop at close (removal refills still preserve earlier
coverage); calculation only after close; recalculation appends a new run
version, never mutates. The rubric locks once judging starts; post-start
removal deactivates instead of deleting.

## Progress view

`GET /events/{id}/judging` carries a `progress` block: overall completion %
(submitted evaluations over live assignments), plus per-judge and
per-project submitted/assigned breakdowns. The console Judges tab renders it
as an overall bar with per-judge and per-project bars — pure counts, no
estimates; judges with no live work read as "no work", not 0%.

## Rubric scales

Each criterion declares the scale judges score against (`score_lo`/`score_hi`, default 0-10, enforced `hi > lo` at write time and by a CHECK constraint). Judge input validates into the declared range per criterion; the submitted weighted snapshot normalizes each score by its own scale first, so mixed-scale rubrics stay comparable. With default scales the snapshot reduces exactly to the old sum-of-products, and all existing snapshots are unaffected. The Bayesian scorer receives the same per-criterion scales. Scales are set in the console rubric builder (blank = 0-10) and exposed in every rubric payload.

## Assignment
Lowest-active-load first, `user_id` tie-break, in-memory load updates per
slot (no stale snapshots), event-row locking plus a partial unique index
with a matching `ON CONFLICT` arbiter for idempotent retries. Rebalance
fills gaps but never steals assigned work.

Later slots **bridge**: they prefer judges serving project-components not yet
represented among the current project's picks. A connectivity repair pass
rewires minimal movable rows until one component exists. Both checks are
structural (shared assignment rows); the pair-evidence connectivity check at
calculate-time is the second gate.

The `GET /events/{id}/assignments/health` checklist now includes
`bridge_strength`: for every pair of directly-connected projects (sharing ≥1
judge) it counts shared judges and warns when any pair shares only 1.
Comparisons across a single-shared pair rest on one judge's verdicts alone,
so the model may misorder those pairs (the truly flat directions are pairs
with no shared judge at all — those stay the connectivity gate's refusal).
Recommendation is to raise `judges_per_project` to ≥3. The batch pass
upgrades single-shared pairs to 2-shared where a coverage-neutral verified
swap exists (reported as `strengthened`, with `min_bridge`/`weak_bridges`
counts); full pairwise redundancy is unachievable at uniform coverage 2
without destroying balance, so the pass takes safe improvements and reports
the rest rather than forcing them.

Manual assignment (`POST /events/{id}/assignments/manual {project_id,
judge_user_id}`) names one eligible roster judge for one submitted project:
the judge must already hold the JUDGE role on an active roster row, duplicate
live pairs are refused, and closed windows are refused (reopen first, as with
batch). It may exceed `judges_per_project`; extra judging is the purpose, not
a coverage fill. Used by the Bayesian close-call workflow to place re-scoring
exactly where uncertainty is highest.

## Auditability

Every model run snapshots its priors, rubric, reference project, convergence
status, optimizer diagnostics, and counts, and stores each pairwise
observation with its source evaluation ids — so the chain
`Final rank → θ ± σ → pairs → weighted scores → rubric scores` is walkable
from the database. Judge posteriors append to a cross-event history table;
the next competition's prior is the latest posterior (mean only — MAP yields
no variance, stated in code rather than faked).

## Results API shape (v2)

`GET /events/{id}/results` ranking entries include:

| Field | Type | Meaning |
|-------|------|---------|
| `theta` | float | Sum-to-zero normalized BT strength |
| `theta_std` | float \| null | Laplace std (null on pre-v2 legacy runs) |
| `confidence` | `"High"` \| `"Low"` \| null | `"Low"` when P(beats adjacent rank) < 90%; null means uncertainty was never computed (pre-0013 legacy rows), not confidence |
| `rank` | int | Competition rank (1224 style) |
| `blended_score` | float \| null | Judge/crowd blend output, null unless the run blended |
| `blended_rank` | int \| null | Competition rank over blended scores, null unless the run blended |

Run envelope includes:

| Field | Type | Meaning |
|-------|------|---------|
| `converged` | bool | Whether BFGS converged |
| `convergence_warning` | str \| null | Human-readable note when not converged |
| `config.optimizer_diagnostics` | obj | `{nit, njev, message, grad_norm}` |
| `config.blend` | obj | `{active, crowd_weight_pct, n_voters, n_ballots}` — `{active: false}` when the run did not blend |

## Judge/crowd final-score blend

Off by default; voting off always means judges alone. When the organizer
enables it (`PATCH /events/{id}/judging` `{crowd_blend_enabled, crowd_weight}`,
weight a 0–100 percent) and crowd ballots exist, calculate appends blended
output without touching the model results: `final = w_judge·N(judge) +
w_voter·N(voter)`, each side min-max normalized to [0, 1] over the ranked set
(scales are otherwise incomparable — thetas vs 0..10 scores vs sqrt
influence). BT blends pre-rank thetas, bayes blends direct scores; unvoted
ranked projects count voter-raw 0; voted-but-unscored projects are excluded.
Ranks are competition 1224. Blend-off runs write NULLs and are identical to
before. See `judging/blend.py` (pure, unit-tested).

## Edge-case model: hierarchical Bayesian scoring (single judge per project)

Crowd-BT is primary wherever pairwise data exists and is never replaced. When
each project has only one judge there are no pairs, so `POST
/events/{id}/results/calculate` refuses — and points at `POST
/events/{id}/bayes/calculate` instead. That fit models absolute scores as
`R = θ + b + ε` (project quality + judge severity/leniency + noise) with
partially pooled judge effects: a judge seen once is shrunk to the population,
never "corrected" on one data point. Criteria are normalized to a common scale
before weighting, so any rubric shape works.

Unlike BT it reports uncertainty, not just points: `GET
/events/{id}/bayes/results` returns the Top-K view in plain language — rank,
score, likely range, Top-K chance, High/Medium/Low confidence, close calls
("A is 72% likely to rank above B"), judge-severity notes, and prioritized
extra-judging recommendations with a suggested judge each. Reopen the window,
assign, score, close, recalculate — a new versioned run, history kept.
Version `hier-bayes-score-v2`, tables `bayes_project_results` /
`bayes_judge_effects`, code `modules/judging/{hier_score,bayes}.py`.
Variance components are EM-estimated (noise from within-project residuals —
same project, different judges — with a weak prior toward small noise;
project/judge variance from posterior spread plus posterior variance; best
marginal-likelihood hypers kept as a guard; deterministic). Pure single-judge
data (no project scored twice) keeps the legacy one-shot convention exactly,
since noise vs quality is unidentifiable there by construction. Each run's
config records the variance shares plus a plain-language flag when noise
claims >80% of total spread ("scores vary mostly within judges — ranking
certainty limited").

When the model flags a close call as uncertain, the organizer — not the model —
has the last word, all inside the Uncertainty tab. The tab itself is shown
only when Bradley–Terry cannot run (no pairs, or a disconnected graph), never
next to a viable BT ranking; a past Bayesian run keeps it visible so its
history is never orphaned (decided server-side in `GET
/events/{id}/judging` as `models: {bt_viable, bayes_ready}`, so tab and
calculate gate cannot disagree):

- **Interchange two ranks** (`POST …/bayes/swap {project_a_id, project_b_id,
  reason?}`): writes a full manual-rank snapshot over the latest run; the model
  order underneath is never mutated. `DELETE …/bayes/overrides` reverts to it.
  Results expose both `ranking` (model) and `effective` (with `rank_source:
  model|manual`).
- **Assign extra judging manually** (`POST …/assignments/manual {project_id,
  judge_user_id}`): one pool judge, one project — pool means active roster AND
  JUDGE role, no new faces; duplicates and closed windows refused. Overrides
  live in `bayes_rank_overrides` (migration `0012`). In the UI the assign
  control appears only on projects the model recommends re-evaluating (members
  of a close call), not on settled rows.

Refit after extra judging means reopening the window, assigning, scoring,
closing, and recalculating: a new versioned run, history kept.

## Known limitations

- **Sparse bridges** — connectivity (one component) is enforced, but bridge
  *redundancy* (≥2 shared judges per group pair) is only warned about in the
  health endpoint, not enforced during assignment. Single-judge bridges
  produce near-flat likelihood directions. See Future work below.
- **All-pairs quadratic dominance** — a judge scoring `n` projects contributes
  `n(n−1)/2` observations, treated as independent. Prolific judges dominate
  and transitive pairs are over-counted. Not fixed in v2. See Future work.
- **Independent per-judge reliabilities** — judges with 1–2 comparisons get
  reliability estimates that mostly reflect the prior, not the data. No partial
  pooling across judges yet. See Future work.
- **History transfer is mean-only** — posterior variance resets to
  `NEUTRAL_SIGMA = 0.60` on every cross-event transfer; a judge with 500 past
  comparisons gets the same prior width as one with 1.
- **Disconnected comparison graphs refuse to fit** (by design) rather than
  ranking incomparable projects.
- Fixture `judges`/`scores` tables are untouched legacy seed data, not live
  judging state. The architecture doc's §15/§16 magnitudes reproduce only under
  the *removed* margin weighting, so they are not reference values for the
  corrected model (see context.md §25); the evidence table and both orderings
  match exactly.

## Future work (not yet implemented)

Items are ordered by estimated correctness impact. The first three address
the largest remaining biases after the v2 improvements.

### FW-1 — Bridge redundancy enforcement in assignment
**Problem:** single-judge links between project groups produce near-flat BT
likelihood directions; the health endpoint warns but assignment does not
enforce ≥2 shared judges per group pair.

**Fix:** strengthen `_slot_ranking` in `assign.py` to count bridge weight
(shared judges) rather than just new components. When filling the 3rd+ slot,
prefer judges who *reinforce weak bridges* (existing 1-judge links) over those
who open new components. This is an assignment-only change, no model change.

### FW-2 — Plackett-Luce or adjacent-pairs likelihood
**Problem:** all-pairs BT with `n(n−1)/2` observations per judge inflates
effective sample size and lets prolific judges dominate (verified: a 4-project
judge contributed 46% of all evidence in the POC). Pairs are treated as
independent when `A>B, B>C ⊨ A>C` makes them redundant.

**Fix (adjacent-pairs, lower risk):** change `pairwise.generate_pairs()` to
emit only `(rank_k, rank_{k+1})` pairs per judge, reducing `O(n²)` to `O(n)`
observations while keeping the BT likelihood unchanged. Add a `pair_mode`
field to `run.config` so runs are comparable.

**Fix (Plackett-Luce, higher correctness):** replace the BT likelihood with a
Plackett-Luce rank likelihood — one observation per judge ranking. Requires
rewriting the `nlp_and_grad` closure and revalidating all tests.

### FW-3 — Pooled judge reliabilities
**Problem:** per-judge independent reliability estimates are meaningless (anti-
correlated with truth at −0.94 Kendall tau) for judges with 1–2 comparisons.
The prior is `NEUTRAL_SIGMA = 0.60` regardless of past evidence.

**Fix:** hierarchical prior `log r_j ~ Normal(μ_pop, τ²)` with estimated
`μ_pop, τ` via EM or a VB step. Immediate lighter-touch fix: suppress
reliability display for judges with fewer than 3 submitted comparisons
(add `n_pairs` to `ModelJudgeResult`).

### FW-4 — Multi-start optimizer
**Problem:** the full model with free log-reliabilities is non-convex.
Different starting points can reach different optima. Currently a single
all-zeros start is used.

**Fix:** add `n_starts` config parameter (default 1, production 5). Use seeded
random starting points (seeded from `run_id` for reproducibility). Keep the
start with the lowest final objective value. Store `best_objective` and
`n_starts_tried` in `run.config`. Do after analytic gradient (cost
multiplied by `n_starts`).

### FW-5 — Real hierarchical history transfer
**Problem:** `reliability.py` transfers only the posterior mean across events;
sigma always resets to `NEUTRAL_SIGMA = 0.60`. A judge with 500 past
comparisons gets the same prior width as a first-timer.

**Fix:** store `posterior_sigma` (currently NULL in `judge_reliability_history`)
using the Laplace variance already computed in v2. In `prior_for_judge`,
propagate `sigma = sqrt(posterior_sigma)` instead of always resetting to neutral.
Requires precision-weighted aggregation when multiple history rows exist.

### FW-6 — Tie model
**Problem:** tied scores produce no observation, discarding "these projects are
equal" signal. Silent dropping biases toward judges who avoid ties.

**Fix:** Davidson or Rao–Kupper BT tie extension — adds a `ν` tie-propensity
parameter and generates a third outcome class. At minimum, report per-judge
tie rate as a diagnostic in the results payload.

### FW-7 — Export hygiene
**Problem (low severity):** CSV export does not neutralize leading `= + - @`
in project/team/track names, which Excel/LibreOffice execute as formulas.
NULL `weighted_score` rows are silently dropped without a count or log.

**Fix:** prefix-sanitize cells that start with formula characters. Count
and log dropped NULL rows as an audit entry rather than a silent filter.

### FW-8 — Async calculation
**Problem:** `POST /events/{id}/results/calculate` runs BFGS synchronously
in-request with no cap or timeout. Even with the analytic gradient, very large
events (100+ projects) can occupy the API worker for minutes.

**Fix:** move fit off-request (async task or background worker). Return a
`run_id` immediately and poll `GET /events/{id}/results/runs` for completion.
Requires a task queue or a lightweight in-process job table — outside the
current "no new services" constraint.
