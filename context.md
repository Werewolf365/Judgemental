# DOGFOOD Architecture Context

This document tracks the core architecture, data model, and recent changes to the DOGFOOD hackathon judging platform.

## Technology Stack
- **Frontend**: Next.js (App Router, TypeScript), React, Vanilla CSS (Frutiger Aero aesthetic).
- **Backend**: FastAPI (Python), SQLAlchemy, asyncpg.
- **Database**: PostgreSQL (schema `dogfood`).
- **Deployment**: Docker Compose.

## Core Data Model

The platform revolves around the following core entities:
- `users`: Registered users with roles (`PARTICIPANT`, `JUDGE`, `ORGANIZER`, `ADMIN`).
- `events`: Hackathon events that users can join.
- `event_participants`: Users who have joined a specific event.
- `participant_registrations`: Detailed registration information for an event participant (e.g. degree, age, institution).
- `teams`: Teams created for an event.
- `team_members`: Users belonging to a team (with roles `CAPTAIN`, `MEMBER`).
- `team_invites`: Tokens used for joining a team.
- `projects`: Submissions/projects created by teams. Each team can draft and submit projects.
- `tracks`: Tracks/categories within an event (projects belong to tracks).
- `prizes`: Prizes awarded per track or event.
- `judges`: Judges invited to score projects.
- `judge_tracks`: Tracks assigned to specific judges.
- `scores`: Scores awarded by judges to projects.
- `sessions`: Authentication sessions.

## Recent Changes

### 1. Event-Scoped Gallery
**Goal**: Make the project gallery specific to each event, rather than global.
- **Frontend**: Created `/events/[slug]/projects` to list projects for a specific event. Removed the global gallery route.
- **Backend**: Secured the gallery backend endpoints (`/public/events/{slug}/projects`) to only return projects belonging to the queried event (`Project.event_id == event.id`), ensuring they have `status == SUBMITTED` and `is_visible == True`. Write protection was added to prevent arbitrary modification of protected fields (e.g., `event_id`, `status`).

### 2. Registration Flow
**Goal**: Collect participant details before they join an event or create a team.
- **Frontend**: Inserted a `RegistrationOverlay` modal into `/events/[slug]/page.tsx`. When a user clicks "Join this event", the form collects their details (name, email, phone, age, degree, year, institution, category, etc.) and validates them inline.
- **Data Flow**: The form data is sent via `POST /api/events/{id}/join`.
- **Docker**: The frontend image requires a rebuild (`docker-compose up -d --build web`) to pick up changes in production mode.

### 3. Participant Registrations Table
**Goal**: Securely store the collected registration details in the database.
- **Backend**: Added the `ParticipantRegistration` model in `backend/app/models.py`.
- **Backend**: Added the `RegistrationForm` schema in `backend/app/modules/events/schemas.py`.
- **Backend**: Updated the `POST /events/{event_id}/join` route to insert the parsed data into the `participant_registrations` table alongside the `EventParticipant` record.
- **Database**: Applied Alembic migration to create the table.

### 4. Draft Project Submissions
- Verified that draft project functionality is natively built-in.
- When creating a project via `/submissions/new`, it is assigned `ProjectStatus.DRAFT`.
- Drafts are invisible to the public and the gallery.
- Users can safely edit drafts on `/submissions/[id]/edit` and later finalize them by clicking "Submit project", setting the status to `SUBMITTED`.

### 5. Event-Scoped Gallery Navigation (no global gallery)
**Goal**: The gallery is per-hackathon, so it must never appear as a global destination. It only shows while exploring a specific event.
- **Frontend**: Removed the global `Gallery` nav item from `components/Header.tsx` (all roles) and the footer link in `app/layout.tsx`.
- **Frontend**: Landing page (`app/page.tsx`) spotlights the first published event and links "View gallery" + featured cards to `/events/[slug]/projects[/id]` for that event. Hero CTAs now point to `/events` instead of a global gallery.
- **Frontend**: `app/events/[slug]/projects/page.tsx` shows the parent event name in the eyebrow/lead and a "Back to event" link, so the gallery always carries its event context.
- **Rule for future work**: every link to a gallery MUST be shaped `/events/[slug]/projects` (reached from an event page, mission control, or event spotlight). Never re-add a global `/gallery` route or nav entry.

### 6. Gallery RBAC + Organizer Draft Previews
**Goal**: Gallery visibility must be role-deterministic: public for published events, organizer/admin-only for drafts, never random.
- **Backend**: `gallery/routes.py` uses `optional_user` on `/public/events/{slug}`, `/public/events/{slug}/projects`, `/public/projects/{id}`. Published → anyone; draft → ORGANIZER/ADMIN only (others get 404, no existence leak). Staff event payloads include inactive tracks.
- **Frontend**: Event page and event gallery fall back to authenticated endpoints for staff and render a "Draft preview — organizers only" badge. Mission-control drafts link "Preview draft" to the event page.
- **Verified**: draft gallery 404 anon/participant, 200 organizer; published gallery 200 anon.

### 7. Publish Flow Hardening
**Goal**: Organizers must always be able to publish from the console, regardless of which tab/selection state they are in.
- **Frontend**: Console `publish()` operates on the selected working-event id (`sel`) instead of a possibly stale detail view. Publish tab shows live status badge plus a requirements checklist (name set, deadline set).
- **Note**: Publish itself always worked at the API level (`POST /events/{id}/publish` → 200, event appears in `/public/events`); the failure mode was UI state, now removed.

### 8. Leave-Team DB Semantics (verified)
**Goal**: Confirm what leaving a team actually deletes.
- **Proven by query**: `DELETE /teams/{id}/members/me` deletes the caller's `team_members` row (1 → 0). Sole-member leave dissolves the team (0 `teams` rows). `event_participants` row is intentionally kept (still registered for the event). Post-submit roster changes are rejected (409).

### 9. Submissions Panel Gating
**Goal**: Submission UI only exists for registered + teamed users, in its own section — never inside registration.
- **Frontend**: Dashboard "My submissions" card and `/submissions` list page render an unlock prompt ("register + team first") when the user has no team; the "New project" action only appears once teamed (`/submissions/new` already guarded the same way server-side).

