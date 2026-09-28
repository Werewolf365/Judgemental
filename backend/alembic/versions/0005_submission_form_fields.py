"""Organizer-defined submission form fields + per-project custom answers.

- event_form_fields: organizer-managed fields per event (label, type, required,
  options for select). Deleting an event cascades; deleting a field leaves
  already-stored answers in place (they render only for existing fields).
- projects.custom_data: JSON object {field_id: value} supplied by teams.

Revision ID: 0005_submission_form_fields
Revises: 0004_participant_registrations
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_submission_form_fields"
down_revision = "0004_participant_registrations"
branch_labels = None
depends_on = None

fields = sa.Table(
    "event_form_fields",
    sa.MetaData(),
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("event_id", sa.Text(), nullable=False, index=True),
    sa.Column("label", sa.Text(), nullable=False),
    sa.Column("field_type", sa.Text(), nullable=False, server_default="text"),
    sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
    sa.Column("options", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    # Name-only stub so the FK resolves to the real events table.
    sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
)

sa.Table("events", fields.metadata, sa.Column("id", sa.Text(), primary_key=True))


def upgrade() -> None:
    fields.create(bind=op.get_bind(), checkfirst=True)
    # Nullable-safe add: server_default keeps existing rows valid.
    op.add_column("projects", sa.Column("custom_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))


def downgrade() -> None:
    op.drop_column("projects", "custom_data")
    op.drop_table("event_form_fields")
