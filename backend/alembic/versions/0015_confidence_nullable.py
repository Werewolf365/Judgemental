"""Confidence NULL means uncomputed (migration 0015).

Migration 0013 added model_project_results.confidence as non-nullable
defaulting to 'High' — so legacy rows that never computed any uncertainty
assert confidence that was never measured. This migration makes the column
nullable, drops the default, and backfills NULL exactly where no Laplace
std exists (theta_std IS NULL). New runs always write a real High/Low.

Revision ID: 0015_confidence_nullable
Revises: 0014_event_timezone
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_confidence_nullable"
down_revision = "0014_event_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE model_project_results ALTER COLUMN confidence DROP NOT NULL")
    op.execute("ALTER TABLE model_project_results ALTER COLUMN confidence DROP DEFAULT")
    op.execute("UPDATE model_project_results SET confidence = NULL WHERE theta_std IS NULL")


def downgrade() -> None:
    op.execute("UPDATE model_project_results SET confidence = 'High' WHERE confidence IS NULL")
    op.execute("ALTER TABLE model_project_results ALTER COLUMN confidence SET DEFAULT 'High'")
    op.execute("ALTER TABLE model_project_results ALTER COLUMN confidence SET NOT NULL")
