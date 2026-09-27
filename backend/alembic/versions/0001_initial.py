"""Initial schema — mirrors app/models.py."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table("users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_norm", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("role", sa.Enum("PARTICIPANT", "JUDGE", "ORGANIZER", "ADMIN", name="user_role"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.Text()))
    op.create_table("events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("registration_start", sa.DateTime(timezone=True)),
        sa.Column("registration_close", sa.DateTime(timezone=True)),
        sa.Column("event_start", sa.DateTime(timezone=True)),
        sa.Column("event_end", sa.DateTime(timezone=True)),
        sa.Column("submissions_open", sa.DateTime(timezone=True)),
        sa.Column("submissions_close", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", "COMPLETED", name="event_status"), nullable=False),
        sa.Column("created_by", sa.Text(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("event_participants",
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("joined_at", sa.DateTime(timezone=True)))
    op.create_table("tracks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("event_id", "name", name="uq_track_event_name"))
    op.create_table("prizes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("track_id", sa.Text(), sa.ForeignKey("tracks.id", ondelete="SET NULL")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("value_desc", sa.Text()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("teams",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("team_members",
        sa.Column("team_id", sa.Text(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.Enum("CAPTAIN", "MEMBER", name="team_role"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True)))
    op.create_table("team_invites",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("team_id", sa.Text(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_by", sa.Text(), sa.ForeignKey("users.id")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_table("projects",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_id", sa.Text(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.Text(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("track_id", sa.Text(), sa.ForeignKey("tracks.id"), nullable=False, index=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text()),
        sa.Column("repo_url", sa.Text()),
        sa.Column("demo_url", sa.Text()),
        sa.Column("live_url", sa.Text()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("status", sa.Enum("DRAFT", "SUBMITTED", name="project_status"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)))
    op.create_table("judges",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_table("judge_tracks",
        sa.Column("judge_id", sa.Text(), sa.ForeignKey("judges.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("track_id", sa.Text(), sa.ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("scores",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("judge_id", sa.Text(), sa.ForeignKey("judges.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("criteria", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("judge_id", "project_id", name="uq_score_judge_project"))

def downgrade():
    for t in ("scores", "judge_tracks", "judges", "projects", "team_invites", "team_members", "teams", "prizes", "tracks", "event_participants", "events", "sessions", "users"):
        op.drop_table(t)
    op.execute("DROP TYPE IF EXISTS project_status")
    op.execute("DROP TYPE IF EXISTS team_role")
    op.execute("DROP TYPE IF EXISTS event_status")
    op.execute("DROP TYPE IF EXISTS user_role")
