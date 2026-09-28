"""Judge/crowd blend persistence: organizer-owned weights plus per-run
blended score/rank columns. All nullable/additive — blend-off runs write
NULLs and behave exactly as before.

Revision ID: 0018_blend
Revises: 0017_profile
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_blend"
down_revision = "0017_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("crowd_blend_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("events", sa.Column("crowd_weight", sa.Float(), nullable=False, server_default="30"))
    op.add_column("model_project_results", sa.Column("blended_score", sa.Float(), nullable=True))
    op.add_column("model_project_results", sa.Column("blended_rank", sa.Integer(), nullable=True))
    op.add_column("bayes_project_results", sa.Column("blended_score", sa.Float(), nullable=True))
    op.add_column("bayes_project_results", sa.Column("blended_rank", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("bayes_project_results", "blended_rank")
    op.drop_column("bayes_project_results", "blended_score")
    op.drop_column("model_project_results", "blended_rank")
    op.drop_column("model_project_results", "blended_score")
    op.drop_column("events", "crowd_weight")
    op.drop_column("events", "crowd_blend_enabled")
