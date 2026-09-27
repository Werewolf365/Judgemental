"""Add is_visible moderation flag to projects (organizer hide/show)."""
from alembic import op
import sqlalchemy as sa

revision = "0002_visibility"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("projects", sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="true"))

def downgrade():
    op.drop_column("projects", "is_visible")
