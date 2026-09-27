MASTER BUILD PROMPT — DOGFOOD T1 CORE
=====================================

You are the principal full-stack engineer, software architect, product designer, QA engineer, and local-devops engineer responsible for building the FIRST COMPLETE VERTICAL SLICE of this project.

Do not merely explain what should be built.

Inspect the repository, inspect the fixture, make the required code changes, run the application, run the tests, diagnose failures, fix them, and repeat until the implementation is actually working.

Your output is a working repository, not a plan.

============================================================
0. PRODUCT CONTEXT
============================================================

We are building a self-hostable hackathon/event-management platform for the Dogfood hackathon.

The fundamental product lifecycle is:

ORGANIZER
    |
    +--> Create event
    +--> Configure dates
    +--> Configure tracks
    +--> Configure prizes
    +--> Publish event
              |
              v
PARTICIPANT
    |
    +--> Register / Login
    +--> Join event
    +--> Create team
    +--> Generate invite link
    +--> Other participants join team
    +--> Create project
    +--> Save draft
    +--> Edit draft
    +--> Submit before deadline
              |
              v
PUBLIC GALLERY
    |
    +--> Search
    +--> Filter
    +--> Paginate
    +--> View project

This is T1 — CORE.

T1 is the minimum judged requirement and therefore must be implemented as a complete end-to-end vertical slice.

DO NOT implement T2 judging functionality.
DO NOT implement T3 community voting functionality.
DO NOT implement T4 stretch functionality.

T2/T3/T4 may have clearly defined architectural boundaries, but they must remain deferred.

============================================================
1. NON-NEGOTIABLE CONSTRAINTS
============================================================

These constraints outrank convenience.

1. EVERYTHING MUST RUN LOCALLY.

2. No cloud database.

3. No Firebase.

4. No Supabase.

5. No hosted authentication.

6. No external API dependency.

7. No SaaS dependency.

8. No runtime network dependency.

9. No runtime CDN dependency.

10. No external font dependency.

11. No external image hosting requirement.

12. No Redis unless absolutely required.
    It is NOT required for T1, so DO NOT add it.

13. No microservices.

14. No separate backend services for Auth, Teams, Submissions, etc.

15. There is ONE deployable backend application.

16. There is ONE PostgreSQL database.

17. Internal modules communicate through application/service interfaces.
    They must NOT call each other through HTTP.

18. The fixture JSON is seed/import data.
    It must NOT simply be stored as one giant JSON blob in PostgreSQL.

19. The frontend must use real backend APIs.
    Never hardcode fixture records into React/Next components.

20. Backend authorization is the actual security boundary.
    Frontend role checks exist only for UX.

21. Do not infer submission state from missing fields.
    Use explicit project status.

22. Server-side UTC time is the authority for all deadline/business-rule enforcement.

23. Do not build a fake demo where buttons merely change local React state.

24. Every major workflow must persist real data in PostgreSQL.

25. Do not claim a feature is implemented unless you have actually executed and verified it.

============================================================
2. FIRST ACTION — REPOSITORY FORENSICS
============================================================

BEFORE writing code:

A. Inspect the entire repository tree.

B. Identify:
   - frontend stack
   - backend stack
   - package managers
   - lockfiles
   - existing Docker files
   - existing environment files
   - database code
   - migrations
   - tests
   - fixture files
   - README
   - existing architecture
   - existing API conventions

C. Locate the supplied fixture JSON.

D. READ THE FIXTURE COMPLETELY.

Do not inspect only the first few objects.

Understand:
- event
- tracks
- judges
- teams
- projects
- scores
- exact IDs
- exact field names
- relationships implied by IDs/emails
- any additional fields actually present

If a fixture exists under a non-obvious filename, locate it using repository search.

If the expected fixture cannot be found:
STOP before inventing a replacement schema or fake dataset.
Report the exact blocker.

E. If existing project code already establishes a reasonable technology choice, preserve it.

F. If this is genuinely greenfield, use this stack:

FRONTEND:
- Next.js
- App Router
- TypeScript
- Tailwind CSS
- accessible component primitives where useful
- no external runtime services

BACKEND:
- Python
- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- async PostgreSQL driver
- Argon2id password hashing

DATABASE:
- PostgreSQL

TESTING:
- pytest
- HTTP/API integration tests against real PostgreSQL
- Playwright for critical browser flows
- TypeScript type-checking
- linting/formatting

CONTAINERIZATION:
- Docker
- Docker Compose

If the repository already has an equivalent stack, DO NOT rewrite the project just for stylistic consistency.

The goal is a working system, not unnecessary migration.

============================================================
3. ARCHITECTURAL TARGET
============================================================

Use a MODULAR MONOLITH.

Target:

frontend
   |
   | REST
   v
ONE BACKEND APPLICATION
   |
   +-------------------------+
   |                         |
   v                         v
modules                  PostgreSQL
   |
   +-- auth
   +-- events
   +-- teams
   +-- submissions
   +-- gallery
   +-- judging [BOUNDARY ONLY]
   +-- voting [BOUNDARY ONLY]
   +-- admin

Recommended dependency direction:

AUTH / IDENTITY
      |
      v
EVENTS
      |
      v
TEAMS
      |
      v
SUBMISSIONS
      |
      +---------> GALLERY
      |
      +---------> JUDGING [future]

Avoid circular dependencies.

Do not create:

auth-service
event-service
team-service
submission-service

That would violate the required modular-monolith architecture.

============================================================
4. RECOMMENDED REPOSITORY SHAPE
============================================================

Use this as the target shape unless the existing repository has a better equivalent:

/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   ├── types/
│   └── tests/
│
├── backend/
│   └── app/
│       ├── modules/
│       │   ├── auth/
│       │   │   ├── routes.py
│       │   │   ├── service.py
│       │   │   ├── repository.py
│       │   │   ├── models.py
│       │   │   ├── schemas.py
│       │   │   └── dependencies.py
│       │   │
│       │   ├── events/
│       │   ├── teams/
│       │   ├── submissions/
│       │   ├── gallery/
│       │   │
│       │   ├── judging/
│       │   │   └── README.md
│       │   │
│       │   ├── voting/
│       │   │   └── README.md
│       │   │
│       │   └── admin/
│       │
│       ├── database/
│       ├── shared/
│       └── main.py
│
├── fixtures/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
├── docs/
├── docker-compose.yml
├── README.md
├── ARCHITECTURE.md
├── DATA-MODEL.md
├── JUDGING.md
├── LICENSE
├── acceptance-report.txt
└── .dogfood.toml

