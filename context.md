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
