"""T3 community voting: event flags, ballots, comments.

Revision ID: 0009_voting
Revises: 0008_judging
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_voting"
down_revision = "0008_judging"
branch_labels = None
depends_on = None

md = sa.MetaData()

# Name-only stubs so FKs resolve to the real tables (never created — only
# `ballots` and `comments` below are created).
sa.Table("events", md, sa.Column("id", sa.Text(), primary_key=True))
sa.Table("projects", md, sa.Column("id", sa.Text(), primary_key=True))
sa.Table("users", md, sa.Column("id", sa.Text(), primary_key=True))

ballots = sa.Table(
    "ballots",
    md,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("event_id", sa.Text(), nullable=False, index=True),
    sa.Column("project_id", sa.Text(), nullable=False, index=True),
    sa.Column("voter_key", sa.Text(), nullable=False, index=True),
    sa.Column("votes", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("fp_hash", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("event_id", "voter_key", "project_id",
                        name="uq_ballot_voter_project"),
    sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
)

comments = sa.Table(
    "comments",
    md,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("event_id", sa.Text(), nullable=False, index=True),
    sa.Column("project_id", sa.Text(), nullable=False, index=True),
    sa.Column("author_user_id", sa.Text(), nullable=False),
    sa.Column("body", sa.Text(), nullable=False),
    sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default="false"),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
)


def upgrade() -> None:
    op.add_column("events", sa.Column("voting_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("events", sa.Column("voting_close", sa.DateTime(timezone=True), nullable=True))
    op.add_column("events", sa.Column("voting_mode", sa.Text(), nullable=False, server_default="auth"))
    op.add_column("events", sa.Column("comments_visibility", sa.Text(), nullable=False, server_default="public"))
    ballots.create(bind=op.get_bind(), checkfirst=True)
    comments.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("comments")
    op.drop_table("ballots")
    op.drop_column("events", "comments_visibility")
    op.drop_column("events", "voting_mode")
    op.drop_column("events", "voting_close")
    op.drop_column("events", "voting_enabled")
