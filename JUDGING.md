# JUDGING (T2 — deferred)

T2 is NOT implemented. No judge console, scoring UI, assignment, weighting,
normalization, or CSV export exists. Fixture `judges` and `scores` rows are
preserved in Postgres (`judges`, `judge_tracks`, `scores` tables) so T2 can
later build on T1's projects/tracks/users/events without rework.
`backend/app/modules/judging/` is an intentional boundary placeholder.