The exact filenames may vary, but the modular boundaries must remain.

============================================================
5. FIXTURE IS THE SOURCE OF TRUTH
============================================================

THIS IS CRITICAL.

The provided fixture already establishes the existing domain structure.

Do not invent an unrelated schema.

Preserve:
- event
- tracks
- judges
- teams
- projects
- scores

The fixture currently represents concepts roughly equivalent to:

event:
- id
- name
- submissions_close

track:
- id
- name

team:
- id
- name
- members[]

project:
- id
- team
- track
- title
- summary
- repo_url
- submitted_at

The exact fixture fields must take precedence over these conceptual descriptions.

Where T1 needs new functionality that the fixture does not contain:
extend the schema MINIMALLY.

Do not:
- duplicate entities
- randomly rename existing concepts
- delete T2 fixture data
- flatten relational data back into blobs
- hardcode fixture rows inside application logic

Preserve fixture IDs whenever practical.

============================================================
6. DATABASE DESIGN
============================================================

Use real normalized PostgreSQL tables.

At minimum:

users
events
event_participants
tracks
prizes
teams
team_members
team_invites
projects
sessions

Also preserve future judging-domain entities required by the fixture:

judges
scores

These judging entities may exist in the database without any T2 functionality.

Do NOT implement score calculation, judge assignment, score normalization, or judging UI.

------------------------------------------------------------
6.1 USERS
------------------------------------------------------------

User must have a persistent identity.

Conceptually:

User
- id
- email
- password_hash
- display_name
- role
- created_at
- updated_at

Roles:

PARTICIPANT
JUDGE
ORGANIZER
ADMIN

Use an enum or equivalent constrained representation.

Email must be unique case-insensitively.

Never store plaintext passwords.

Use Argon2id.

Normalize email for lookup.

------------------------------------------------------------
6.2 SESSIONS
------------------------------------------------------------

Use DB-backed sessions rather than JWTs unless the existing architecture already has a superior secure session approach.

Session concept:

- id
- user_id
- token_hash
- created_at
- expires_at
- revoked_at
- optional metadata such as user_agent

Generate cryptographically random session tokens.

Store only the token hash in PostgreSQL.

Send the raw session token to the browser only as a secure HttpOnly cookie.

Cookie characteristics:
- HttpOnly
- SameSite=Lax or stricter where compatible
- Secure in HTTPS deployment
- reasonable local development behavior
- explicit expiry

Do not store auth tokens in localStorage.

Implement:

POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me

Registration must:
- validate email
- validate password
- hash password
- create user
- create session
- return safe user/session state

Login must:
- authenticate
- create session
- set HttpOnly cookie

Logout must:
- revoke session
- clear cookie

/me must never return:
- password_hash
- session token
- internal secrets

------------------------------------------------------------
6.3 EVENTS
------------------------------------------------------------

Event must support multiple events.

Conceptually:

Event:
- id
- slug
- name
- registration_start nullable
- registration_close nullable
- event_start nullable
- event_end nullable
- submissions_open nullable
- submissions_close
- status
- created_by
- created_at
- updated_at

Preserve the fixture's submissions_close concept.

Use UTC timestamps.

Use timezone-aware database timestamps.

For status, keep the state machine intentionally small:

DRAFT
PUBLISHED
COMPLETED

Do NOT create redundant states such as:
REGISTRATION_OPEN
SUBMISSIONS_OPEN
SUBMISSIONS_CLOSED

unless there is an actual repository requirement.

Those phases should primarily be DERIVED from the dates.

Publishing:
- requires valid event configuration
- makes the event publicly discoverable

Unpublishing:
- moves the event back to DRAFT or equivalent unpublished state

Do not allow nonsense date ranges.

At minimum validate independently:
- registration_start <= registration_close
- event_start <= event_end
- submissions_open <= submissions_close

Do not impose additional cross-field restrictions unless they are clearly justified.

The backend must determine current phase using UTC.

------------------------------------------------------------
6.4 EVENT PARTICIPATION
------------------------------------------------------------

T1 needs a real "Join Event" concept.

Create:

event_participants
- event_id
- user_id
- joined_at

Composite uniqueness:
(event_id, user_id)

Participant cannot create a team for an event they have not joined.

A team invitation may optionally auto-join an authenticated participant to the event during the transaction, but the system must still create the event participation record.

------------------------------------------------------------
6.5 TRACKS
------------------------------------------------------------

Tracks belong to events.

Conceptually:

Track:
- id
- event_id
- name
- is_active
- created_at
- updated_at

Constraints:
- track belongs to one event
- track name should be unique within an event

Organizer/Admin can:
- create
- edit
- deactivate

Do not hard-delete a track that is already referenced by a project.

If a track has usage, deactivate it instead.

Participant project track selection must always be validated against:
- same event
- active track

Never hardcode fixture tracks.

------------------------------------------------------------
6.6 PRIZES
------------------------------------------------------------

Add:

Prize:
- id
- event_id
- track_id nullable
- name
- description nullable
- value_or_award_description nullable
- display_order
- created_at
- updated_at

Organizer/Admin can:
- create
- edit
- delete safely

Prizes are data, not hardcoded UI strings.

Public event pages must display prizes.

------------------------------------------------------------
6.7 TEAMS
------------------------------------------------------------

The fixture currently uses:

team:
- id
- name
- members[]

The final database must normalize members.

Use:

Team:
- id
- event_id
- name
- created_by
- created_at
- updated_at

TeamMember:
- team_id
- user_id
- role
- joined_at

Roles inside a team:
CAPTAIN
MEMBER

The user who creates the team becomes CAPTAIN.

Do not store members as a JSON array in the database.

Team names do not need global uniqueness.

============================================================
7. INVITATION LINKS
============================================================

T1 requires invitation-based team formation.

Create:

TeamInvite:
- id
- team_id
- token_hash
- created_by
- expires_at nullable
- used_at nullable
- revoked_at nullable
- created_at

Generate the raw token using a cryptographically secure source.

Use something equivalent to:

secrets.token_urlsafe(32)

DO NOT use:
- team ID
- user ID
- sequential IDs
- timestamps
- predictable UUID constructions

Store only a hash of the secret token.

The raw invite token appears only in the generated invitation URL.

Example frontend route:

/teams/join/<token>

Flow:

