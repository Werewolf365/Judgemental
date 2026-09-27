import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (Column, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON, Integer, Enum as SAEnum)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class Role(str, enum.Enum):
    PARTICIPANT = "PARTICIPANT"
    JUDGE = "JUDGE"
    ORGANIZER = "ORGANIZER"
    ADMIN = "ADMIN"

class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    COMPLETED = "COMPLETED"

class TeamRole(str, enum.Enum):
    CAPTAIN = "CAPTAIN"
    MEMBER = "MEMBER"

class ProjectStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"

class GalleryVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PARTICIPANTS = "PARTICIPANTS"
    ORGANIZERS_ONLY = "ORGANIZERS_ONLY"

def _uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(Text, primary_key=True, default=_uuid)
    email = Column(Text, nullable=False)
    email_norm = Column(Text, nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False, default="")
    role = Column(SAEnum(Role, name="user_role"), nullable=False, default=Role.PARTICIPANT)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Text, primary_key=True, default=_uuid)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(Text, nullable=True)

class Event(Base):
    __tablename__ = "events"
    id = Column(Text, primary_key=True, default=_uuid)
    slug = Column(Text, nullable=False, unique=True, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    registration_start = Column(DateTime(timezone=True), nullable=True)
    registration_close = Column(DateTime(timezone=True), nullable=True)
    event_start = Column(DateTime(timezone=True), nullable=True)
    event_end = Column(DateTime(timezone=True), nullable=True)
    submissions_open = Column(DateTime(timezone=True), nullable=True)
    submissions_close = Column(DateTime(timezone=True), nullable=True)
    status = Column(SAEnum(EventStatus, name="event_status"), nullable=False, default=EventStatus.DRAFT)
    gallery_visibility = Column(SAEnum(GalleryVisibility, name="gallery_visibility"), nullable=False, default=GalleryVisibility.PUBLIC, server_default="PUBLIC")
    created_by = Column(Text, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class EventParticipant(Base):
    __tablename__ = "event_participants"
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime(timezone=True), default=utcnow)

class ParticipantRegistration(Base):
    __tablename__ = "participant_registrations"
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(Text, nullable=False)
    age = Column(Integer, nullable=False)
    degree = Column(Text, nullable=False)
    year_of_study = Column(Text, nullable=False)
    institution = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    tshirt_size = Column(Text, nullable=True)
    dietary_restrictions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("event_id", "name", name="uq_track_event_name"),)
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Prize(Base):
    __tablename__ = "prizes"
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id = Column(Text, ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    value_desc = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class Team(Base):
    __tablename__ = "teams"
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    created_by = Column(Text, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class TeamMember(Base):
    __tablename__ = "team_members"
    team_id = Column(Text, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(SAEnum(TeamRole, name="team_role"), nullable=False, default=TeamRole.MEMBER)
    joined_at = Column(DateTime(timezone=True), default=utcnow)

class TeamInvite(Base):
    __tablename__ = "team_invites"
    id = Column(Text, primary_key=True, default=_uuid)
    team_id = Column(Text, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False, unique=True, index=True)
    created_by = Column(Text, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(Text, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id = Column(Text, ForeignKey("tracks.id"), nullable=False, index=True)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=True)
    repo_url = Column(Text, nullable=True)
    demo_url = Column(Text, nullable=True)
    live_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    status = Column(SAEnum(ProjectStatus, name="project_status"), nullable=False, default=ProjectStatus.DRAFT, index=True)
    is_visible = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

Index("ix_projects_event_status", Project.event_id, Project.status)

class Judge(Base):
    __tablename__ = "judges"
    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class JudgeTrack(Base):
    __tablename__ = "judge_tracks"
    judge_id = Column(Text, ForeignKey("judges.id", ondelete="CASCADE"), primary_key=True)
    track_id = Column(Text, ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True)

class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("judge_id", "project_id", name="uq_score_judge_project"),)
    id = Column(Text, primary_key=True, default=_uuid)
    judge_id = Column(Text, ForeignKey("judges.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    criteria = Column(JSON, nullable=False, default=dict)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
