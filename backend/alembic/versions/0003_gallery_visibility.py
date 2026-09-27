"""Gallery visibility per event (PUBLIC / PARTICIPANTS / ORGANIZERS_ONLY)."""
from alembic import op
import sqlalchemy as sa

revision = "0003_gallery_visibility"
down_revision = "8159621d23e9"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("DO $$ BEGIN CREATE TYPE gallery_visibility AS ENUM ('PUBLIC', 'PARTICIPANTS', 'ORGANIZERS_ONLY'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.add_column("events", sa.Column("gallery_visibility", sa.Enum("PUBLIC", "PARTICIPANTS", "ORGANIZERS_ONLY", name="gallery_visibility"), nullable=False, server_default="PUBLIC"))

def downgrade():
    op.drop_column("events", "gallery_visibility")
    op.execute("DROP TYPE IF EXISTS gallery_visibility")