CAPTAIN
  |
  +--> Generate Invite
  |
  v
secure URL
  |
  v
participant opens link
  |
  v
authenticate
  |
  v
validate token
  |
  v
verify:
- token exists
- not revoked
- not expired
- team exists
- team/event relationship is valid
- user is not already in another incompatible team for same event
  |
  v
transaction:
- join event if necessary
- add member
- invalidate one-time invite if configured as one-use
  |
  v
success

Use one active invite at a time in the UI.
Regenerating an invite should revoke the previous active invite.

Never expose:
- raw invite tokens
- token hashes
through regular API responses.

============================================================
8. PROJECT / SUBMISSION MODEL
============================================================

IMPORTANT:

Do NOT create separate:
Project
AND
Submission

entities unless the fixture or actual domain absolutely requires it.

Prefer ONE entity representing the team's project/submission.

Keep the domain name aligned with the fixture: projects.

The submissions module may manage it internally.

Conceptually:

Project:
- id
- event_id
- team_id
- track_id
- title
- summary
- description nullable
- repo_url
- demo_url nullable
- live_url nullable if cheap to support
- thumbnail_url nullable
- status
- created_at
- updated_at
- submitted_at nullable

Optional tech tags may be added if they are cheap and cleanly modeled.

Do NOT allow optional presentation fields to complicate the T1 core.

The fixture's existing fields MUST be preserved.

------------------------------------------------------------
8.1 EXPLICIT STATE
------------------------------------------------------------

Status:

DRAFT
SUBMITTED

Rules:

DRAFT:
- editable by authorized team members
- not public
- submitted_at = null

SUBMITTED:
- public when event/gallery rules permit
- submitted_at populated by server
- no longer treated as a draft

Do NOT infer draft state from null fields.

------------------------------------------------------------
8.2 OWNERSHIP
------------------------------------------------------------

Only members of the project's team may:
- read its private draft
- edit it
- submit it

Do not trust:
- client-provided team IDs
- client-provided user IDs
- hidden form fields

Determine ownership from the authenticated session and database relationships.

Participant A must NEVER be able to modify Participant B's project by changing an ID in the request.

============================================================
9. DEADLINE ENFORCEMENT
============================================================

THIS IS A BACKEND SECURITY/BUSINESS RULE.

The frontend timer is for presentation only.

The server/database decides whether the deadline has passed.

Use UTC everywhere internally.

The backend must enforce:

BEFORE DEADLINE:
- create project
- edit draft
- save changes
- submit draft

AFTER DEADLINE:
- reject operations that are no longer permitted

Never rely on:
- disabled buttons
- JavaScript timers
- client timestamps
- hidden UI controls

For a robust implementation, introduce a small injectable Clock abstraction for business logic.

Production Clock:
- current UTC

Tests:
- controllable fake/test clock

This lets deadline tests run deterministically without altering the machine clock.

Submission operation must be transactional.

On submit:
1. authenticate
2. verify event
3. verify event membership
4. verify team membership
5. verify project belongs to team
6. verify track belongs to event
7. verify required fields
8. verify event accepts submissions
9. verify current server time <= submissions_close
10. verify status == DRAFT
11. atomically:
       status = SUBMITTED
       submitted_at = server UTC timestamp
12. commit

Prevent race conditions around the deadline as much as practically possible.

Use a DB transaction and row locking where appropriate.

After deadline:
return a clear machine-readable error and a useful UI message.

============================================================
10. SUBMISSION VALIDATION
============================================================

Before creating/updating/submitting a project:

Verify:

- authenticated user
- authenticated user is a participant
- user belongs to the selected team
- team belongs to event
- project belongs to team
- selected track belongs to same event
- selected track is active
- required fields are present
- project status transition is valid
- event publication/submission rules are valid
- submission opening time has arrived if configured
- submission closing time has not passed

Reject forged cross-event relationships.

Example invalid combination:

team from event A
+
track from event B

This must fail at the backend.

============================================================
11. PUBLIC GALLERY
============================================================

Implement:

GET /public/events
GET /public/events/{event_slug}
GET /public/events/{event_slug}/projects
GET /public/projects/{project_id}

Project gallery must support:

q
track
page
page_size

Example:

GET /public/events/sample-hack-2026/projects?q=signal&track=trk_04&page=1&page_size=20

Search should cover:
- project title
- project summary
- team name

Use backend/database-backed filtering.

DO NOT fetch every project to the browser and filter client-side.

Only return:
- SUBMITTED projects
- from public/published events
- that are eligible for public visibility

Never expose draft data.

Never expose:
- password
- password hash
- sessions
- session tokens
- invite tokens
- private auth metadata
- unpublished drafts
- internal authorization details

Use pagination.

Set a safe server-side maximum page size, for example 50.

Implement proper indexes for:
- event foreign keys
- track foreign keys
- team foreign keys
- submitted status
- timestamps
- common lookup fields

For search:
start with straightforward PostgreSQL-backed matching such as ILIKE.
Do NOT introduce a complicated search engine.
Only add trigram/full-text search if a local benchmark demonstrates it is necessary.

============================================================
12. API DESIGN
============================================================

Use REST.

Keep route handlers/controllers thin.

Business rules belong in services.

Preferred:

Route
  |
  v
Service
  |
  v
Repository
  |
  v
PostgreSQL

Do not put business logic directly in route handlers.

The services must own:
- authorization decisions
- event-state rules
- date/deadline rules
- membership validation
- invitation validation
- project state transitions

At minimum implement:

AUTH:

POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me

EVENTS:

GET    /public/events
GET    /public/events/{event_slug}
POST   /events
GET    /events/{event_id}
PATCH  /events/{event_id}
POST   /events/{event_id}/publish
POST   /events/{event_id}/unpublish
POST   /events/{event_id}/join

TRACKS:

GET    /events/{event_id}/tracks
POST   /events/{event_id}/tracks
PATCH  /tracks/{track_id}
DELETE /tracks/{track_id}

PRIZES:

GET    /events/{event_id}/prizes
POST   /events/{event_id}/prizes
PATCH  /prizes/{prize_id}
DELETE /prizes/{prize_id}

TEAMS:

GET    /teams
POST   /events/{event_id}/teams
GET    /teams/{team_id}
POST   /teams/{team_id}/invites
POST   /teams/join/{token}

PROJECTS:

GET    /submissions
POST   /submissions
GET    /submissions/{project_id}
PATCH  /submissions/{project_id}
POST   /submissions/{project_id}/submit

