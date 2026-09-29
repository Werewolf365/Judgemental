# Security model

What this platform defends, how, and what it deliberately does not.
Verified by `scripts/pen_test_abuse.py` (34 checks), `scripts/check_t1/t2/t3.py`,
and the backend unit suites. Threat model assumes a hostile voter on the
open internet; organizers, judges and admins are trusted with exactly the
powers their role grants — nothing more.

## 1. Identity and sessions

- Passwords: Argon2id (`backend/app/shared/security.py`), 8–128 chars.
  Only hashes are stored; the audit trail strips anything resembling a
  credential (`password/token/secret/hash/...` keys are dropped, never
  truncated — `backend/app/shared/audit.py`).
- Sessions: 256-bit `secrets.token_urlsafe` tokens, stored as SHA-256 hashes,
  14-day expiry, revocable. Cookie is `HttpOnly`, `SameSite=Lax`
  (`Secure` opt-in via `COOKIE_SECURE=1` for TLS deployments).
- Password change revokes every other session; the caller stays logged in.

## 2. Roles and event scoping

Four roles, ascending: `PARTICIPANT`, `JUDGE`, `ORGANIZER`, `ADMIN`.
Self-registration always yields `PARTICIPANT`; only `ADMIN` can grant roles,
never to itself, and the last admin cannot be stepped down
(`backend/app/modules/admin/routes.py`).

`ORGANIZER` alone grants nothing: every organizer action passes through
`backend/app/modules/events/access.py`, which allows an event only to its
creator, its assigned organizers, or `ADMIN` (platform-wide bypass for
support/recovery). Drafts are invisible to outsiders — denials return the
same 404 as a bogus id, so drafts cannot be enumerated. Staff and judges
can never register as participants.

## 3. Voting anti-abuse (T3)

One voter, one math cap: 10 votes total across all projects, priced on the
**full resulting allocation** on every write, with per-row square-root
influence at tally time (`backend/app/modules/voting/quadratic.py`).

| Layer | Mechanism | Where |
|---|---|---|
| Budget | 10 votes/voter, 0–10/cell, whole numbers only; over-budget → 422 | `quadratic.py`, `service.price_allocation` |
| Concurrency | Per-voter Postgres advisory lock around price-and-write, so concurrent casts cannot double-spend | `routes.cast_ballot` |
| Identity | `auth` = session user id (strongest, enables own-team block); `email` = normalized address; `open` = client UUID | `service.voter_key_for` |
| Own-team | Logged-in voters cannot vote their own team's project (auth mode) | `routes.cast_ballot` |
| Rate limits | Token buckets: 30/min votes, 20/min comments, 30/min logins, 100/hour registrations (env-tunable in `docker-compose.yml`); every refusal audited | `ratelimit.py` |
| Flood signal | `fp_hash` (IP + user-agent + event, hashed) collision counts in turnout — advisory, never auto-blocking (shared networks) | `service.fingerprint` |
| Duplicate comments | Same author + project + body within 10 min → 429 `comment.duplicate` | `routes.post_comment` |
| Eligibility | Ballots/comments require SUBMITTED + gallery-visible projects; anything else is the same 404 as missing | `service.require_commentable`, `routes.cast_ballot` |
| Visibility | Results hidden until close; live standings organizer-only; drafts staff-only; team-only comment threads enforced | `routes.vote_results/standings/list_comments` |

IP attribution uses the **right-most** `X-Forwarded-For` entry (the address
the bundled nginx actually saw) and falls back to the direct peer — the
left-most entry is attacker-controlled past the gateway and is never
trusted (`routes._ip`, `shared/audit._client_ip`). A 45-request flood with
spoofed `XFF` still eats 429s instead of gaining a fresh bucket.

## 4. Judging integrity (T2, summarized)

Judge→project assignments are per-judge work items: opening a peer's
assignment is 403. Scores validate into each criterion's scale, snapshots
weight at submit time (later rubric edits cannot rewrite history), and
submitted evaluations are immutable. Pairwise evidence is unit-weighted by
DB constraint, ties produce no rows, and model recalculation appends new
versions instead of mutating. See `JUDGING.md`.

## 5. Audit trail

Append-only `audit_log` table, written on an independent short-lived session
so denied/rolled-back actions are still recorded and a failed write never
breaks the request (`shared/audit.record` never raises). Actor columns are
plain text, not foreign keys, so the trail survives account deletion.
Readers: `ADMIN` reads everything (`GET /admin/audit`); organizers read
their own events (`GET /events/{id}/audit` with action/search filters) —
no database client needed. Security-relevant refusals (rate limits,
duplicates, role-change denials, failed logins) are recorded, not just
successes.

## 6. API keys (T4 API-first)

Scoped bearer tokens for external integrations, managed in the admin
console (Administration → API keys):

- A key authenticates **as its owner**: role checks and event scoping apply
  unchanged; scopes further restrict by area (`events/judging/voting/
  transfer/admin`, each `:read`/`:write`, write implying read).
- Send as `Authorization: Bearer <token>`; `GET /auth/me` works as a whoami.
  Cookie sessions are never scope-checked, and keys are refused on all
  other `/auth/*` endpoints.
- Only the SHA-256 hash is stored — the raw token is shown once at creation.
  Revocation is a timestamp (audit stays joinable); expiry is optional;
  `last_used_at` tracks activity for stale-key cleanup.
- Creation, revocation are admin-only and audited (`apikey.created`,
  `apikey.revoked`); the key list shows owner, scopes, expiry, last use.

## 7. Residual risks (accepted, not oversights)

- **Email mode** trusts self-asserted addresses (no mail infrastructure to
  verify); plus-addressing multiplies identities.
- **Open mode** is Sybil-able by design; UUIDs are friction, fingerprints
  are signals. Use `auth` mode (with the own-team block) for anything
  prize-bearing.
- **Auth-mode Sybil** is slowed — not stopped — by the registration
  throttle; stopping it needs email verification.
- **NAT-shared IPs** share one bucket (generous by choice); multi-worker
  deployments would split buckets per worker (documented fail-open).
- Unlimited **reads** (ballot box, gallery) are not throttled; they are
  cheap indexed queries.