### 10. Organizer Gallery Entry Points
**Goal**: The gallery had no entry point inside the organizer section (console/mission control), so organizers couldn't find it.
- **Frontend**: Console working-event row now has "View gallery" (`/events/[slug]/projects`) plus a "+ New event" shortcut back to the Events tab. Events-tab rows and mission-control cards each have a "Gallery" button.
- **Note**: Creating an event always lives in Organize → Events tab → "New event" form (name + deadline → Create draft), then configure Tracks/Prizes and Publish. The "+ New event" buttons elsewhere just jump back to that tab.

### 11. Custom Date-Time Picker (no native control)
**Goal**: The native `datetime-local` picker looked foreign to the theme and showed an ambiguous DD-MM-YYYY format.
- **Frontend**: New `components/DateTimePicker.tsx` — glassy Aero-styled popup with month grid, month stepping, hour/minute selects, Today/Clear/Done, outside-click + Escape dismissal, and an unambiguous `DD Mon YYYY, H:MM AM/PM UTC` display. Same `YYYY-MM-DDTHH:mm` value contract as before, so the backend is untouched. Used for the console "Submissions close" field.
- **Fix**: The popup initially rendered `absolute` inside the `.card` (which has `overflow: hidden` for its gloss effect), so it was clipped invisible. It now renders through a `createPortal` to `document.body` with `fixed` positioning measured from the button, repositioned on scroll/resize, viewport-clamped, z-index above everything. Required adding `@types/react-dom` to devDependencies.
- **Fix 2**: The popup only opened downward, so the time row + footer drowned below the viewport edge. It now flips above the field when there is no room below (measured height, second pass after paint), like a native picker.
- **Fix 3**: The footer row (Time selects + Clear/Today/Done) was wider than the popup, so Done spilled past the card edge. The footer now wraps, gaps/padding tightened, and popup width is capped at `min(320px, 100vw - 16px)`.

### 12. Gallery Access Control + Guided Organizer Wizard
**Goal**: Let organizers choose who sees the gallery, and give event creation one cohesive path instead of scattered tabs.
- **Backend**: New `Event.gallery_visibility` (`PUBLIC` / `PARTICIPANTS` / `ORGANIZERS_ONLY`, default `PUBLIC`, migration `0003_gallery_visibility`). Gallery endpoints enforce it: drafts are staff-only (404 otherwise); published + PUBLIC → anyone; PARTICIPANTS → staff or joined participants (others 403 with a plain message); ORGANIZERS_ONLY → staff (others 403). Event info page stays public. Set via `PATCH /events/{id}` (also fixed: `EventIn.name` is now optional so partial PATCHes work; create still requires a name).
- **Frontend**: Console rewritten as a 5-step wizard — 1 Details (create or edit name/description/deadline), 2 Tracks, 3 Prizes, 4 Gallery access (three plain-worded cards: Public / Participants / Organizers only), 5 Review & publish (checklist + preview links). Clickable steps with progress, Next/Back everywhere. Submissions + Participants review lives in a second card below. Mission-control cards and the event page show the gallery access badge.
- **Verified matrix**: PUBLIC anon 200; PARTICIPANTS anon/outsider 403, joined 200, organizer 200; ORGANIZERS_ONLY participant 403, organizer 200; draft 404 anon/participant, 200 organizer; bad value 422.

### 13. Security Hardening (backend-only, no UI change)
**Goal**: Close the confirmed findings from the read-only security audit without changing anything the user sees or clicks.
- **Teams** (`teams/routes.py`): new invites and invite-token joins are rejected (409) once the team has a SUBMITTED project — the roster lock `leave_team` already had now covers all three mutation paths. Team names capped at 100 chars.
- **Events** (`events/routes.py`): `GET /events/{id}` returns 404 for non-staff on DRAFT events (was visible to any logged-in user). `EventIn.name` optional so PATCH is truly partial (create still requires a name).
- **Auth** (`auth/routes.py`, `auth/schemas.py`): password change revokes all other sessions (current session kept); passwords capped at 128 chars on register/login/change; self-registration is always PARTICIPANT (JUDGE role grants nothing today and must stay seed-assigned until T2). Session cookie `Secure` flag is opt-in via `COOKIE_SECURE=1` (off locally, behavior identical).
- **Schemas**: length caps on event/track/prize/project/registration fields; registration `age` is 1–150; URLs capped at 2000 chars.
- **Gateway** (`gateway/nginx.conf`): `X-Content-Type-Options`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, minimal `Permissions-Policy`. No HSTS (plain-HTTP local dev).
- **Health** (`app/main.py`): DB failures return a generic "database unreachable" (full error stays server-side in logs).
- **Verified**: 13/13 targeted probes pass (lock/invite/join 409s, draft 404 vs 200, session revoke + survivor, password/input 422s, role forcing). Full participant flow re-verified unchanged. `run.py` still `claimed T1, verified T1`.
- **Left as deploy-time notes (not changed)**: backend `:8000` stays published for local dev; CSV export and judge scoring remain deferred per T1 scope.

### 14. Repository Move + Data Incident (2026-09-26)
- **Move**: Project now lives at `https://github.com/Werewolf365/We_Judge.git` as a single root commit ("Initial commit - Dogfood T1 hackathon portal", dated 2026-09-26). No prior history, branches, or messages were carried over.
- **Incident**: During security testing, an overbroad scratch-cleanup query deleted the user-created events "another one" and "something". Both were recreated with identical names, deadlines, PUBLISHED status, and the two known tracks on "something" (`kay pata`, `kya pata ^ 1`); participant@local.test was re-registered. NOTE: their event IDs changed, and any prizes / extra tracks / other joins on those events that were never observed could not be restored — verify in the console.
- **Rule for future work**: never clean scratch data with a `NOT IN` filter. Delete probe rows by exact ID only.

