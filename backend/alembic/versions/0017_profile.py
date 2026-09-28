"""Reusable registration profile on users (migration 0017).

Event registration asks for the same generic contact/academic details every
time (phone, age, degree, year, institution, t-shirt, dietary). These columns
let a user save them once on their profile: the registration form prefills
from them (still editable per event), and submitting a registration writes
the values back, so filling one event's form counts as updating the profile.

Revision ID: 0017_profile
Revises: 0016_criterion_scale
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_profile"
down_revision = "0016_criterion_scale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_phone", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("profile_age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("profile_degree", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("profile_year", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("profile_institution", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("profile_tshirt", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("profile_dietary", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("profile_dietary", "profile_tshirt", "profile_institution",
                "profile_year", "profile_degree", "profile_age",
                "profile_phone"):
        op.drop_column("users", col)