PUBLIC:

GET    /public/events/{event_slug}/projects
GET    /public/projects/{project_id}

You may add sensible supporting endpoints where needed.

Do not remove required endpoints simply because another route is more elegant.

============================================================
13. AUTHORIZATION MATRIX
============================================================

Backend MUST enforce this.

PARTICIPANT:
- browse public events
- join event
- create own team
- view own team
- generate invite only when captain
- join another team via valid invite
- create own team's project
- edit own team's draft
- submit own team's project
- never create event
- never create prize
- never modify another team's project
- never access another team's draft

JUDGE:
- role must exist
- fixture judges must map to users where possible
- no T2 judging functionality yet
- cannot perform organizer operations

ORGANIZER:
- create/manage events
- configure dates
- manage tracks
- manage prizes
- publish/unpublish events

ADMIN:
- all organizer-level management permissions
- platform administration boundary

Do not infer authorization from frontend route visibility.

Every protected backend endpoint must check authorization.

============================================================
14. FIXTURE IMPORT / SEEDING
============================================================

Create a reproducible seed/import process.

The fixture is external seed data, not source code.

Do not manually copy 40 teams / 41 projects / 30 judges into Python dictionaries.

The fixture loader must:
1. read the fixture file
2. validate its structure
3. upsert/import event
4. import tracks
5. import users referenced by fixture email
6. assign judge roles to judge users
7. import teams
8. resolve team member emails to User IDs
9. import projects
10. preserve submitted_at
11. import judge/score data without exposing T2 functionality
12. preserve original IDs wherever practical
13. maintain foreign-key integrity

The current fixture is expected to contain approximately:
- 1 event
- 8 tracks
- 30 judges
- 40 teams
- 41 projects
- score data

Do NOT assume these numbers are authoritative if the actual fixture differs.
The actual fixture file wins.

The seed process must be IDEMPOTENT.

Running seed twice must not duplicate:
- users
- events
- tracks
- teams
- projects

For local usability, create development seed accounts for:
- one ORGANIZER
- one ADMIN

Use explicit documented local-only credentials via environment/configuration.

Do not require external signup to demonstrate organizer functionality.

Example:
organizer@local.test
admin@local.test

Use a documented dev-only password.

Do not accidentally create these in production mode.

============================================================
15. FRONTEND
============================================================

The frontend is NOT a disposable shell.

It must feel like a real product.

It must connect to the actual REST API.

No hardcoded project arrays.
No hardcoded event records.
No fake login state.
No simulated backend actions.

Every state shown in the UI should come from:
- API response
- authenticated session
- local form state before persistence

------------------------------------------------------------
15.1 VISUAL DIRECTION
------------------------------------------------------------

Use a MODERNISED FRUTIGER AERO aesthetic.

Important:

Do NOT make it look like a 2008 website.

The target is:

FRUTIGER AERO DNA
+
modern product design
+
clean information architecture
+
high usability

Visual language:

- sky
- aqua
- soft blue
- mint
- fresh green
- white
- translucent glass
- subtle gradients
- soft reflections
- subtle glossy surfaces
- organic curves
- very restrained cloud/water/leaf motifs
- clean typography
- generous whitespace
- soft depth
- modern cards

The experience should feel:
- optimistic
- fresh
- polished
- trustworthy
- energetic
- lightweight

Avoid:
- excessive glass everywhere
- giant blobs behind every card
- cartoonish childish illustrations
- neon cyberpunk
- clutter
- excessive animation
- 3D gimmicks that hurt readability
- giant dashboard grids
- excessive rounded containers

FRUTIGER AERO is the visual identity,
not an excuse for visual noise.

------------------------------------------------------------
15.2 LOCAL-FIRST VISUALS
------------------------------------------------------------

No runtime dependency on:
- Google Fonts
- remote icon CDNs
- Unsplash
- Pexels
- external image hosts
- Lottie CDN
- external analytics

Use:
- local fonts if already available
- system font stacks if necessary
- local SVG icons
- CSS-generated decorative shapes
- CSS gradients
- simple local illustrations/assets

Project cards may use:
- uploaded/local thumbnail when supported
- otherwise a deterministic CSS-generated visual based on project information

Do not let an external image failure break the layout.

------------------------------------------------------------
15.3 INFORMATION ARCHITECTURE
------------------------------------------------------------

Keep navigation simple.

PUBLIC:
- Home / Events
- Gallery
- Login
- Register

PARTICIPANT:
- Dashboard
- Events
- My Team
- My Submission

ORGANIZER:
- Dashboard
- Events
- Event Management

Do not create a navigation item for T2 judging because T2 is not implemented.

------------------------------------------------------------
15.4 ROUTES
------------------------------------------------------------

AUTH:

/login
/register

PUBLIC:

/events
/events/:slug
/gallery
/gallery/:projectId

PARTICIPANT:

/dashboard
/teams
/teams/:id
/teams/join/:token
/submissions
/submissions/new
/submissions/:id/edit

ORGANIZER:

/organizer
/organizer/events
/organizer/events/new
/organizer/events/:id
/organizer/events/:id/tracks
/organizer/events/:id/prizes

Use redirects based on actual authenticated role.

Never trust a frontend route guard as a security boundary.

------------------------------------------------------------
15.5 PUBLIC EVENT EXPERIENCE
------------------------------------------------------------

Event page should clearly present:

- event name
- short description if available
- event dates
- registration phase
- submission deadline
- tracks
- prizes
- participation CTA

The deadline should be visually prominent.

A countdown may be used for presentation.

IMPORTANT:
the countdown is NOT enforcement.

The server remains authoritative.

------------------------------------------------------------
15.6 PARTICIPANT DASHBOARD
------------------------------------------------------------

The participant dashboard should answer, at a glance:

"What am I doing right now?"

Show:
- current event(s)
- team status
- teammates
- submission status
- selected track
- deadline
- primary next action

Example state progression:

JOIN EVENT
      ->
CREATE TEAM
      ->
INVITE MEMBERS
      ->
START PROJECT
      ->
SAVE DRAFT
      ->
SUBMIT

Use one clear primary action at a time.

Do not overwhelm the participant with ten equal buttons.

------------------------------------------------------------
15.7 TEAM PAGE
------------------------------------------------------------

Show:
- team name
- captain indicator
- member list
- invite-link section
- copy invite button
- regenerate/revoke invite action
- current event

