"""Explicit abuse flags + blocks (migration 0021).

The voting layer flagged abuse only implicitly (in-memory rate buckets,
on-the-fly fingerprint collisions, audit rows). These two tables make it
explicit and actionable per event:
- security_flags: one row per (event, kind, subject) — rate-limit hits,
  own-team vote attempts, shared-device collisions, comment floods.
  Status open/blocked/dismissed; re-offence reopens a dismissed flag.
- security_blocks: organizer-issued blocks (user id or IP) enforced on
  ballot casts and comment posts until revoked.

Revision ID: 0021_security
Revises: 0020_api_keys
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_security"
down_revision = "0020_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_flags",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(),
                  sa.ForeignKey("events.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False,
                  server_default="{}"),
        sa.Column("status", sa.Text(), nullable=False,
                  server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", "kind", "subject",
                            name="uq_flag_event_kind_subject"),
    )
    op.create_table(
        "security_blocks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(),
                  sa.ForeignKey("events.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("security_blocks")
    op.drop_table("security_flags")
