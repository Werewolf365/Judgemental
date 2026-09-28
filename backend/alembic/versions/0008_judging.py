"""T2 judging tables + event judging configuration.

New tables (all judge identity is users.id — see context.md §17/D1):
- rubric_criteria: organizer-defined weighted criteria per event.
- event_judges: per-event judge roster (removal deactivates, never deletes).
- judge_assignments: judge→project work items with ASSIGNED/IN_PROGRESS/
  COMPLETED/REVOKED lifecycle and a partial unique index so the same live
  pair can never exist twice (DB-level assignment idempotency).
- evaluations: one rubric-score record per assignment (DRAFT→SUBMITTED).
- judge_reliability_history: per-judge posterior per model run; the latest
  row becomes the prior of the judge's next competition.
- model_runs / model_project_results / model_judge_results /
  pairwise_observations: reproducible Crowd-BT run storage. The pairwise
  weight is CHECK-constrained to 1 (unit-weighted evidence invariant).
- events gains judging_open/judging_close/judges_per_project/rolling_judging.

Revision ID: 0008_judging
Revises: 0007_audit_log
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_judging"
down_revision = "0007_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("event_id", "name", name="uq_rubric_event_name"),
    )
    op.create_table(
        "event_judges",
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("assigned_by", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "judge_assignments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.Enum("ASSIGNED", "IN_PROGRESS", "COMPLETED", "REVOKED",
                                    name="assignment_status"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial unique index: one live row per (project, judge). REVOKED rows
    # are excluded so a re-added judge can hold a new row for the same
    # project. (A unique Index, not a UniqueConstraint — SQLAlchemy only
    # accepts postgresql_where on Index — with identical enforcement.)
    op.create_index(
        "uq_assignment_project_judge_active", "judge_assignments",
        ["project_id", "judge_user_id"], unique=True,
        postgresql_where=sa.text("status <> 'REVOKED'"),
    )
    op.create_index("ix_assignments_event_status", "judge_assignments", ["event_id", "status"])
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("assignment_id", sa.Text(), sa.ForeignKey("judge_assignments.id", ondelete="CASCADE"),
                  nullable=False, unique=True, index=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("scores", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("DRAFT", "SUBMITTED", name="evaluation_status"), nullable=False, index=True),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "model_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_version", sa.Text(), nullable=False, server_default="crowd-bt-map-v1"),
        sa.Column("status", sa.Enum("RUNNING", "SUCCEEDED", "FAILED", name="model_run_status"),
                  nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("n_projects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_judges", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_comparisons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_table(
        "model_project_results",
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("theta", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
    )
    op.create_table(
        "model_judge_results",
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("r", sa.Float(), nullable=False),
        sa.Column("prior_mu", sa.Float(), nullable=False),
        sa.Column("prior_sigma", sa.Float(), nullable=False),
        sa.Column("posterior_mu", sa.Float(), nullable=False),
    )
    op.create_table(
        "judge_reliability_history",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("posterior_mu", sa.Float(), nullable=False),
        sa.Column("posterior_sigma", sa.Float(), nullable=True),
        sa.Column("r", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("model_run_id", "judge_user_id", name="uq_relhist_run_judge"),
    )
    op.create_table(
        "pairwise_observations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("winner_project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("loser_project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("source_evaluation_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.CheckConstraint("weight = 1", name="ck_pairwise_unit_weight"),
    )
    op.add_column("events", sa.Column("judging_open", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("judging_close", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("judges_per_project", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("events", sa.Column("rolling_judging", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("events", "rolling_judging")
    op.drop_column("events", "judges_per_project")
    op.drop_column("events", "judging_close")
    op.drop_column("events", "judging_open")
    op.drop_table("pairwise_observations")
    op.drop_table("judge_reliability_history")
    op.drop_table("model_judge_results")
    op.drop_table("model_project_results")
    op.drop_table("model_runs")
    op.drop_table("evaluations")
    op.drop_index("ix_assignments_event_status", table_name="judge_assignments")
    op.drop_index("uq_assignment_project_judge_active", table_name="judge_assignments")
    op.drop_table("judge_assignments")
    op.drop_table("event_judges")
    op.drop_table("rubric_criteria")
    # PG enum types left behind by the table drops (matches 0001 behavior,
    # which also leaves its types in place on downgrade).
    for name in ("assignment_status", "evaluation_status", "model_run_status"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
