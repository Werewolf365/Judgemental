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
- participant@local.test (PARTICIPANT)
- 30 fixture judges (role JUDGE), 91 fixture participants

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
organizer results view, CSV export.

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
