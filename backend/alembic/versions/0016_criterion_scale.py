"""Per-criterion scoring scale (migration 0016).

Adds rubric_criteria.score_lo/score_hi (default 0/10, CHECK hi > lo) so a
rubric can declare any scale. Scores validate into the declared range at
input; normalization divides by it before weighting, keeping mixed-scale
rubrics comparable. Existing rows backfill to 0/10, under which every
formula in the codebase reduces exactly to its previous behavior.

Revision ID: 0016_criterion_scale
Revises: 0015_confidence_nullable
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_criterion_scale"
down_revision = "0015_confidence_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rubric_criteria",
                  sa.Column("score_lo", sa.Float(), nullable=False, server_default="0"))
    op.add_column("rubric_criteria",
                  sa.Column("score_hi", sa.Float(), nullable=False, server_default="10"))
    op.create_check_constraint("ck_rubric_scale_order", "rubric_criteria",
                               "score_hi > score_lo")


def downgrade() -> None:
    op.drop_constraint("ck_rubric_scale_order", "rubric_criteria", type_="check")
    op.drop_column("rubric_criteria", "score_hi")
    op.drop_column("rubric_criteria", "score_lo")
