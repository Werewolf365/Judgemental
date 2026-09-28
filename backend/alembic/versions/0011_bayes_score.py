"""Hierarchical Bayesian scoring results (single-judge-per-project edge case).

New tables (shares model_runs with Crowd-BT, distinguished by model_version):
- bayes_project_results: per-project posterior summary per run (score
  mean/sd, likely range, rank, Top-K probability, confidence).
- bayes_judge_effects: posterior judge severity/leniency per run.

Revision ID: 0011_bayes_score
Revises: 0010_avatar
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_bayes_score"
down_revision = "0010_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bayes_project_results",
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("score_mean", sa.Float(), nullable=False),
        sa.Column("score_sd", sa.Float(), nullable=False),
        sa.Column("score_lo", sa.Float(), nullable=False),
        sa.Column("score_hi", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("p_top_k", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False, server_default="Low"),
    )
    op.create_table(
        "bayes_judge_effects",
        sa.Column("model_run_id", sa.Text(), sa.ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("judge_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("b_mean", sa.Float(), nullable=False),
        sa.Column("b_sd", sa.Float(), nullable=False),
        sa.Column("n_evaluations", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("bayes_judge_effects")
    op.drop_table("bayes_project_results")
