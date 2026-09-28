# Community Voting (T3)

Public, quadratic, organizer-controlled. Judging (scores, rubrics,
Crowd-BT) is a separate system documented in JUDGING.md — nothing here
feeds it, and nothing there feeds this.

## The one-paragraph model

Each event may open a **ballot box**. Every voter gets **10 votes** to
spread across any number of projects (never more than 10 total). Influence
follows a square-root curve — n votes on one project carry √n influence —
so piling everything onto one project gains less than broad support
(√9 + √1 beats √10 every time). The leaderboard sums influence per
project. Results stay hidden until the organizer's deadline passes.

## Organizer controls (console Step 7 — Voting)

- **Accept public votes** on/off (default off).
- **Who may vote**: open link (client UUID, weakest identity), email-gated
  (one ballot set per address), or authenticated (logged-in users only,
  with own-team votes blocked).
- **Voting ends**: UTC deadline, blank means open-ended.
- **Comments**: public (everyone reads) or team-only (each project's team
  plus organizers). Posting always needs a login.
- **Turnout**: distinct voters, ballot count, shared-device signals.
- **Event audit trail**: every vote, refusal, and moderation action,
  readable in the console — no database client needed.

Drafts are staff-only across the whole voting surface, same as the gallery.

## Anti-abuse

1. **Math cap**: the quadratic budget makes floods expensive by construction.
2. **One cell per (voter, project)** (unique constraint); re-votes update.
3. **Rate limits**: in-memory token buckets (30 ballot/min, 20 comment/min
   per IP-or-user, env-overridable); refusals are 429s and audited.
4. **Duplicate signals**: IP+agent fingerprints surfaced as collision
   counts for organizers — advisory, never auto-blocking.
5. **Own-team block** for logged-in voters.

Single worker is assumed (stock uvicorn); each worker would carry its own
bucket, erring generous rather than blocking legit traffic.

## Verification

- `backend/app/modules/voting/tests/test_quadratic.py` — budgets, validation, tally order.
- `scripts/check_t3.py` — full live lifecycle on a per-run probe event.
