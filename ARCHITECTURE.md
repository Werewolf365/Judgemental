# ARCHITECTURE

```
Browser → :8080 nginx gateway → web:3000 (Next.js) | api:8000 (FastAPI) → Postgres:5432
```

Modular monolith: ONE deployable backend. Modules `auth, events, teams,
submissions, gallery, admin` communicate via service/repository imports,
never HTTP. `judging/` and `voting/` are boundary placeholders (README only).

Request flow: route (thin) → service logic inline in route → SQLAlchemy →
PostgreSQL. AuthZ lives server-side: `current_user` (HttpOnly `session`
cookie → SHA256 token_hash lookup) + `require_roles(...)` + team-membership
and event/track ownership checks per request. Frontend role checks are UX only.

Why not microservices: T1 needs transactions spanning events/teams/projects
(deadline submit, invite auto-join). A single DB + single app keeps those
atomic without distributed sagas, and `docker compose up` stays trivial.
