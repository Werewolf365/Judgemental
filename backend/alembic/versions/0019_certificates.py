"""T4 certificates: organizer template + issued rows (lazy on first view).

No backfill: templates appear when organizers upload; certificates appear
when participants first view them after results are declared.

Revision ID: 0019_certificates
Revises: 0018_blend
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_certificates"
down_revision = "0018_blend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificate_templates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"),
                  nullable=False, unique=True, index=True),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "certificates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("kind", sa.Enum("WINNER", "PARTICIPATION", name="certificate_kind"), nullable=False),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_name", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True, index=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_id", "user_id", name="uq_cert_event_user"),
    )


def downgrade() -> None:
    op.drop_table("certificates")
    op.drop_table("certificate_templates")
    op.execute("DROP TYPE IF EXISTS certificate_kind")
