"""Organizer manual rank overrides for Bayesian scoring runs.

One table: each swap writes a full per-project snapshot for the run, so the
effective ranking is always exactly the latest snapshot. Clearing the rows
reverts to the model ranking.

Revision ID: 0012_bayes_overrides
Revises: 0011_bayes_score
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_bayes_overrides"
down_revision = "0011_bayes_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bayes_rank_overrides",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_rank", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("model_run_id", "project_id", name="uq_bayes_override_run_project"),
        sa.UniqueConstraint("model_run_id", "manual_rank", name="uq_bayes_override_run_rank"),
    )


def downgrade() -> None:
    op.drop_table("bayes_rank_overrides")
