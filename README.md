# T1 Core — Hackathon Portal

Self-hostable hackathon platform (T1 vertical slice): organizer creates/publishes
events, participants join, form teams via secure invite links, save drafts,
submit before a server-enforced UTC deadline, and the public browses a
searchable gallery. Everything runs locally with `docker compose up`.

## Quick start

```
docker compose up --build -d
# WEB     http://localhost:3000
# GATEWAY http://localhost:8080   <- use this for run.py
# API     http://localhost:8000
# health  http://localhost:8000/health
docker compose logs api   # shows "seeded ... test logins"
python run.py .dogfood.toml
```

Stop: `docker compose down`. Clean reset: `docker compose down -v`.

## Seeded accounts (local only, password `Local123!`)

- organizer@local.test (ORGANIZER)
- admin@local.test (ADMIN)
- judge@local.test (JUDGE)
- participant@local.test (PARTICIPANT)
- 30 fixture judges (role JUDGE), 91 fixture participants

## Scale demos (700 projects, 50 judges, 4000 voters)

`python scripts/seed_scale.py` (runs inside the api container — see its
header) rebuilds the three demos at real-event volume: tailored CSVs in
`scripts/demo_csv/scale/` imported through the real endpoint, then bulk
evidence and real calculations. Deterministic (seeded): leaders separate,
mid-field is honest mush.

- `demo-bt` — 700 projects × 3 evaluations from 50 judges, Crowd-BT ranked.
- `demo-bayes` — 700 projects × 1 evaluation, hier-Bayes scored.
- `demo-vote` — 50 projects, 4000 skewed voters, blended judge/crowd ranking.

Scale truth: a 700-way total order cannot be confident — adjacent gaps are
dust. The top group leads decisively (θ ≈ 2.4–3.0 vs ≈ 0 mid-field) while
internal order flags close calls. That is the uncertainty tab working, not
failing.

## Dedicated demo events (manual testing)

`python scripts/seed_demos.py` (rerun-safe) ensures three stable events with
full tracks + prizes, so specific flows can be tested by hand without
tripping over per-run probe data:

- `demo-bt` — BT Model Demo: Craft 60 / Scope 40 rubric, 2 judges, batch mode.
- `demo-vote` — Community Vote Demo: open ballot, public comments.
- `demo-bayes` — Bayes Score Demo: unweighted rubric, 1 judge per project.

Sample Hack 2026 and `fixtures.json` data are never touched by it.

`python scripts/seed_demo_data.py` (rerun-safe, run after the above) fills
those events with real data — demo-* users, teams, SUBMITTED projects,
judge scores, ballots — and runs the calculations, so each demo is
immediately viewable in the UI:

- `demo-bt` — 8 projects across both tracks, 4 judges (2 evaluations
  each), designed scoring gradient, Crowd-BT ranking P1>…>P8 with
  reliabilities.
- `demo-bayes` — 4 projects, 2 judges, H1>H2>H3>H4 under the hier-Bayes
  scorer with means, ranges and Top-K.
- `demo-vote` — 5 projects, 4 voters with varied ballots, visible comment
  thread, window closed, public tally P1>P2>P3>P5>P4.

## Anti-abuse (T3 voting) + pen test

Full model: [`SECURITY_MODEL.md`](SECURITY_MODEL.md).

Rate limits (per-minute token buckets, refusals audited), quadratic vote
budgets, own-team block, UUID/email voter identity, fingerprint-collision
turnout signals, and an organizer-readable event audit
(`GET /events/{id}/audit` — no database client needed).

`python scripts/pen_test_abuse.py` attacks a throwaway probe event across
45 checks: budget overruns (including a concurrent double-spend race),
bad/negative identities, cross-event, draft and hidden targets, own-team
votes, pre-close tally pulls, comment abuse plus identical-repost spam,
stored-flag assertions, the full block lifecycle (voter + IP create,
enforce, revoke), and ballot/comment/register/login floods with and without
spoofed `X-Forwarded-For` — then verifies every refusal lands in the
organizer's (or admin's) audit view. Clean up after with `clean_probes.py`.

Fixed along the way: comment floods now carry the real event id into the
audit (previously invisible to organizers), comments on draft/hidden
projects 404 for non-staff, IP attribution uses the gateway-seen address,
ballot writes serialize per voter, and register/login are throttled
(`REGISTER_PER_HOUR` 100, `LOGIN_PER_MIN` 30 — tunable in
docker-compose.yml).

Known accepted risks (by design, not oversights): email mode trusts
self-asserted addresses (no mail infra to verify), open mode is Sybil-able
by design (UUIDs are friction, fingerprints are advisory signals),
auth-mode Sybil is slowed — not stopped — by the register throttle, and
NAT-shared IPs share one bucket (generous by choice).

## Cleaning test-probe clutter

`check_t1/t2/t3.py` leave per-run probe events + users behind
(`t2-probe-*`, `t3-probe-*`, `scope-probe-tmp`, …). To wipe them:

```
python scripts/clean_probes.py --dry-run   # list only
python scripts/clean_probes.py             # delete
```

Keeps `evt_01`, the `demo-*` events, fixture users and all four demo
accounts. Needs the `db` container running.

Stable local session tokens for the checker live in `.dogfood.toml`.

## Scope (T1 + T2 + T3) / deferred

T1 Implemented: auth + DB sessions, account settings, events/dates/publish,
tracks, prizes, event join/leave, teams + captain + invites + leave
(roster locks after submission), draft/submit/delete with UTC deadline,
organizer submissions review with gallery hide/show moderation,
organizer participants list, public gallery (search/filter/pagination)
with team member names.

T2 Implemented (see JUDGING.md): organizer rubric builder with weights,
judge roster with load/utilization, balanced assignment (rolling on submit
or explicit batch), judge console with draft/final scoring, judging window
enforcement, within-judge pairwise preferences, hierarchical Crowd-BT
ranking with judge reliability + cross-event priors, versioned model runs,
organizer results view, CSV export. Edge case (one judge per project):
hierarchical Bayesian scorer with Top-K uncertainty view, organizer rank
interchange with revert, and manual extra-judging assignment from the
existing pool.

T3 Implemented (see VOTING.md): opt-in public voting with organizer-set
mode (open link / email-gated / authenticated) and end deadline, 10 votes
per voter with square-root influence (piling votes counts for less than
broad support), hidden-until-close results tally,
comments with public/team-only visibility + organizer moderation, rate
limits with audited refusals, duplicate signals, organizer-readable audit.

Deferred: T4 webhooks/certificates/widgets.
`judges`/`scores` fixture tables stay as seeded legacy data; live judging
uses the T2 tables (DATA-MODEL.md).

## Migrations / seed

```
# inside api container (compose does this on boot):
alembic upgrade head
python -m app.seed     # idempotent; safe to run twice
```

## Tests

- Official: `python run.py .dogfood.toml` → expect `claimed T1 T2, verified T1 T2`
- Internal T1: `python scripts/check_t1.py` (health/seed/auth/roles/gallery/leakage)
- Internal T2: `python scripts/check_t2.py` (rubrics/assignment/scoring/lifecycle/ranking/CSV)
- Internal T3: `python scripts/check_t3.py` (settings/modes/budgets/results/comments/rate-limits/audit)
- Backend unit: `docker compose exec api python -m pytest app/modules/judging/tests/ app/modules/voting/tests/ -q`
- Frontend: `npm run build` (typecheck+lint) runs in the web image build.

## Known limitations

- One team per participant per event (by design).
- Submitted projects are immutable (no SUBMITTED→DRAFT).
- Search is ILIKE-based; no trigram/full-text engine.