When user is not captain:
- invite controls should not appear

But remember:
this is UX only.
Backend must also enforce captain-only invitation generation.

Invite URL must never expose the hashed token.

------------------------------------------------------------
15.8 SUBMISSION EDITOR
------------------------------------------------------------

Design the form as a calm multi-section editor.

Sections:

1. Project identity
   - title
   - summary/tagline

2. Description
   - rich enough long-form description

3. Links
   - repository URL
   - demo URL
   - live URL if supported

4. Track
   - event tracks loaded from backend

5. Visuals
   - thumbnail URL if supported
   - optional project media if implemented

Primary actions:

SAVE DRAFT
SUBMIT PROJECT

State indicators:
- Draft
- Saved
- Unsaved changes
- Submitted
- Deadline passed

Do not make autosave mandatory.

Use explicit Save Draft behavior unless the existing codebase already provides reliable autosave.

For unsaved form changes:
- warn before navigation where practical

------------------------------------------------------------
15.9 DEADLINE UX
------------------------------------------------------------

Before deadline:
- normal editing

Near deadline:
- subtle urgency indicator

After deadline:
- lock editing
- explain why
- do not pretend a submission succeeded

If a request fails because the deadline was crossed:
the UI should present the backend's authoritative error.

Never rely solely on a local timer.

------------------------------------------------------------
15.10 ORGANIZER DASHBOARD
------------------------------------------------------------

The organizer should be able to understand the state of an event quickly.

Include:

- events list
- event status
- key dates
- track count
- prize count
- participant/team activity
- publish state

For event management use a clean segmented flow:

EVENT
DATES
TRACKS
PRIZES
PUBLISH

Do not build a complex enterprise admin dashboard.

The goal is:
"An organizer can configure an event without needing a manual."

------------------------------------------------------------
15.11 GALLERY
------------------------------------------------------------

Gallery should feel like a public showcase rather than an admin table.

Features:
- search box
- track filter
- pagination
- project cards
- team name
- track
- summary
- optional thumbnail
- repository/demo links

Search parameters should be reflected in the URL.

Example:

/gallery?q=signal&track=trk_04&page=1

Search must hit the backend.

Use loading states.

Use empty states.

Use error states.

Use pagination.

Do not load every project into the browser.

------------------------------------------------------------
15.12 PROJECT DETAIL
------------------------------------------------------------

Show:

- title
- summary
- full description
- team name
- team members where appropriate
- track
- repository
- demo
- live link if present
- submission timestamp where appropriate

Never expose private draft information.

Never expose auth/session information.

------------------------------------------------------------
16. API CLIENT
============================================================

Create one clean frontend API abstraction.

Do not scatter fetch() calls throughout random components.

Centralize:
- base URL behavior
- credentials
- JSON parsing
- typed responses
- error handling

Use same-origin API routing where practical.

Preferred local architecture:

Browser
   |
   v
Next.js frontend
   |
   | same-origin route/rewrite
   v
FastAPI backend
   |
   v
PostgreSQL

This minimizes browser CORS complexity and keeps cookie sessions straightforward.

If the repository already uses direct API calls, preserve it only if it remains secure and clean.

============================================================
17. ERROR HANDLING
============================================================

Backend errors must be structured.

Use stable error shapes.

Examples:
- unauthenticated
- forbidden
- not found
- validation error
- deadline passed
- invitation expired
- invitation revoked
- already joined
- invalid track
- invalid state transition

Frontend must translate these into useful messages.

Do not show raw Python tracebacks to users.

Development logs can remain detailed server-side.

============================================================
18. DATABASE SAFETY
============================================================

Use:
- foreign keys
- unique constraints
- indexes
- transactions
- timestamps
- enum/check constraints where appropriate

Never rely solely on application-level uniqueness.

Examples:

unique user email
unique event slug
unique (event_id, track name)
unique (team_id, user_id)
unique (event_id, user_id)

Ensure foreign-key deletion behavior is deliberate.

Do not use SQLite fallback.

Do not silently downgrade PostgreSQL-specific behavior.

============================================================
19. DOCKER / LOCAL EXECUTION
============================================================

Primary acceptance requirement:

docker compose up

must produce a working local application.

Target:

WEB       -> localhost:3000
API       -> localhost:8000
POSTGRES  -> internal network

The user should not need:
- cloud credentials
- API keys
- external service accounts

On startup:

1. PostgreSQL becomes healthy
2. backend runs migrations
3. backend seeds fixture data idempotently
4. backend starts
5. frontend becomes available

Use Docker healthchecks.

Do not hide migration or seed failures.

If the database is unavailable:
the backend should fail loudly and clearly rather than silently starting in a broken state.

============================================================
20. OFFLINE REQUIREMENT
============================================================

Runtime must not require internet access.

That means:

After images/dependencies are already available locally:

docker compose up

must work with the network disconnected.

No runtime:
- CDN calls
- Google Fonts
- hosted icons
- auth requests
- cloud DB
- cloud storage
- analytics
- remote config
- external API calls

The UI must still fully function offline.

External URLs such as project repositories may exist as CONTENT,
but their availability must not affect application functionality.

Also create a local preflight/check script that can identify:
- required Docker images
- required local packages
- required fixture files
- required ports

so offline failures are diagnosed quickly.

============================================================
21. MIGRATIONS
============================================================

Use Alembic.

Never rely on:
"create_all()" as the final database setup.

Create an initial clean migration.

Migration lifecycle:

fresh PostgreSQL
    ->
alembic upgrade head
    ->
seed
    ->
working portal

Test this from a completely clean database.

Also test running migrations against an already-seeded fixture database.

============================================================
22. SECURITY BASELINE
============================================================

T1 is not a security hackathon product yet, but basic security cannot be skipped.

Required:

- Argon2id password hashing
- HttpOnly session cookies
- hashed server-side session secrets
- cryptographic invite tokens
- backend RBAC
- ownership checks
- event relationship checks
- input validation
- safe serialization
- no secret leakage
- no password leakage
- no draft leakage
- no token leakage

Mutating cookie-authenticated requests should use:
- SameSite protection
- same-origin behavior
- and/or Origin validation where practical

Do not build a fake security layer in React.

============================================================
23. OBSERVABILITY / LOGGING
============================================================

Keep logging useful but lightweight.

Log:
- application startup
- migrations
- seeding summary
- authentication failures
- important business-rule failures
- unexpected exceptions