### 15. Migrations Resequenced + Organizer-Defined Submission Fields
**Goal**: Numeric migration chain teammates can actually run, plus a submission form the organizer fully controls.
- **Migrations**: Deleted dead hex revisions (`e06e85…` renamed constraints only, `8159621d…` was an empty stub). New `0004_participant_registrations` really creates the table (`checkfirst`, FK stubs, matches the model). `0003` re-pointed `8159…` → `0002` (content untouched) so the chain is `0001→0002→0003→0004→0005`. **One-time repair**: any DB stamped past 0003 needs nothing; a DB stamped on a deleted hex rev must `alembic stamp 0003_gallery_visibility` then `upgrade head`. Verified fresh-DB `upgrade head` on a scratch database (both new tables created), then dropped it.
- **Backend**: `event_form_fields` table (label, type text/textarea/number/url/select, required, options) with organizer CRUD (`GET/POST /events/{id}/form-fields` — read is public like tracks; `PATCH/DELETE /form-fields/{id}` staff-only). Answers live on `projects.custom_data` (`{field_id: value}`, merged on PATCH); required/type/option rules enforced at submit, drafts stay partial. Public project detail resolves answers to label/value pairs.
- **Frontend**: Console wizard is now 6 steps with a new Step 4 "Submission form" (add, edit label/type/options, required toggle, remove). New/edit project forms render the event's questions dynamically underneath links.
- **Verified**: field CRUD 403/422 matrix, submit-without-required-answer 422 naming the field, answered submit → SUBMITTED, public detail shows answers, field edit/delete propagate. `run.py` still `claimed T1, verified T1`.

### 16. Role Model Reversed + Staff-Only Registration + Scroll Perf (2026-09-26)
**Goal**: Stop admin/organizer/judge accounts registering for events, make roles fully admin-assignable, confirm a publish with a popup, and fix laggy scrolling.
- **Roles are no longer "permanent"** (`modules/admin/routes.py`): deleted the `PERMANENT_ROLE` constant and the refusal branch that blocked any participant change. `ASSIGNABLE_ROLES` is now `("PARTICIPANT", "JUDGE", "ORGANIZER", "ADMIN")` and remains the single source of truth the pydantic validator enforces, so an unknown value still cannot reach `users.role`. Promotion **and** demotion both work in every direction. The only refusals left are the two that would break the platform rather than one account: you cannot change your own role, and the last remaining ADMIN cannot be stepped down — and both are now audited as `user.role_change_refused` (previously only the participant refusal was recorded, so a self/last-admin attempt left no trace).
- **Admin console dropdown** (`/admin`): the per-role "Make organizer"/"Make admin" buttons and the "role is permanent" label are gone, replaced by one `<select>` per row listing all four roles (`<current> — current` / `Make <role>`). Demoting away from ADMIN/ORGANIZER/JUDGE confirms first ("They lose <role> access right away."); a refused or cancelled change reloads the list so the dropdown snaps back rather than showing a role the server rejected. Own row is disabled.
- **Registration is participant-only** (`modules/events/routes.py`): `POST /events/{id}/join` refuses `ORGANIZER`/`ADMIN`/`JUDGE` with 403 **before** loading the event, so the answer cannot depend on which event is targeted. Frontend mirrors it (UX only): event page hero swaps the Join button for a role badge, `/events` cards swap "Register" for "Staff account". Participant flow is byte-for-byte unchanged.
- **Publish popup** (new `components/Popup.tsx`): a real `role="alertdialog"` dialog on a portal, dismissable by button / outside click / Escape, and it sets `body.overflow: hidden` while open so the wheel cannot scroll the page behind it. Fires on publish from both the console (Step 6) and the dashboard mission-control cards, for any role. Unpublish gets the same treatment in the `info` tone.
- **Scroll perf** (`globals.css`): three real causes removed. (1) `background-attachment: fixed` on `body` re-rasterized the whole gradient every scroll frame — moved to the existing fixed `.aero-field` layer, painted once then only composited. (2) `backdrop-filter: blur(14px)` on **every** `.card` (a dozen simultaneous blurs on a gallery page) — removed; `--card` alpha 0.72 → 0.88 so the panel reads the same. The header keeps its blur, it is the one place the glass effect is load-bearing, at a smaller radius (10px). (3) `filter: blur(2px)` on the three animated orbs re-blurred per frame for no visual gain (the radial gradients are already soft) — removed, and `will-change: transform` added so drift is a pure compositor transform. Also `scroll-behavior: smooth` is now gated behind `prefers-reduced-motion: no-preference`, and `.proj-card:hover` had its `transition` declared *inside* `:hover` so the lift only animated on the way out and snapped on the way in — moved to the resting state.
- **Also fixed (pre-existing, unrelated to the request)**: `scripts/check_t1.py` built its probe track names from `str(int(time.time()))[-6:]`, so two runs inside the same second collided on the event's unique `(event_id, name)` constraint and intermittently failed. Now `f"{int(time.time())%1000000:x}{os.getpid()%4096:03x}"` — unique per process. Separately, the `audit records event.published` check depended on a *previous* run having published something, so it failed on a fresh database; the suite now publishes/unpublishes the probe event itself.
- **Doc correction**: `ARCHITECTURE.md` had a whole paragraph arguing that PARTICIPANT is deliberately permanent and that "an admin cannot promote a competitor into staff". That is now the opposite of the code, so it was rewritten rather than left to lie.
- **Verified**: 68/68 internal checks pass, confirmed across 14 consecutive runs. New checks cover all three refused roles on join, participant→ORGANIZER→JUDGE→PARTICIPANT round trip, live-on-next-request for each direction, no-op idempotence, and last-admin safety. Role dropdown and publish popup confirmed in-browser (including that the popup closes on outside click). Rendering trace: 0 long tasks, 0 frames over 32ms. `run.py` still `claimed T1, verified T1`; T2 remains 404-by-design and is not claimed. (One caveat if you see 67: the suite talks to a live API, so a run that straddles `docker compose up --build` scores one check as a connection failure rather than a real regression. Re-run it once the container reports healthy.)
- **Rule for future work**: any guard that exists for a *platform* reason (lockout, event scoping) should be kept and audited; guards that exist only to freeze one account's role are policy, not security, and belong in the admin UI instead of the handler.

