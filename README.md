# Dogfood T1 Core — Hackathon Portal

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

## T1 scope / deferred

Implemented: auth + DB sessions, account settings, events/dates/publish,
tracks, prizes, event join/leave, teams + captain + invites + leave
(roster locks after submission), draft/submit/delete with UTC deadline,
organizer submissions review with gallery hide/show moderation,
organizer participants list, public gallery (search/filter/pagination)
with team member names.
Deferred: T2 judging UI/scoring/normalization, T3 voting/comments, T4
webhooks/certificates/widgets. `judges`/`scores` fixture data is preserved
in Postgres with no T2 behavior.

## Migrations / seed

```
# inside api container (compose does this on boot):
alembic upgrade head
python -m app.seed     # idempotent; safe to run twice
```

## Tests

- Official: `python run.py .dogfood.toml` → expect `claimed T1, verified T1`
- Internal: `python scripts/check_t1.py` (health/seed/auth/roles/gallery/leakage)
- Frontend: `npm run build` (typecheck+lint) runs in the web image build.

## Known limitations

- One team per participant per event (by design).
- Submitted projects are immutable (no SUBMITTED→DRAFT).
- Search is ILIKE-based; no trigram/full-text engine.