Do not log:
- passwords
- session tokens
- invite tokens
- password hashes

Provide a simple health endpoint such as:

GET /health

It should indicate:
- API alive
- database reachable

Do not make the health endpoint depend on external internet access.

============================================================
24. T2/T3/T4 BOUNDARY
============================================================

DO NOT IMPLEMENT:

T2:
- judge assignment
- judge console
- scoring UI
- weighted rubric evaluation
- cross-judge normalization
- score normalization algorithms

T3:
- community voting
- quadratic voting
- vote abuse controls
- comments

T4:
- full API-first bonus implementation
- webhooks
- certificates
- public judge signatures
- embeddable widget
- bulk migration tools

However, preserve the architectural boundary so T2 can later consume:

Projects
Tracks
Users
Judges
Events

without rewriting T1.

Create lightweight module placeholders for:
- judging
- voting

Do not put placeholder fake logic into them.

============================================================
25. TESTING IS PART OF THE BUILD
============================================================

THIS SECTION IS NON-NEGOTIABLE.

Do not build the entire application first and "test at the end."

Build in vertical slices.

After EACH slice:

1. run the relevant tests
2. inspect failures
3. fix root cause
4. rerun the failed test
5. rerun the relevant full suite
6. only then continue

Never knowingly carry a broken earlier slice into the next stage.

============================================================
26. TEST LOOP 0 — INFRASTRUCTURE
============================================================

Before feature work:

Run:

docker compose config

Verify:
- services resolve
- environment variables resolve
- volumes are sane
- healthchecks exist

Then:

docker compose up -d

Verify:
- postgres healthy
- backend healthy
- frontend accessible

Verify:

GET /health

Then destroy/recreate the DB volume and prove the project can bootstrap again.

Expected result:
a new machine with the repository can reproduce a working local environment.

============================================================
27. TEST LOOP 1 — MIGRATION + SEED
============================================================

Start from a clean PostgreSQL volume.

Run migrations.

Run seed.

Run seed AGAIN.

Verify:
- no duplicate events
- no duplicate tracks
- no duplicate users
- no duplicate teams
- no duplicate projects
- foreign keys remain valid

Count and compare the imported fixture data with the fixture itself.

Do not merely check that "some rows exist."

Verify relationships.

============================================================
28. TEST LOOP 2 — AUTHENTICATION
============================================================

Test:

register
login
me
logout

Verify:

- correct password works
- incorrect password fails
- session persists
- logout invalidates session
- expired/revoked session fails
- password is hashed
- password never appears in API response

Also test:
- duplicate email
- malformed email
- weak password
- unauthenticated protected endpoint

============================================================
29. TEST LOOP 3 — ROLE ISOLATION
============================================================

Create users for:

participant
judge
organizer
admin

Test direct HTTP/API access.

Examples:

PARTICIPANT attempts:
POST /events
POST prize
modify another team's submission

must fail.

JUDGE attempts:
create event
edit event
create prize

must fail.

ORGANIZER:
must succeed for organizer operations.

ADMIN:
must succeed for admin-level management.

Do not test only frontend visibility.

Use actual HTTP requests against the backend.

============================================================
30. TEST LOOP 4 — EVENT CREATION
============================================================

Create a new event as organizer.

Configure:
- name
- slug
- registration dates
- event dates
- submission dates

Create:
- tracks
- prizes

Publish event.

Verify:
- event exists in PostgreSQL
- track rows reference correct event
- prize rows reference correct event
- public event endpoint can access it
- unpublished event is not public
- published event is public

Also test invalid date configurations.

============================================================
31. TEST LOOP 5 — EVENT JOIN
============================================================

As participant:

join event

Verify:
- event_participants row exists
- duplicate join is handled safely
- participant can now create a team

Test behavior when registration is closed.

Verify backend rejection.

Do not rely on button disabling.

============================================================
32. TEST LOOP 6 — TEAM FLOW
============================================================

As participant:

create team

Verify:
- correct event
- correct creator
- creator becomes captain

Generate invite.

Verify:
- raw token is only in the generated link
- database stores hash
- token cannot be predicted
- unauthorized user cannot generate invites
- regenerated invite invalidates previous invite

Open invite in a separate browser context/user session.

Authenticate.

Join.

Verify:
- member is inserted once
- duplicate join is handled
- team is preserved
- event relationship remains valid

Test expired/revoked invite behavior.

============================================================
33. TEST LOOP 7 — CROSS-TEAM ISOLATION
============================================================

Create:

Team A
Team B

Create:

Project A
Project B

As Team A member attempt:

GET Project B
PATCH Project B
SUBMIT Project B

Every unauthorized operation must fail.

Then attempt:

Team A project
+
Track from another event

Must fail.

Then attempt:
Team A project
+
Track from same event

Must work.

============================================================
34. TEST LOOP 8 — DRAFT FLOW
============================================================

Create project.

Verify:
status = DRAFT
submitted_at = null

Save changes.

Reload the page.

Verify:
changes persist.

Edit again.

Reload.

Verify:
changes persist.

Verify:
draft is NOT in public gallery.

============================================================
35. TEST LOOP 9 — SUBMISSION DEADLINE
============================================================

Create an event with a controlled test clock.

Test:

BEFORE DEADLINE:
- create project
- edit project
- submit project

All should succeed.

Move test clock AFTER deadline.

Attempt:
- edit draft
- create submission
- submit draft

All must fail according to policy.

Do this through direct API requests.

Do not merely test the frontend.

============================================================
36. TEST LOOP 10 — SUBMISSION STATE TRANSITION
============================================================

Verify:

DRAFT
 ->
SUBMITTED

On success:
- exactly one state transition
- submitted_at populated by server
- timestamp is UTC
- project becomes public

Attempt to submit twice.

Verify:
second transition is rejected or idempotently handled.

Do not allow:
SUBMITTED -> DRAFT
unless an explicitly justified T1 editing policy exists.

Keep the state machine intentionally small.

============================================================
37. TEST LOOP 11 — GALLERY SEARCH
============================================================

Seed/create multiple submitted projects with:
- distinct titles
- distinct summaries
- distinct teams
- multiple tracks

Verify:

q searches:
- title
- summary
- team name

track filters correctly.

pagination works.

page_size is bounded.

drafts never appear.

Unpublished events never appear publicly.

Project details resolve correctly.

Also test zero-result state.

============================================================
38. TEST LOOP 12 — PUBLIC DATA LEAKAGE
============================================================