### 17. T2 Judging — Plan and Binding Decisions (2026-09-26)
**Sources**: `prompt_T2.md` (workflow, in implementation order Phase 1–10) + `crowd_bt_architecture_poc_corrected.md` (math reference) + `PROMPT.md` (still-binding T1 constraints). The POC reference subset (`prj_02/03/04/06/07/12`, `jdg_12/19/21/22/24/26`, documented MAP thetas/reliabilities) was verified to exist verbatim in the real `fixtures.json`, so the fitter can be validated against it. POC Appendix A uses wrong key names (`project_id`/`judge_id`/`score`/`name`); the real keys are `project`/`judge`/`criteria`/`title` — the validation adapter must map these, not the other way round.
- **D1 — Judge identity is `users.id`, not `judges.id`.** Auth, sessions, and the checker's judge tokens are all user-based, and `users.id` needs no fixture-row mapping (admin-promoted judges have no `judges` row). The `judges`/`scores`/`judge_tracks` tables stay untouched as seeded fixture legacy; the POC validation reads them through an email mapping in a test, never as live state. This also honors PROMPT.md §13 ("fixture judges must map to users where possible") — the seed already maps all 30.
- **D2 — No new `EventStatus` values.** PROMPT.md §6.3 forbids redundant states; judging stage is *derived*: `NOT_STARTED` (no window set or now < `judging_open`), `OPEN` (inside window, or window unset), `CLOSED` (past `judging_close`, no results), `RESULTS_READY` (a SUCCEEDED run exists). `CALCULATING` lives transiently on the model-run row (`RUNNING`), not on the event. New event columns only: `judging_open`, `judging_close` (nullable), `judges_per_project` (default 2), `rolling_judging` (default ON — the prompt's headline mode; harmless when no judges are assigned yet).
- **D3 — No workers/queues.** PROMPT.md bans new services, so rolling assignment runs in-request after a successful submit, wrapped so it can never fail the submission. Batch assignment is an explicit organizer-triggered endpoint (there is no scheduler to fire it at deadline-close; documented, not hidden).
- **D4 — Weight semantics (no total-100 rule).** Criterion `weight` is a nullable percentage: all-NULL across active criteria → equal weighting; any explicit weight must be `0 < w <= 100` and then *every* active criterion must carry one (mixed mode is 422); the calculator normalizes (`w_k / Σw`). Rationale: total-100 blocks incremental rubric building (add-one-criterion-at-a-time fails until the sum lands exactly), while normalization keeps 40/35/25 working identically.
- **D5 — No fixture backfill.** Fixture `scores` are legacy evidence for validating the fitter, not live evaluations. Runtime judging starts empty; CSV before results is header-only rather than fabricated rows.
- **D6 — Tests follow repo convention, not pytest-DB.** `backend/tests/test_gallery.py` has no `conftest.py` (its `client`/`headers` fixtures don't exist — the suite errors on collection today; left untouched, out of scope). So: pure unit tests for the DB-free fitter under `backend/tests/`, plus a live-server `scripts/check_t2.py` in the `check_t1.py` style (unique probe entities + cleanup).
- **D7 — New-dependency rule.** numpy+scipy are build-time wheels baked into the image (offline runtime unaffected); pinned to the exact versions verified installable (`numpy==2.5.3 scipy==1.18.1`).
- **Phases**: 1 data model → 2 rubrics → 3 assignment+roster → 4 judge API/UI → 5 lifecycle enforcement → 6 pairwise → 7 reliability history → 8 Crowd-BT fit (+POC validation test) → 9 results/CSV + claim T2 → 10 tests + docs. Each phase verified by live probes before moving on.

### 18. T2 Phase 1 — Data Model (done 2026-09-26)
- **Migration `0008_judging`** (revises 0007): 9 tables + 4 event columns (`judging_open`, `judging_close`, `judges_per_project` default 2, `rolling_judging` default true). All FKs `ondelete=CASCADE` except audit-style `assigned_by` (`SET NULL`); downgrade drops tables then the three new PG enum types. Applied cleanly on container boot; `check_t1.py` still ALL PASS.
- **Two implementation notes.** (1) The partial unique on `judge_assignments` had to be a unique *Index*, not a `UniqueConstraint` — SQLAlchemy only accepts `postgresql_where` on `Index` (the container failed to boot until this was fixed; the error is loud, not silent). Same enforcement either way. (2) Backend code is baked into the `api` image, so migration/model changes take effect only after `docker compose up -d --build api` — `exec` against the old container silently tests old code.
- **`requirements.txt`**: added `numpy==2.5.3 scipy==1.18.1` (exact versions verified installable in the container) for the Phase 8 MAP fit. Build-time wheels only; runtime stays offline.
- **Rule for future work**: never trust `exec`-based verification right after editing backend files — rebuild `api` first, then confirm via `alembic current`.

### 19. T2 Phase 2 — Rubrics + Judging Config (done 2026-09-26)
- **New module `backend/app/modules/judging/`** (`service.py`, `schemas.py`, `routes.py`, wired into `main.py`). Organizer/admin only, event-scoped through the existing `managed_event`/`require_manageable` guards — including the child-id rule: `PATCH/DELETE /rubric/{id}` re-checks the parent event, so a criterion id alone is never sufficient (probed: participant gets 403, not 404, on a live id — same convention as tracks).
- **Endpoints**: `GET/POST /events/{id}/rubric`, `PATCH/DELETE /rubric/{id}`, `GET/PATCH /events/{id}/judging` (window, `judges_per_project` 1–10, `rolling_judging` toggle; open≤close validated). Weight values restricted to `0 < w ≤ 100` at write time (422); mixed explicit/NULL weights are storable mid-edit but `resolve_weights()` refuses to score under them (422 naming the incomplete criteria) — incremental rubric building works, incoherent scoring cannot.
- **Lock semantics** (`service.rubric_locked`): locked once the window has opened OR any evaluation row exists. POST/PATCH → 409 when locked. DELETE pre-start hard-deletes; post-start it deactivates (`is_active=False`, one-way since PATCH stays locked) — the first draft had the 409 ordered before the deactivate branch, making deactivation unreachable dead code; probes caught it and the order was fixed so the prompt's explicit remove/deactivate power actually works.
- **Stage derivation** (no new `EventStatus`, per PROMPT.md §6.3): `NOT_STARTED` only when a future `judging_open` is set and nothing is finalized; no window at all means `OPEN` ("judge whenever"), so organizers are never forced to configure dates before trying judging. `CLOSED` past `judging_close`; `RESULTS_READY` once a SUCCEEDED run exists.
- **Verified by live probes** (draft probe event `judge-probe-tmp`, left in place like check_t1's own probe): create/duplicate-name/zero-weight/over-100/participant-403/config-range-422 matrix, lock→409 on all three writes, unlock→hard-delete, locked-delete→`{deactivated:true}` with the row surviving inactive. `check_t1.py` ALL PASS throughout.

### 20. T2 Phase 3 — Assignment Service + Roster (done 2026-09-26)
- **New `assign.py`**: `assign_project` / `assign_all_pending` / `remove_judge` / `utilization`, plus `eligible_judges` (active roster AND still holding the JUDGE role — a demoted account is skipped, never errors) and `judge_loads`. Selection is lowest-active-load with `user_id` tie-break (deterministic across concurrent runs); the in-memory load map is bumped per slot so one call never reuses a stale snapshot.
- **Concurrency, two layers**: (1) `SELECT … FOR UPDATE` on the event row serializes assignment decisions per event; (2) the partial unique index makes duplicates impossible even on interleave, and inserts use `ON CONFLICT DO NOTHING` — but the arbiter had to repeat the index predicate (`index_where`), otherwise Postgres cannot infer a partial index and concurrent dupes raise instead of being ignored.
- **Deliberate non-goal**: no stealing. Rebalance only fills under-covered projects; an ASSIGNED row is a commitment. Removing a judge revokes only incomplete rows (COMPLETED + evaluations survive), then refills through the same balanced pick excluding the removed judge.
- **Routes** (same file, same guards): roster `GET/POST/DELETE /events/{id}/judges` (target must already be JUDGE-role, mirroring the organizer roster; re-add reactivates the same row via upsert), `POST …/assignments/batch` (explicit one-big-assignment trigger — there is no scheduler, so `rolling_judging=false` events rely on this; idempotent, second run creates 0).
- **Rolling hook** in `submit_proj`: runs post-commit in try/except with rollback + log, so assignment can never fail a submission. `record()` never raises, so the audit row is safe too.
- **Verified by live probes**: roster 200×3 + 422/404/403 matrix; submit→auto-assign 2; second submit→balanced (2,1,1); batch twice→0 on rerun; remove judge with 2 incomplete→`{revoked:2, refilled:2, still_open:0}` with loads rebalancing to the survivors; re-add→200; remove-unknown→404. `check_t1.py` ALL PASS.

### 21. T2 Phase 4 — Judge API + UI (done 2026-09-26)
- **New `judge.py`** (strict `require_roles("JUDGE")` on every route): `GET /judge/assignments` (own work with project titles), `GET /judge/assignments/{id}` (project + active rubric + draft), `POST …/scores` (partial drafts allowed, first save flips ASSIGNED→IN_PROGRESS), `POST …/submit` (requires every active criterion, snapshots `weighted_score` under current normalized weights, one-way DRAFT→SUBMITTED + assignment COMPLETED, transactional), `GET /judge/scores` (own submitted evaluations; `?judge=<other-id>`→403 — this doubles as the checker's peer_scores URL).
- **Isolation matrix probed**: peer assignment id→403 (same answer as a missing id, no oracle), participant/organizer→403, anon→401, self-via-param→200. Edit/resubmit-after-submit→409. Out-of-range (11) and unknown-criterion scores→422. Submit-half-scored→422 naming the missing criteria. Past `judging_close`→403 with stage CLOSED; reopening restores 200. Score range is 0–10 inclusive; booleans explicitly rejected (they're `int` instances in Python).
- **UI**: `/judge` console (open vs submitted, per-assignment status badges) and `/judge/score/[id]` (project context, per-criterion 0–10 inputs, comment, live weighted total mirroring the server's equal/normalized logic with an explicit "rubric mid-edit" state instead of a bogus number, Save draft + confirm-gated Submit). Header shows Judging instead of Dashboard/Teams for JUDGE role; `/dashboard` forwards judges to `/judge` (the participant workspace is a dead end for accounts refused event registration). Full flow driven in a real browser: draft→submit→7.10 total, inputs locking post-submit.
- **check_t1.py fix (test-only)**: the suite asserted a *historical* `auth.login_failed` row inside the newest-500 audit window, which T2 probing pushed out (754 audit rows and counting). It now performs its own bad-password login before asserting — same self-sufficiency precedent as the `event.published` fix. ALL PASS (69 checks).

### 22. T2 Phase 5 — Judging Lifecycle (done 2026-09-26)
- **Gap closed**: previously nothing stopped *new assignments* after judging closed — a late submit would create work no judge could ever score. Now `assign_project` returns `ok:false` once the stage is CLOSED/RESULTS_READY, the rolling hook silently skips (the submission itself is untouched — 200 with 0 assignments, probed), and the explicit batch endpoint answers 409 with a message pointing at reopening the window.
- **Refills bypass the gate** (`allow_closed=True`): removing a judge post-close still revokes and refills, because that preserves coverage granted *before* the close rather than creating anything new. Probed: revoke-1/refill-1 post-close, then window reopened and roster restored.
- **Full lifecycle matrix now enforced**: rubric locked at start (§19) → scoring only in OPEN (§21) → no new assignments after close (here) → calculation only after close (Phase 9). Pre-close assignment (window in future) stays allowed so organizers can queue work. `check_t1.py` ALL PASS.

### 23. T2 Phase 6 — Pairwise Generator (done 2026-09-26)
- **New `pairwise.py`, pure functions, no DB**: `generate_pairs` (group by judge → all pairs → winner by snapshotted `weighted_score`, ties skipped, weight hardcoded 1.0) and `connected_components` (union-find over projects; >1 component means no common scale). Scores are read from the stored snapshot, so later rubric edits cannot reinterpret history.
- **Tie epsilon 1e-9**: weights like 0.35 aren't binary-exact, so two mathematically tied vectors can differ by float dust — `math.isclose(abs_tol=1e-9)` treats that as a tie instead of crowning a winner on dust. The POC's exact-`==` would do the wrong thing here; probed with the classic `0.1+0.2 vs 0.3` case.
- **First real unit tests** (`judging/tests/test_pairwise.py`, 7 passing in-container): the headline one replays the six-project reference subset through real `fixtures.json` keys and asserts the pipeline reproduces the architecture's documented 13-row evidence table *exactly* — this validates the key mapping (`judge`/`project`/`criteria`, not the POC's wrong names), tie behavior, and unit weights in one shot. Plus ties, dust, scale-invariance (strict 5v3 vs lenient 85v70 → same direction, same weight), single-project, connected, disconnected.
- **Test-layout notes**: the api image's build context is `backend/` only, so the test finds fixtures via `FIXTURE_PATH` → parents → cwd (the seed's convention first). Pre-existing `tests/test_gallery.py` still errors on collection (missing `client`/`headers` fixtures, no conftest — predates T2, left untouched). `check_t1.py` ALL PASS.

### 24. T2 Phase 7 — Historical Reliability (done 2026-09-26)
- **New `reliability.py`**: `prior_for_judge(db, user_id, event_id)` returns `(mu, sigma, source)`. Latest history row from any *other* event wins (same-event rows excluded so a recalculation can never feed on its own output); no row → neutral `(0, 0.60)` per the POC. History rows are written by the calculate flow (Phase 9), one per judge per SUCCEEDED run.
- **MAP limitation stated in code, not hidden**: point estimates carry no posterior variance, so `posterior_sigma` stores NULL and only the mean propagates — sigma always resets to neutral. Anyone expecting uncertainty to compound across competitions will read why it doesn't, plus the pointer to full-posterior sampling as the real fix.
- **Probed**: neutral prior for a judged judge with no history and for a nonexistent user. The HISTORICAL path has no rows to exercise yet — covered in Phase 9 after the first real calculation.

### 25. T2 Phase 8 — Crowd-BT Fitter (done 2026-09-26)
- **New `crowd_bt.py`, pure**: `fit()` (BFGS from zeros over free thetas + log-reliabilities, reference project fixed at 0, priors per judge, theta prior σ=2) and `rank()` (competition "1224" ranks, ties share). Deterministic by construction — same stored observations always replay to the same ranking, which is what makes §19's reproducibility requirement literally true.
- **Reference finding (important)**: the pipeline reproduces the architecture's 13-row evidence table *exactly* and both documented orderings (projects and judges) *exactly* — but the doc's §15/§16 magnitudes do NOT come from the corrected model. Proven by experiment: all gradient methods from multiple starts converge to one unique optimum (mine), while the documented numbers reproduce to 3 decimals only under the *removed* `w = 1 + |margin|` weighting. I.e. the doc's numbers encode the exact scale dependence §6 deletes (and Appendix A's printed code can't even run — it indexes `score[k]` on dicts keyed `judge`/`project`/`criteria`). Conclusion: magnitudes are not usable as reference values; the tests assert exact evidence + exact orders + a tight regression pin on the corrected model's own verified optimum (unique, multi-start confirmed). This is documented in the test file, not buried.
- **8 new tests, 15/15 passing** (`test_crowd_bt.py`): documented orders, pinned optimum, positivity, reference-fixed-at-0, historical-prior-pulls-posterior, determinism, empty/missing-prior refusal. `check_t1.py` ALL PASS.

### 26. T2 Phase 9 — Results/CSV + Claim T2, Phase 10 — Suite + Docs (done 2026-09-26)
- **Calculate** (`POST /events/{id}/results/calculate`, in `results.py`): requires stage CLOSED (never before the deadline — 409 while OPEN/NOT_STARTED, probed both), refuses empty/pairless/disconnected inputs with messages (disconnected names the stranded projects), deterministic reference (lexicographically smallest ranked project), per-judge priors, then persists run + unit-weighted observations + thetas/ranks + reliabilities + history rows in one transaction. Recalculation appends a new version (old rows never mutated); a <5min RUNNING run blocks duplicates; failures commit a FAILED row with the error and audit `event.results_failed`. Found live: stage derivation initially checked RESULTS_READY first, which would have made recalculation permanently impossible after the first run — reordered so reopening genuinely returns to OPEN.
- **Results/CSV**: `GET …/results` (latest SUCCEEDED run: ranking with team/track/thetas, reliabilities with priors, full config), `GET …/results/runs` (version history), `GET /export.csv?event_id=` (event-scoped; header-only 200 before any calculation — honest empty, not fabricated rows; participant 403, missing param 422, all probed).
- **Real-data finding**: the first live run (two judges, perfectly contradictory 1–1 evidence) converged to all-theta-0, all-r-1 — the correct Bayesian answer for zero net information, and a good sign the model isn't inventing separation. Competition "1224" rank-sharing handled the tie.
- **Coverage bug caught live**: `assign_project` counted only ACTIVE rows toward coverage, so batch-after-completion would re-pick finished judges into the partial unique index as an unhandled 500. Coverage now counts every live row (only REVOKED frees a slot).
- **Check ordering fix**: `_editable_assignment` checked finished-before-stage, so a post-deadline write on a completed item answered 409 instead of the uniform 403. Ambient stage first now — one "judging is over" branch for clients.
- **Organizer UI** (new `JudgingPanel.tsx` with Rubric/Judges/Settings/Results tabs inside the console, verified in-browser incl. the results table + run history), **judge peer URLs stable across reseeds** (`?judge=` accepts email as well as id — generated uuids change on `down -v`, fixture emails don't).
- **`.dogfood.toml` claims T1+T2** with real routes; `run.py` reports `claimed T1 T2, verified T1 T2` (7/7) and `acceptance-report.txt` regenerated.
- **`scripts/check_t2.py`** (37 checks, ALL PASS ×3 runs): full lifecycle on two fresh-per-run draft probes — rubric validation/lock matrix, roster guards, rolling-off proof, batch balance+idempotency, peer isolation, weighted-math equality, immutability, the connectivity-gate refusal (with no FAILED residue), cross-link recovery, deadline refusal, unanimous ranking with strictly decreasing thetas, recalculation replay identity, run history, CSV rows, equal-weight fallback live ((9,3)→6.0), second-event HISTORICAL prior. Rerun-safe via per-run slugs (T2 needs unevaluated projects; reuse is impossible, unlike check_t1's probe).
- **Docs**: JUDGING.md rewritten (was "deferred"), judging README replaced, DATA-MODEL/ARCHITECTURE/README updated, suite documented in README. Full matrix green: run.py 7/7, check_t1 69/69, check_t2 37/37, unit 15/15, `tsc` clean.
- **Rule for future work**: never assert on a doc's *numbers* without reproducing them — the crowd doc's own MAP magnitudes turned out to encode the removed weighting. Assert on evidence tables and orderings (exact), pin your own optimum (tight), and write down which is which.

### 27. Auto-Assign Sweep — Scheduled Batch Assignment (done 2026-09-26)
**Goal**: stop making the organizer press "Run batch assignment" by hand; cover submissions on a fixed cadence the manual button can never disturb.
- **Backend** (new `judging/scheduler.py`, asyncio-only — no new dependencies, image build untouched): an in-process loop started/stopped by a lifespan handler in `main.py`. Each tick sleeps `AUTO_ASSIGN_EVERY_SECONDS` (default `180` = 3 min testing; set `1800` for the 30-min production cadence — env only, no code change; also explicit in `docker-compose.yml`), then runs one `assign_all_pending` pass per event that has SUBMITTED projects, each in its own session with per-event rollback. Ticks re-read env, skip (don't pile up) while a sweep is still running via an `asyncio.Lock`, and log-only (no audit spam — the manual button keeps the audit trail). Empty sweeps change nothing (idempotent by construction).
- **Timer independence**: the button hits the same endpoint as before and shares no state with the loop — pressing it cannot shift, skip, or double a scheduled sweep; a manual batch racing a sweep converges via the existing FOR UPDATE + ON CONFLICT DO NOTHING guarantees.
- **UI**: button untouched; the stale "rolling OFF means press the button" note now states the sweep cadence + last sweep (time, count created), rendered from the existing judging-status payload the panel already fetches — zero new requests, zero polling, no lag risk. Rolling-settings label corrected the same way. The batch endpoint docstring's "there is no scheduler" claim was false after this change, so it was rewritten.
- **Rule for future work**: single worker assumed (stock uvicorn) — concurrent sweeps would stay *correct* but duplicate effort; revisit if workers are ever added.

### 28. Rubric Weights Must Total 100 (done 2026-09-26)
**Goal**: organizers could stack weights past 100 (e.g. 20+45+35+22=122) because scoring silently normalized. Weights are percentages now, enforced both ends.
- **Write-time** (`service.check_weight_cap`, called by POST/PATCH criterion): the explicit total across ACTIVE criteria may never exceed 100 — incremental building (20 → 65 → 100) works, overshoot 422s naming the remaining capacity. NULLs contribute 0 (mid-edit mixed mode still storable); deactivation frees capacity.
- **Scoring-time** (`resolve_weights`): an all-explicit rubric must total exactly 100 (±1e-6 float dust) or scoring/calculation 422s telling the organizer to fix it. All-NULL equal split unchanged.
- **UI**: rubric tab shows running total + remaining (or an over-cap error for legacy rows), and add/edit pre-checks the cap client-side with the same message — server stays authoritative.
- **Compatibility**: check_t2's 60/40 (=100) and all-NULL paths unaffected; unit tests never touch weights. Legacy rows already over 100 can no longer score until trimmed — intended.
- **Verified live**: add 30 → 200, add 80 (→110) → 422, add 70 (→100) → 200, patch 30→40 (→110) → 422, patch 30→20 → 200; unit 15/15, check_t2 ALL PASS, run.py 7/7.

### 29. Revoked Assignments Hidden From Judges (done 2026-09-26)
**Goal**: after an organizer removed a judge, their dashboard still listed every revoked assignment with REVOKED badges — dead work the judge could also still open via a bookmarked URL.
- **Backend** (`judging/judge.py`): `GET /judge/assignments` now excludes `REVOKED` rows outright, and `_own_assignment` answers 403 on revoked ids too (same no-oracle answer as missing/peer's, so detail/score/submit paths all refuse identically). COMPLETED work stays visible — only revoked work disappears, matching the "completed evaluations survive" rule.
- **Frontend**: removed the now-unreachable `REVOKED` badge tone; the page's existing filters already ignore anything but ASSIGNED/IN_PROGRESS/COMPLETED, so a removed judge lands on the "No assignments yet" empty state with zero new requests.
- **Rule for future work**: visibility of dead platform objects belongs server-side — the client must never be the thing hiding revoked/removed rows.

### 30. One Submission Per Team (done 2026-09-26)
**Goal**: teams were able to pile up multiple projects; exactly one project row may exist per team (deleted drafts free the slot).
- **Backend** (`submissions/routes.py`): `POST /submissions` answers 409 when the team already owns a project. Seed/fixture legacy rows (e.g. tm_07's duplicate) are untouched — the rule is write-time only.
- **Frontend**: project picker disables teams that already own one (with reason), auto-prefers a team without a project, and blocks save with an "open it instead" link; dashboard hides "New project" once every team owns one.
- **Suite migration**: `check_t2.py` previously built 4-projects-on-1-team scaffolding, which is now illegal input — it registers throwaway users (`mkuser` + `join_team_project` helpers) so EV runs 4 users/teams and EV2 runs 2, titles and all downstream numbers unchanged, plus a new explicit "second project refused (409)" check.
- **Verified**: check_t2 ALL PASS, run.py 7/7, unit 15/15.

### 31. Guided Judge Submit — Draft, Review, Final (done 2026-09-26)
**Goal**: judges must save a draft before submitting (already server-enforced), but the UI gave no guidance and submitted via `confirm()`.
- **Frontend** (`/judge/score/[id]`): step guidance under the buttons (save draft → complete → review → submit); Submit stays disabled until a complete draft is saved with no unsaved edits; then it opens a review `Popup` (per-criterion scores, comment, weighted total) with the **Final submit** button inside. `confirm()` is gone.
- **Backend untouched**: draft-required/complete/immutable semantics already held; check_t2's submit/409 paths re-verified green.

### 32. Captain-Only Submit + Invite Crash Fix (done 2026-09-26)
**Goal**: only the team captain may finalize a submission; also fixed an invite endpoint that 500'd for everyone.
- **Backend** (`submissions/routes.py`): `POST /submissions/{id}/submit` answers 403 unless the caller holds CAPTAIN on the team. Draft create/edit/delete stay member-level (collaborative drafting, single submitter — the Devfolio pattern). All suite submitters are team creators (captains), so no suite changes needed.
- **Backend** (`teams/routes.py`): `POST /teams/{id}/invites` crashed with `NameError: request` (T2 commit added an audit call without the `Request` param) — added the missing parameter. Invite flow works again.
- **Frontend** (editor Publish card): fetches the team roster, shows Submit only to the captain, members see "Only your team captain can submit".
- **Verified live**: member submit → 403, captain submit → 200; check_t2 ALL PASS, run.py 7/7, unit 15/15.

### 33. T3 Community Voting (done 2026-09-27)
**Goal**: organizer-opt-in public voting with quadratic budgets, gated comments, and anti-abuse that actually fires — without touching T1/T2 behavior.
- **Data** (migration `0009_voting`): event flags (`voting_enabled`, `voting_close`, `voting_mode` auth/email/open, `comments_visibility` public/team) + `ballots` (unique per voter×project, quadratic spend) + `comments` (hide-don't-delete moderation).
- **Rules**: 100 credits per voter, n votes cost n² (pure `quadratic.py`, 10 unit tests); drafts staff-only across the voting surface like the gallery; results 403 until the deadline passes, then public tally with 1224 ranks; comments need login, team-mode threads visible to the project's team + staff only.
- **Anti-abuse**: in-memory token buckets (30 ballot / 20 comment per min, env-tunable, 429 + audited refusals), fingerprint-collision turnout signals (advisory, never auto-blocking), own-team block for logins.
- **UI, zero polling**: `/events/[slug]/vote` (credits meter, steppers, per-mode identity, results after close), comments thread on project pages, console Step 7 (settings cards, deadline, turnout, audit search). Lag-free by construction — single load each.
- **Caught live, twice**: (1) tally "missing" P2 was a dropped suite step, not an app bug — the formalized check never cast the deciding vote; fixed the suite, exact tally asserted. (2) Three straight runs collided on reused probe emails; `mkuser` now logs in on 409 (rerun-safe).
- **Verified**: check_t3 ALL PASS (34 checks), unit 25/25, run.py 7/7, check_t1/check_t2 green, no T1/T2 route touched.

### 34. Voting Remodel — 10 Votes, Square-Root Influence (done 2026-09-27)
**Goal**: the credits-and-squares UX confused voters; organizers asked for "10 votes to distribute, total never above 10, no squared math shown" — while keeping the quadratic anti-concentration requirement (n votes carry √n influence).
- **Model** (`voting/quadratic.py`): per-voter cap of 10 total votes; tally sums **per-ballot** √votes per project (1224 ranks, deterministic). Spent/remaining now mean votes used/left; no totals or costs surface anywhere in the UI.
- **UI**: vote page shows "Votes left: X of 10", steppers refuse to exceed 10 in total, results show score (influence, 2dp); organizer view replaces casting controls for staff. DateTimePicker gains `defaultToday` (empty deadline fields pre-select today) — applied to voting + event deadlines, deliberately NOT to judging open/close (that would silently create restrictions).
- **Caught live, twice**: (1) the remodel's first `tally()` summed raw votes then took one √ (sqrt-of-sum) — wrong invariant, and the unit test accidentally encoded it (√4 = 2.0 passes either way); fixed the function AND pinned the test to √3+√1 ≈ 2.7321 with a comment stating the distinction. (2) A stale `quadratic.CREDITS` reference 500'd the ballot box — fixed to `VOTE_CAP`.
- **Verified**: check_t3 ALL PASS (exact sqrt tally asserted), unit 25/25, run.py 7/7.

### 35. Vote UX: Cast Confirmation + Organizer Standings (done 2026-09-27)
**Goal**: voters got no persistent "you voted" signal, and organizers had no way to see live standings before close.
- **Voter**: the vote page now tracks server-confirmed allocations separately from local edits — a "Votes cast — X of 10 placed" badge plus per-project "✓ N votes cast", with an "unsaved changes" note when the two differ. Survives reload (state comes from the server, not memory).
- **Organizer**: new `GET /events/{id}/voting/standings` (staff-only; 403 participant, 401 anon, all probed) sharing one `_rank_event` helper with the public results endpoint so both can never disagree. The organizer ballot view renders the live ranking with a "public results publish at close" note. The public results gate itself is untouched.
- **Verified**: standings matrix live, check_t3 ALL PASS, run.py 7/7, unit 25/25.

### 36. Profile Pictures + Judge-Only UI + Full-Detail CSV (done 2026-09-27)
**Goal**: three small professional gaps — no avatars, judges seeing participant dead-ends, and a results-only CSV.
- **Avatars** (migration `0010_avatar`): `users.avatar_url` stores a client-resized data: URL (128px JPEG via canvas, 300KB server cap, data:image-only validation so nothing external can be smuggled in; empty clears). Shown in the header chip, settings (upload/preview/remove), and comment author rows. Public profile data by design, never auth material.
- **Judge-only UI**: header already hid Dashboard for judges and `/dashboard` already forwarded to `/judge`; now `/teams`, `/submissions`, `/submissions/new` render a shared `JudgeGate` ("Judges don't compete" → judging console) instead of dead-end participant flows, and event cards hide Register/Submit for judge accounts (registration is 403 server-side anyway).
- **CSV** (`GET /export.csv` reshaped): one row per evaluation at EVERY stage (drafts included, status column) — project, team, team **leader** (captain name + email), track, judge (+email), per-criterion raw score / weight% / normalized share, weighted total, plus rank/theta once a SUCCEEDED run exists (blank before). Mid-edit rubrics export with blank shares instead of 422ing. `check_t2` assertion migrated to the new shape (9 lines: header + 8 evaluations).
- **Verified live**: avatar set/read/clear roundtrip + non-image 422; captain name+email in real export rows; run.py 7/7, check_t2 ALL PASS, unit 25/25, check_t3 ALL PASS.
- **Follow-up**: the export had no UI entry point, so organizers couldn't find it. The judging console Results tab now has an **Export CSV** download button (plain same-origin anchor → browser download with session cookies, no fetch plumbing). Verified 200 + `text/csv` through the gateway.

### 37. Comment UI Polish (done 2026-09-27)
**Goal**: the comment composer rendered label + textarea crammed on one line (it sat outside any `.field` container, so inputs fell back to unstyled inline layout).
- **Frontend** (`components/Comments.tsx` rewritten): proper stacked composer (full-width 3-row textarea, live character count, Post disabled until non-empty, login prompt for anonymous), comment rows with avatar initials, name + timestamp header, hidden-state badges, staff Hide/Show tucked per row, count badge header, designed empty state.
- **Verified**: frontend build clean (typecheck + lint), project page 200.
