"""Per-event certificate switch. Certificates render from the built-in
design; the flag decides whether they are issued and shown at all.

Revision ID: 0022_certificates_enabled
Revises: 0021_security
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_certificates_enabled"
down_revision = "0021_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("certificates_enabled", sa.Boolean(),
                                      nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("events", "certificates_enabled")
