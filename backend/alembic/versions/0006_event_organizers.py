"""Per-event organizer assignment (event_organizers).

Until now an event recorded only `created_by`, and nothing ever read it:
`require_roles("ORGANIZER", "ADMIN")` was the whole authorization model, so any
organizer could read and mutate every other organizer's events. This table makes
the assignment explicit and auditable.

- event_organizers(event_id, user_id) is the membership list. The creator is
  inserted as the first row when the event is created.
- Backfill: every existing event with a `created_by` gets that user as an
  organizer, so upgrades keep their current access.
- Events with `created_by IS NULL` (only the fixtures.json sample event) are
  left alone here; `app.seed` claims them for the demo organizer on next boot.

Revision ID: 0006_event_organizers
Revises: 0005_submission_form_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_event_organizers"
down_revision = "0005_submission_form_fields"
branch_labels = None
depends_on = None

organizers = sa.Table(
    "event_organizers",
    sa.MetaData(),
    sa.Column("event_id", sa.Text(), primary_key=True),
    sa.Column("user_id", sa.Text(), primary_key=True),
    sa.Column("assigned_by", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
)

# Name-only stubs so the FKs resolve to the real tables (never created).
sa.Table("events", organizers.metadata, sa.Column("id", sa.Text(), primary_key=True))
sa.Table("users", organizers.metadata, sa.Column("id", sa.Text(), primary_key=True))


def upgrade() -> None:
    # checkfirst: databases seeded while an earlier dev revision existed may
    # already have this table via metadata.create_all().
    organizers.create(bind=op.get_bind(), checkfirst=True)
    op.execute(
        """
        INSERT INTO event_organizers (event_id, user_id, assigned_by, created_at)
        SELECT e.id, e.created_by, e.created_by, now()
        FROM events e
        WHERE e.created_by IS NOT NULL
        ON CONFLICT (event_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("event_organizers")
