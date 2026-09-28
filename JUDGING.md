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
  → Judge roster + balanced assignment
  → Scores within the judging window (S_ij = Σ w_k × score_ijk, judge-local)
  → Within-judge pairwise preferences, unit-weighted, ties skipped
  → Hierarchical Bayesian Crowd-BT (MAP): project strength θ + judge reliability r
  → Ranked results + versioned model runs + CSV export
```

The one invariant everything else serves: **raw score margins never become
evidence weights.** Every non-tied comparison enters the model with weight 1
(enforced in `pairwise.py`, in a DB `CHECK` constraint, and by test). Judge
reliability — not score range — decides how strongly a preference pattern
counts. Strictness and leniency are offsets the pairwise conversion removes,
not signals about trustworthiness.

## Roles

- **Organizer/admin** (event-scoped as usual): rubric CRUD, judge roster,
  judging settings (window, judges per project, rolling on/off), batch
  assignment, final calculation, results, CSV export.
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

## Assignment

Lowest-active-load first, `user_id` tie-break, in-memory load updates per
slot (no stale snapshots), event-row locking plus a partial unique index
with a matching `ON CONFLICT` arbiter for idempotent retries. Rebalance
fills gaps but never steals assigned work.

## Auditability

Every model run snapshots its priors, rubric, reference project, and counts,
and stores each pairwise observation with its source evaluation ids — so the
chain Final rank → θ → pairs → weighted scores → rubric scores is walkable
from the database. Judge posteriors append to a cross-event history table;
the next competition's prior is the latest posterior (mean only — MAP yields
no variance, stated in code rather than faked).

## Known limitations

- MAP point estimates, no posterior uncertainty (crowd doc §20 future work).
- No confidence/margin model yet — margins stay out of the evidence
  entirely rather than half-used.
- Batch assignment is organizer-triggered; no scheduler fires it at deadline.
- Disconnected comparison graphs refuse to fit (by design) rather than
  ranking incomparable projects.
- Fixture `judges`/`scores` tables are untouched legacy seed data, not live
  judging state. One finding from validation: the architecture doc's own
  §15/§16 magnitudes reproduce only under the *removed* margin weighting,
  so they are not reference values for the corrected model (see context.md
  §25); the evidence table and both orderings match exactly.
