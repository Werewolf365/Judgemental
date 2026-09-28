"""Profile pictures: users.avatar_url holds a small client-resized image.

Deliberately a data: URL in the row, not a file store: no volumes, no
object storage, no new service, and it works offline. The frontend
downscales to 128px JPEG before upload (tens of KB); the backend caps
length as a backstop. Avatars are public profile data by design (shown
in comments and the header chip), never auth material.

Revision ID: 0010_avatar
Revises: 0009_voting
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_avatar"
down_revision = "0009_voting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