Inspect public API responses.

Assert that public payloads do NOT contain:

password
password_hash
session token
invite token
token hash
internal role metadata
private draft fields
unpublished submissions

Do not assume serialization is secure.

Write an automated test that checks the JSON response.

============================================================
39. TEST LOOP 13 — FRONTEND E2E
============================================================

Use Playwright against the running local application.

Test the actual browser workflow:

1. open application
2. login as organizer
3. create event
4. configure dates
5. create track
6. create prize
7. publish event
8. logout
9. register/login as participant
10. join event
11. create team
12. generate invite
13. open invite as second participant
14. join team
15. create project
16. save draft
17. reload
18. edit draft
19. submit
20. visit public gallery
21. search project
22. filter by track
23. open project details

This is the golden-path test.

No step may be simulated with hardcoded frontend state.

============================================================
40. TEST LOOP 14 — FAILURE/EDGE CASE UX
============================================================

Test browser behavior for:

- invalid login
- unauthorized route
- expired invite
- revoked invite
- duplicate team join
- duplicate email
- empty gallery
- no search results
- expired submission deadline
- invalid track
- missing required fields
- API unavailable
- stale session

The application should fail gracefully.

Do not leave blank screens.

Do not leave infinite spinners.

============================================================
41. TEST LOOP 15 — CLEAN MACHINE TEST
============================================================

This is the final "works on my machine" killer test.

Assume:
- fresh environment
- no local app process
- empty PostgreSQL volume
- no seeded database
- network disconnected AFTER required Docker assets are present

Run:

docker compose up

Then verify:

1. database initializes
2. migrations run
3. fixture seeds
4. backend starts
5. frontend starts
6. login works
7. event creation works
8. team creation works
9. submission works
10. gallery works

If any of those fail, the implementation is NOT done.

============================================================
42. NO-HALLUCINATION BUILD LOOP
============================================================

You are forbidden from claiming:

"implemented"
"working"
"tested"
"fixed"

unless the corresponding command has actually been executed.

Whenever a test fails:

DO NOT:
- ignore it
- disable the test
- weaken the assertion
- hide the exception
- replace the real DB with a mock
- change the requirement simply to make the test green

Instead:

1. capture the exact failure
2. identify root cause
3. change the smallest correct piece
4. rerun the failed test
5. rerun the regression suite

If a library behaves differently than expected:
inspect the installed version and actual documentation/source rather than guessing.

If an API contract fails:
inspect request/response payloads.

If a database relationship fails:
inspect the actual row state.

If frontend state is wrong:
inspect the actual network request and API payload.

Evidence beats assumption.

============================================================
43. ACCEPTANCE AUTOMATION
============================================================

Create:

scripts/check_t1.*

This script should run the local T1 verification sequence.

The exact language can be bash/python/node depending on the project.

It should verify:

- infrastructure
- health
- migration
- seed
- authentication
- roles
- event creation
- tracks
- prizes
- event join
- teams
- invites
- submission drafts
- deadline enforcement
- submission transition
- gallery
- search
- public data isolation
- frontend golden path if practical

Output clear PASS/FAIL information.

Also create:

acceptance-report.txt

with:
- timestamp
- environment
- test commands
- results
- T1 status

DO NOT fabricate an "official acceptance suite" result if the official suite is not actually present.

If the official acceptance suite exists in the repository:
run it.

If it does not exist:
create an INTERNAL T1 verification suite and clearly label it as such.

Never misrepresent a self-authored test as an official judge result.

============================================================
44. DOCUMENTATION
============================================================

README.md

Must explain:

- what the project is
- architecture
- how to start
- how to stop
- local URLs
- seeded accounts
- fixture import
- migrations
- tests
- T1 scope
- known limitations
- what is intentionally deferred

The first setup path should be obvious.

ARCHITECTURE.md

Document:

frontend
  ->
REST API
  ->
modular monolith
  ->
PostgreSQL

Explain module boundaries.

Explain why this is a modular monolith and not microservices.

Explain request flow:

route
 ->
service
 ->
repository
 ->
database

Explain T2/T3/T4 future boundaries.

DATA-MODEL.md

Document:
- entities
- relationships
- important constraints
- foreign keys
- fixture mapping
- import process
- export considerations

JUDGING.md

DO NOT INVENT T2 MATH.

State:
- T2 is deferred
- judging entities are preserved from the fixture
- no scoring UI is currently implemented
- the T1 architecture is deliberately ready for future judging

.dogfood.toml

Claim ONLY the tier actually implemented and verified.

Do not claim T2/T3/T4.

LICENSE

Use MIT unless the existing repository already has an OSI-approved license that should be preserved.

============================================================
45. PRODUCT POLISH
============================================================

The product should not feel like:

"CRUD app with pastel colors."

The frontend must communicate a coherent product model.

Public:
DISCOVER

Participant:
BUILD

Organizer:
RUN

A user should be able to understand:
- what event they're in
- what their team is doing
- whether their project is a draft
- what the deadline is
- whether they are submitted
- where their work appears publicly

Use visual hierarchy rather than adding more UI.

Prefer:
- one strong primary CTA
- compact secondary actions
- status chips
- timeline/date presentation
- subtle microinteractions
- predictable forms

Use animations sparingly:
- page entrance
- hover
- button feedback
- subtle background motion

Respect prefers-reduced-motion.

Use accessible:
- contrast
- labels
- focus states
- keyboard navigation
- semantic headings
- aria attributes where appropriate

============================================================
46. PERFORMANCE
============================================================

Do not optimize prematurely.

But do not build obviously inefficient behavior.

Avoid:
- fetching all projects for gallery
- polling without reason
- giant client-side datasets
- repeated duplicate API calls
- rendering unnecessary full dashboards

Use:
- pagination
- server-side filtering
- sensible caching only where simple
- database indexes
- stable API calls

============================================================
47. FILE / CODE QUALITY
============================================================

Prefer:
- small cohesive modules
- typed request/response models
- service-layer business rules
- repository abstractions
- explicit schemas
- descriptive names
- useful comments only where reasoning is non-obvious

Avoid:
- 2000-line components
- giant route handlers
- duplicate auth logic
- duplicate validation
- magic strings scattered everywhere
- hardcoded fixture IDs
- hardcoded role checks throughout JSX

Centralize:
- auth dependencies
- role guards
- API client
- date formatting
- common UI primitives
- error handling

