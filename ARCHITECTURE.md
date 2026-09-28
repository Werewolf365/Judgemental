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

Organizer access is **event-scoped**, enforced in
`modules/events/access.py` (never in route bodies): a user may manage an event
only if `events.created_by` is them or they are in `event_organizers`. `ADMIN`
is the single platform-wide role. `GET /events` filters to the caller's events,
`managed_event(...)` guards every event-scoped route, and `require_manageable`
re-checks the parent event on child routes (`/tracks/{id}`, `/prizes/{id}`,
`/form-fields/{id}`, `/submissions/{id}/visibility`) so a child id alone is
never sufficient. Denials on unpublished events return 404 to avoid confirming
that a draft exists. Adding an organizer grants access to that one event and
never grants a role — the target must already be an ORGANIZER or ADMIN.

Role management lives in `modules/admin/` and is ADMIN-only
(`require_roles("ADMIN")` on every route): `GET /admin/users` (directory
lookup), `POST /admin/users/role` (grant/revoke), `GET /admin/audit`. Because
`current_user` re-reads the user row on every request, a role change takes
effect on the target's next request without touching their session. An admin can
move an account to any of the four roles — `ASSIGNABLE_ROLES` is the single
source of truth, and the schema rejects anything outside it, so an unknown or
misspelled value never reaches the `users` table. The two refusals that remain
are platform-level, not per-account: you cannot change your own role (no
accidental lockout) and the last remaining ADMIN cannot be stepped down. Refused
attempts are audited as `user.role_change_refused`.

**Registration is the participant flow only.** `POST /events/{id}/join` refuses
`ORGANIZER`, `ADMIN` and `JUDGE` before it even looks at the event: staff run
events rather than competing in them, and a judge must not end up eligible to
submit into the event they are judging. The check is on the account's role, not
on a per-event relationship, so no event lets a staff account slip through.

`shared/audit.record()` writes the audit trail on its own short-lived session so
a row survives a rolled-back or denied action, and it never raises: a broken
audit write must not fail the request it is auditing. It strips any detail key
that looks like a credential (`password`, `token`, `secret`, `cookie`,
`authorization`, `hash`, `csrf`) and caps lengths, so secrets cannot be logged
by accident.

Why not microservices: T1 needs transactions spanning events/teams/projects
(deadline submit, invite auto-join). A single DB + single app keeps those
atomic without distributed sagas, and `docker compose up` stays trivial.
