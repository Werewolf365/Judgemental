"""Per-event timezone for deadline input.

submissions_close stays UTC in storage; `timezone` records the IANA zone
the organizer entered the deadline in, so the console can round-trip the
wall-clock value. Defaults to UTC, so existing rows need no backfill.

Revision ID: 0014_event_timezone
Revises: 0013_theta_std
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_event_timezone"
down_revision = "0013_theta_std"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"))


def downgrade() -> None:
    op.drop_column("events", "timezone")
