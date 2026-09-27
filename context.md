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
