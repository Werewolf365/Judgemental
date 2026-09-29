# DATA-MODEL

Normalized Postgres (Alembic `0001_initial`). Key constraints: unique
`users.email_norm`, `events.slug`, `(event_id, track name)`,
`(team_id, user_id)`, `(event_id, user_id)`, `(judge_id, project_id)`.

- users(id, email, email_norm unique, password_hash Argon2id, display_name, avatar_url data-URL nullable, role, profile_* nullable registration details: phone/age/degree/year/institution/tshirt/dietary)
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

T2 judging (migration `0008_judging`; judge identity is `users.id`
throughout, never the fixture `judges.id` rows — see context.md §17/D1.
The fixture `judges`/`scores`/`judge_tracks` tables stay as seeded legacy):

- events += judging_open, judging_close (nullable UTC), judges_per_project int default 2, rolling_judging bool default true
- rubric_criteria(id, event_id, name unique-per-event, description?, weight float nullable, display_order, is_active, score_lo/hi float default 0/10 with CHECK hi > lo)
- event_judges(event_id, user_id, is_active, assigned_by?) — organizer-roster pattern; removal deactivates, never deletes
- judge_assignments(id, event_id, project_id, judge_user_id, status ASSIGNED/IN_PROGRESS/COMPLETED/REVOKED, completed_at?) + partial unique index (project_id, judge_user_id) WHERE status <> 'REVOKED'
- evaluations(id, assignment_id unique, event_id, project_id, judge_user_id, scores JSON {criterion_id: number}, comment?, status DRAFT/SUBMITTED, weighted_score snapshot, submitted_at?)
- model_runs(id, event_id, model_version, status RUNNING/SUCCEEDED/FAILED, started/finished_at, config JSON snapshot, n_projects/judges/comparisons, error?)
- model_project_results(model_run_id, project_id, theta, rank) + model_judge_results(model_run_id, judge_user_id, r, prior_mu/sigma, posterior_mu)
- judge_reliability_history(id, judge_user_id, event_id, model_run_id, posterior_mu, posterior_sigma NULL under MAP, r) — latest row per judge is the next competition's prior
- pairwise_observations(id, model_run_id, judge_user_id, winner/loser project_id, weight CHECK = 1, source_evaluation_ids JSON)

T2b Bayesian scoring edge case (migration `0011_bayes_score`; shares `model_runs`,
distinguished by `model_version = hier-bayes-score-v2` (v1 rows remain readable):

- bayes_project_results(model_run_id, project_id, score_mean/sd/lo/hi, rank, p_top_k, confidence High/Medium/Low)
- bayes_judge_effects(model_run_id, judge_user_id, b_mean/sd, n_evaluations) — posterior severity/leniency, shrunk toward 0 when evidence is thin
- bayes_rank_overrides(id, model_run_id, project_id, manual_rank 1..P, reason?, created_by?) — organizer rank swaps; full snapshot per run, unique (run, rank); empty means model order stands

T3 voting (migration `0009_voting`):

- events += voting_enabled bool default false, voting_close nullable UTC, voting_mode text default 'auth' (auth/email/open), comments_visibility text default 'public' (public/team)
- ballots(id, event_id, voter_key, project_id, votes int, fp_hash?, created_at/updated_at) + unique (event_id, voter_key, project_id); voter_key is `user:<id>`, `email:<addr>` or `anon:<uuid>`
- comments(id, event_id, project_id, author_user_id, body ≤2000, is_hidden, created_at) — hidden, never deleted
- security_flags(id, event_id, kind, subject_type, subject, detail JSON, status open/blocked/dismissed, created/updated) + unique (event_id, kind, subject); repeats reopen
- security_blocks(id, event_id, target_type user/voter/ip, target, reason?, created_by?, created_at, revoked_at?) — enforced on ballot casts + comment posts

T4 certificates (migration `0019_certificates`):

- certificate_templates(id, event_id unique, image data: URL ≤2MB, updated_by?, created_at/updated_at) — organizer-uploaded base; participant details overlay at render
- certificates(id, event_id, user_id, kind WINNER/PARTICIPATION, project_id?, team_name?, rank?, code unique, issued_at) + unique (event_id, user_id) — issued lazily on first view after results declared; WINNER = rank-1 team member (blended-aware order)

T4 bulk transfer is stateless (no tables): `GET /events/{id}/export` (ZIP of 14 CSVs) and `POST /events/{id}/import` (create-only tracks/prizes/rubric/judges/organizers), both organizer-only and event-scoped.
