# DATA-MODEL

Normalized Postgres (Alembic `0001_initial`). Key constraints: unique
`users.email_norm`, `events.slug`, `(event_id, track name)`,
`(team_id, user_id)`, `(event_id, user_id)`, `(judge_id, project_id)`.

- users(id, email, email_norm unique, password_hash Argon2id, display_name, role)
- sessions(id, user_id, token_hash unique, expires_at, revoked_at)
- events(id e.g. evt_01, slug unique, name, 6 nullable UTC dates, status DRAFT/PUBLISHED/COMPLETED, gallery_visibility PUBLIC/PARTICIPANTS/ORGANIZERS_ONLY default PUBLIC, created_by -> users)
- event_organizers(event_id, user_id, assigned_by?, created_at) — who may manage an event. Creator is inserted as the first row; ADMIN bypasses per-event scoping.
- event_participants(event_id, user_id)
- tracks(id e.g. trk_01, event_id, name unique-per-event, is_active)
- prizes(id, event_id, track_id?, name, description, value_desc, display_order)
- teams(id e.g. tm_01, event_id, name, created_by)
- team_members(team_id, user_id, role CAPTAIN/MEMBER)
- team_invites(id, team_id, token_hash unique, created_by, expires/used/revoked_at)
- projects(id e.g. prj_01, event_id, team_id, track_id, title, summary, description?, repo/demo/live/thumbnail?, status DRAFT/SUBMITTED, is_visible moderation flag default true, custom_data JSON answers `{field_id: value}` default {}, submitted_at server-UTC)
- event_form_fields(id e.g. fld_xxxx, event_id, label, field_type text/textarea/number/url/select, required bool, options JSON list for select)
- judges(id e.g. jdg_01, name, email) + judge_tracks(judge_id, track_id)
- scores(id, judge_id, project_id unique-pair, criteria JSON, comment)
- audit_log(id, created_at, actor_id?, actor_email?, action, target_type?, target_id?, event_id?, detail JSON, ip?) — append-only, ADMIN-readable. Actor columns are plain text, not FKs, so the trail survives account deletion.

Fixture mapping: `fixtures.json` event/tracks/teams/projects/scores/judges
imported by `backend/app/seed.py` with original string IDs preserved and
upsert-idempotent. Team `members[]` normalized to `team_members`
(first = CAPTAIN). Projects seed as SUBMITTED with fixture `submitted_at`.
