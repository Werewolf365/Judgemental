"""T3 voting service: windows, voter identity, budget enforcement.

Three ballot access modes, chosen per event by the organizer:
- "auth"  — logged-in users only. Strongest identity, supports the
  own-team block. voter_key = "user:<id>".
- "email" — anyone who names an address (shape-validated, normalized).
  One ballot set per address. voter_key = "email:<normalized>".
- "open"  — anyone with a client-generated voter id (UUID, persisted in
  the browser's localStorage). Lowest friction, weakest identity:
  voter_key = "anon:<uuid>". Duplicate humans behind fresh ids are
  expected here — fp_hash collisions surface them to organizers as a
  signal, never an auto-block (shared networks would false-positive).

Quadratic budget (see quadratic.py) is enforced on every write across ALL
of the voter's cells, not just the edited one: the check always prices the
voter's full resulting allocation.
"""
import hashlib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ballot, Event, EventParticipant, Project, ProjectStatus, Team, TeamMember
from app.modules.voting import quadratic
from app.shared.clock import utcnow
from app.shared.errors import err

VOTING_MODES = ("auth", "email", "open")
COMMENT_VIS = ("public", "team")


def _aware(x):
    if x is None:
        return None
    return x if x.tzinfo else x.replace(tzinfo=__import__("datetime").timezone.utc)


def is_staff(user) -> bool:
    if user is None:
        return False
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role in ("ORGANIZER", "ADMIN")


def is_published(event: Event) -> bool:
    st = event.status.value if hasattr(event.status, "value") else str(event.status)
    return st == "PUBLISHED"


def require_live_or_staff(event: Event, user) -> None:
    """Drafts are staff-only across the whole voting surface (same rule as
    the gallery): the public never sees draft ballots, casts, or results."""
    from app.shared.errors import err
    if not is_published(event) and not is_staff(user):
        err(404, "not_found", "Event not found")


def voting_open(event: Event) -> tuple[bool, str]:
    """(open, reason). Open = enabled and (no close set or now < close)."""
    if not event.voting_enabled:
        return False, "public voting is not enabled for this event"
    close = _aware(event.voting_close)
    if close is not None and utcnow() >= close:
        return False, "public voting has closed for this event"
    return True, ""


def voting_config_out(event: Event) -> dict:
    f = lambda x: x.isoformat() if x else None
    mode = (event.voting_mode or "auth").lower()
    vis = (event.comments_visibility or "public").lower()
    return {"voting_enabled": bool(event.voting_enabled),
            "voting_close": f(event.voting_close),
            "voting_mode": mode if mode in VOTING_MODES else "auth",
            "comments_visibility": vis if vis in COMMENT_VIS else "public"}


def voter_key_for(event: Event, user, email: str | None, voter_id: str | None) -> str:
    """Resolve who is voting under this event's mode. Never trusts the
    client for anything the server can derive (user id comes from session)."""
    mode = (event.voting_mode or "auth").lower()
    if mode == "auth":
        if user is None:
            err(401, "unauthenticated", "log in to vote in this event")
        return f"user:{user.id}"
    if mode == "email":
        em = (email or "").strip().lower()
        if "@" not in em or "." not in em.split("@")[-1]:
            err(422, "validation_error", "a valid email address is required to vote")
        return f"email:{em}"
    # open mode
    vid = (voter_id or "").strip()
    try:
        uuid.UUID(vid)
    except (ValueError, AttributeError):
        err(422, "validation_error", "a voter id is required to vote")
    return f"anon:{vid.lower()}"


def fingerprint(ip: str | None, ua: str | None, event_id: str) -> str:
    """Soft duplicate signal. Deliberately coarse (IP + agent + event) and
    hashed — stored for organizer review, never used to block writes."""
    raw = f"{ip or ''}|{ua or ''}|{event_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


async def voter_team_id(db: AsyncSession, event_id: str, user_id: str | None) -> str | None:
    if not user_id:
        return None
    res = await db.execute(
        select(Team.id).join(TeamMember, TeamMember.team_id == Team.id).where(
            Team.event_id == event_id, TeamMember.user_id == user_id))
    return res.scalar_one_or_none()


async def eligible_projects(db: AsyncSession, event_id: str):
    """SUBMITTED + visible projects of this event, for the ballot box."""
    res = await db.execute(
        select(Project).where(
            Project.event_id == event_id,
            Project.status == ProjectStatus.SUBMITTED,
            Project.is_visible == True).order_by(Project.title))  # noqa
    return res.scalars().all()


async def voter_allocations(db: AsyncSession, event_id: str, voter_key: str) -> dict:
    res = await db.execute(select(Ballot).where(
        Ballot.event_id == event_id, Ballot.voter_key == voter_key))
    return {b.project_id: b.votes for b in res.scalars().all()}


async def price_allocation(db: AsyncSession, event_id: str, voter_key: str,
                           project_id: str, votes: int) -> dict:
    """Price the voter's FULL resulting allocation (existing cells plus this
    edit). Raises 422 via quadratic.check_budget when over budget."""
    current = await voter_allocations(db, event_id, voter_key)
    current[project_id] = votes
    current = {pid: v for pid, v in current.items() if v}
    try:
        return quadratic.check_budget(current)
    except ValueError as e:
        err(422, "validation_error", str(e))
