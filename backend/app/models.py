import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (Column, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, JSON, Integer, Float, Enum as SAEnum,
    text as sa_text)
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

class AssignmentStatus(str, enum.Enum):
    """Lifecycle of one judge→project assignment. Terminal states are
    COMPLETED (judged) and REVOKED (judge removed or assignment replaced).
    Rows are never deleted: REVOKED preserves the audit trail."""
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REVOKED = "REVOKED"

class EvaluationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"

class ModelRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"

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
    # --- T2 judging configuration. The window bounds are optional: when unset,
    # scoring is allowed on any SUBMITTED project of a live event, and the
    # organizer sets an explicit deadline before the final calculation.
    judging_open = Column(DateTime(timezone=True), nullable=True)
    judging_close = Column(DateTime(timezone=True), nullable=True)
    judges_per_project = Column(Integer, nullable=False, default=2, server_default="2")
    rolling_judging = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(Text, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class EventOrganizer(Base):
    """Who may manage an event. Created by `events.created_by` on create."""
    __tablename__ = "event_organizers"
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    assigned_by = Column(Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

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
    custom_data = Column(JSON, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

Index("ix_projects_event_status", Project.event_id, Project.status)

class AuditLog(Base):
    """Append-only trail of security-relevant actions. Read by ADMIN only.

    Actor columns are plain text rather than foreign keys on purpose: the
    record of what happened must not disappear when an account does.
    """
    __tablename__ = "audit_log"
    id = Column(Text, primary_key=True, default=_uuid)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    actor_id = Column(Text, nullable=True, index=True)
    actor_email = Column(Text, nullable=True)
    action = Column(Text, nullable=False, index=True)
    target_type = Column(Text, nullable=True)
    target_id = Column(Text, nullable=True)
    event_id = Column(Text, nullable=True, index=True)
    detail = Column(JSON, nullable=False, default=dict, server_default="{}")
    ip = Column(Text, nullable=True)

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

class EventFormField(Base):
    __tablename__ = "event_form_fields"
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(Text, nullable=False)
    field_type = Column(Text, nullable=False, default="text")
    required = Column(Boolean, nullable=False, default=False)
    options = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("judge_id", "project_id", name="uq_score_judge_project"),)
    id = Column(Text, primary_key=True, default=_uuid)
    judge_id = Column(Text, ForeignKey("judges.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    criteria = Column(JSON, nullable=False, default=dict)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

# ---------------------------------------------------------------------------
# T2 judging. Judge identity throughout is users.id (the authenticated JUDGE
# account), never the fixture judges.id rows — see context.md §17/D1. The
# fixture judges/scores tables above stay untouched as seeded legacy data.
# ---------------------------------------------------------------------------

class RubricCriterion(Base):
    """One organizer-defined scoring criterion for an event.

    weight is a nullable percentage. NULL on every active criterion means
    "no explicit weights" → equal weighting. Once any criterion carries an
    explicit weight, all of them must (enforced in the route, not here).
    Deactivation (is_active=False) is the post-start removal path; hard
    DELETE is only allowed before judging starts (also enforced in routes).
    """
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("event_id", "name", name="uq_rubric_event_name"),)
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class EventJudge(Base):
    """Roster of judges for one event. Removal sets is_active=False — the row
    (and everything judged under it) is never deleted."""
    __tablename__ = "event_judges"
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    is_active = Column(Boolean, nullable=False, default=True)
    assigned_by = Column(Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class JudgeAssignment(Base):
    """One judge→project work item. The partial unique index is the DB-level
    idempotency guarantee: the same live (non-REVOKED) pair can never exist
    twice, so concurrent assign_project calls cannot duplicate work. A removed
    then re-added judge may legitimately hold a new row for the same project,
    which is why REVOKED rows are excluded rather than using a full unique."""
    __tablename__ = "judge_assignments"
    # Partial unique index (not a UniqueConstraint: SQLAlchemy only allows
    # postgresql_where on Index). Same guarantee — one live row per pair.
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    judge_user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SAEnum(AssignmentStatus, name="assignment_status"), nullable=False,
                    default=AssignmentStatus.ASSIGNED, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

Index("ix_assignments_event_status", JudgeAssignment.event_id, JudgeAssignment.status)
Index("uq_assignment_project_judge_active",
      JudgeAssignment.project_id, JudgeAssignment.judge_user_id,
      unique=True, postgresql_where=sa_text("status <> 'REVOKED'"))

class Evaluation(Base):
    """A judge's rubric scores for one assignment. scores maps
    rubric_criterion.id → number (0–10 inclusive, validated in routes).
    weighted_score is snapshotted at submit time using the then-current
    normalized weights, so later rubric edits cannot rewrite history."""
    __tablename__ = "evaluations"
    id = Column(Text, primary_key=True, default=_uuid)
    assignment_id = Column(Text, ForeignKey("judge_assignments.id", ondelete="CASCADE"),
                           nullable=False, unique=True, index=True)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    judge_user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    scores = Column(JSON, nullable=False, default=dict, server_default="{}")
    comment = Column(Text, nullable=True)
    status = Column(SAEnum(EvaluationStatus, name="evaluation_status"), nullable=False,
                    default=EvaluationStatus.DRAFT, index=True)
    weighted_score = Column(Float, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class JudgeReliabilityHistory(Base):
    """The Bayesian chain across competitions: each SUCCEEDED model run appends
    one row per judge; the latest row for a judge becomes the prior (mu,
    sigma) of their next competition. A judge with no row gets the neutral
    prior (mu=0, sigma=0.60, i.e. r centered at 1). posterior_sigma is NULL
    for MAP estimation, which yields point estimates only — recorded honestly
    rather than fabricated."""
    __tablename__ = "judge_reliability_history"
    __table_args__ = (UniqueConstraint("model_run_id", "judge_user_id", name="uq_relhist_run_judge"),)
    id = Column(Text, primary_key=True, default=_uuid)
    judge_user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    model_run_id = Column(Text, ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    posterior_mu = Column(Float, nullable=False)
    posterior_sigma = Column(Float, nullable=True)
    r = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class ModelRun(Base):
    """One Crowd-BT calculation over an event. config snapshots everything
    needed to reproduce it: model version, priors, theta prior, reference
    project, and the full rubric (criteria + weights used)."""
    __tablename__ = "model_runs"
    id = Column(Text, primary_key=True, default=_uuid)
    event_id = Column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    model_version = Column(Text, nullable=False, default="crowd-bt-map-v1")
    status = Column(SAEnum(ModelRunStatus, name="model_run_status"), nullable=False,
                    default=ModelRunStatus.RUNNING, index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    config = Column(JSON, nullable=False, default=dict, server_default="{}")
    n_projects = Column(Integer, nullable=False, default=0)
    n_judges = Column(Integer, nullable=False, default=0)
    n_comparisons = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)

class ModelProjectResult(Base):
    __tablename__ = "model_project_results"
    model_run_id = Column(Text, ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True)
    project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    theta = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)

class ModelJudgeResult(Base):
    __tablename__ = "model_judge_results"
    model_run_id = Column(Text, ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True)
    judge_user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    r = Column(Float, nullable=False)
    prior_mu = Column(Float, nullable=False)
    prior_sigma = Column(Float, nullable=False)
    posterior_mu = Column(Float, nullable=False)

class PairwiseObservation(Base):
    """One unit-weighted within-judge comparison. weight is CHECK-constrained
    to 1: raw score margins must never become cross-judge evidence weights
    (the corrected architecture's central invariant). Ties are never stored —
    a tie produces no row rather than a forced winner."""
    __tablename__ = "pairwise_observations"
    __table_args__ = (CheckConstraint("weight = 1", name="ck_pairwise_unit_weight"),)
    id = Column(Text, primary_key=True, default=_uuid)
    model_run_id = Column(Text, ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    judge_user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    winner_project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    loser_project_id = Column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Float, nullable=False, default=1.0, server_default="1")
    source_evaluation_ids = Column(JSON, nullable=False, default=list, server_default="[]")