============================================================
48. WHAT NOT TO DO
============================================================

DO NOT:

- build a static mockup
- hardcode fixture data into React
- create fake login
- store plaintext passwords
- store session tokens in localStorage
- trust frontend role checks
- use SQLite
- use Firebase
- use Supabase
- use hosted Postgres
- use Redis
- call module APIs over HTTP internally
- create microservices
- build T2 judging UI
- build T3 voting UI
- build T4 features
- add LLM functionality
- add unnecessary AI
- add external APIs
- add unnecessary infrastructure
- introduce Kubernetes
- add a message queue
- create a full-text search engine
- create a giant admin panel
- create giant multi-step forms without reason
- silently swallow backend errors
- weaken tests to make CI green
- fabricate acceptance results
- claim offline compatibility without actually testing local execution
- overwrite the fixture because its data is inconvenient
- delete judge/score data simply because judging is deferred

============================================================
49. EXECUTION ORDER
============================================================

Build in this exact order unless repository constraints demand a small change:

PHASE 0
Repository inspection + fixture inspection

PHASE 1
Database schema + migrations + fixture import

PHASE 2
Authentication + sessions + roles

PHASE 3
Events + dates + publication

PHASE 4
Tracks + prizes

PHASE 5
Event participation

PHASE 6
Teams + team membership

PHASE 7
Secure invitations

PHASE 8
Projects + draft editing

PHASE 9
Deadline enforcement + submission transition

PHASE 10
Public gallery + search + filters + pagination

PHASE 11
Participant UI

PHASE 12
Organizer UI

PHASE 13
Public gallery UI

PHASE 14
End-to-end Playwright workflow

PHASE 15
Security/authorization regression suite

PHASE 16
Offline/local reproducibility verification

PHASE 17
Documentation + acceptance report

After EVERY phase:
RUN TESTS.

Do not stack unfinished phases.

============================================================
50. DEFINITION OF DONE
============================================================

T1 IS DONE ONLY WHEN ALL OF THE FOLLOWING ARE TRUE:

[ ] PostgreSQL-backed relational schema exists
[ ] Alembic migrations work from empty DB
[ ] fixture importer exists
[ ] fixture seeds successfully
[ ] seed is idempotent
[ ] authentication works
[ ] secure password hashing works
[ ] DB-backed sessions work
[ ] logout/revocation works
[ ] PARTICIPANT role exists
[ ] JUDGE role exists
[ ] ORGANIZER role exists
[ ] ADMIN role exists
[ ] backend RBAC is enforced
[ ] event creation works
[ ] event editing works
[ ] configurable dates work
[ ] event publish/unpublish works
[ ] tracks work
[ ] prizes work
[ ] event joining works
[ ] teams work
[ ] team membership is normalized
[ ] captain role works
[ ] invitation links work
[ ] invite tokens are cryptographically random
[ ] invite tokens are not stored raw
[ ] project creation works
[ ] drafts work
[ ] draft editing works
[ ] deadline enforcement is server-side
[ ] submission transition is atomic
[ ] submitted_at is server-generated
[ ] submitted projects are public
[ ] drafts are never public
[ ] cross-team authorization tests pass
[ ] cross-event validation tests pass
[ ] gallery works
[ ] gallery search works
[ ] gallery filtering works
[ ] gallery pagination works
[ ] project detail works
[ ] public responses contain no private secrets
[ ] UI uses real APIs
[ ] UI is responsive
[ ] Frutiger Aero modernised visual system is cohesive
[ ] accessibility basics are implemented
[ ] no runtime external service dependency exists
[ ] docker compose up works
[ ] clean DB bootstrap works
[ ] local fixture bootstrap works
[ ] frontend E2E passes
[ ] backend integration tests pass
[ ] role isolation tests pass
[ ] deadline tests pass
[ ] acceptance verification is recorded
[ ] README exists
[ ] ARCHITECTURE.md exists
[ ] DATA-MODEL.md exists
[ ] JUDGING.md exists
[ ] LICENSE exists
[ ] .dogfood.toml exists
[ ] T2/T3/T4 are NOT falsely claimed as implemented

============================================================
51. FINAL SELF-REVIEW BEFORE YOU STOP
============================================================

Before declaring completion, act as three different reviewers.

REVIEWER A — ORGANIZER

Ask:

"Can I run this on a laptop, create an event, configure it, publish it, and operate it without asking the developers what to click?"

If not:
fix it.

REVIEWER B — SECURITY REVIEWER

Ask:

"Can a participant modify another team's project by changing an ID in the API request?"

If yes:
fix it.

"Can a judge invoke organizer endpoints?"

If yes:
fix it.

"Can a public request retrieve a draft?"

If yes:
fix it.

"Can an invite token be guessed or leaked?"

If yes:
fix it.

REVIEWER C — HACKATHON JUDGE

Ask:

"Can I clone the repository, start it locally, use the seeded data, exercise the T1 workflow, and understand what is implemented without reading the application source line by line?"

If not:
fix the repository and documentation.

============================================================
52. FINAL COMMAND SEQUENCE
============================================================

Before completion, actually execute the equivalent of:

docker compose down -v

docker compose up --build -d

run migrations / verify migrations

run seed

run backend unit tests

run backend integration tests

run frontend typecheck

run frontend lint

run frontend tests

run Playwright E2E

run role-isolation tests

run deadline tests

run public-data-leakage tests

run T1 verification script

generate acceptance-report.txt

Then inspect the running app manually through the browser.

Finally:

docker compose down

docker compose up -d

Verify it still starts cleanly.

ONLY AFTER ALL OF THAT may you declare the implementation complete.

============================================================
53. MOST IMPORTANT ENGINEERING PRINCIPLE
============================================================

Build the smallest system that is genuinely correct.

Do not confuse:
more features
with
better product.

The priority order is:

1. CORRECTNESS
2. SECURITY / AUTHORIZATION
3. DATA INTEGRITY
4. DEADLINE ENFORCEMENT
5. END-TO-END FLOW
6. LOCAL OPERABILITY
7. UX POLISH
8. VISUAL DISTINCTIVENESS

The frontend must make the product pleasant.

The backend must make the product trustworthy.

The database must make the state real.

The tests must prove the three agree.

The final result should feel like a real hackathon platform,
not a hackathon prototype.

BUILD IT.
RUN IT.
TEST IT.
BREAK IT.
FIX IT.
RUN IT AGAIN.

Do not stop at generated code.