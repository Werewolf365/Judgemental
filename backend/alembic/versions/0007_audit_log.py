"""Admin-visible audit log.

Records security-relevant actions (auth, role changes, organizer assignment,
event mutation, gallery moderation) so an administrator can answer "who did
what, and when". Written on its own connection by `app.shared.audit.record`, so
a row survives even when the action it describes rolled back or failed.

Revision ID: 0007_audit_log
Revises: 0006_event_organizers
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_audit_log"
down_revision = "0006_event_organizers"
branch_labels = None
depends_on = None

audit = sa.Table(
    "audit_log",
    sa.MetaData(),
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    # Actor. Kept as plain text (not FK) so the trail survives account deletion.
    sa.Column("actor_id", sa.Text(), nullable=True, index=True),
    sa.Column("actor_email", sa.Text(), nullable=True),
    sa.Column("action", sa.Text(), nullable=False, index=True),
    sa.Column("target_type", sa.Text(), nullable=True),
    sa.Column("target_id", sa.Text(), nullable=True),
    sa.Column("event_id", sa.Text(), nullable=True, index=True),
    sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    sa.Column("ip", sa.Text(), nullable=True),
)


def upgrade() -> None:
    # `index=True` on created_at/action/etc. makes Table.create() emit the
    # indexes, so no separate create_index calls here.
    audit.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Dropping the table drops its indexes with it.
    op.drop_table("audit_log")
