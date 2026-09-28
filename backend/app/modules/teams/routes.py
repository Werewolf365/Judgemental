from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from app.database import get_db
from app.models import Team, TeamMember, TeamRole, TeamInvite, Event, EventParticipant, User
from app.modules.auth.dependencies import current_user
from app.shared.errors import err
from app.shared.audit import record
from app.shared.security import sha256_hex, utcnow
import secrets, uuid

router = APIRouter(tags=["teams"])

def team_out(t: Team, members: list) -> dict:
    return {"id": t.id, "event_id": t.event_id, "name": t.name,
            "members": [{"user_id": m[0], "email": m[1], "display_name": m[2], "role": m[3]} for m in members]}

async def _members(db: AsyncSession, team_id: str):
    res = await db.execute(select(TeamMember, User).join(User, User.id == TeamMember.user_id).where(TeamMember.team_id == team_id))
    return [(m.user_id, u.email, u.display_name, m.role.value if hasattr(m.role, "value") else str(m.role)) for m, u in res.all()]

async def _require_event_manager(db: AsyncSession, event_id: str, user) -> bool:
    """Staff may only step outside the participant flow for their own events."""
    from app.modules.events.access import manages_event
    return await manages_event(db, user, await db.get(Event, event_id))

async def _require_event_member(db: AsyncSession, event_id: str, user_id: str):
    res = await db.execute(select(EventParticipant).where(EventParticipant.event_id == event_id, EventParticipant.user_id == user_id))
    return res.scalar_one_or_none() is not None

async def _user_team_for_event(db: AsyncSession, event_id: str, user_id: str):
    res = await db.execute(select(Team, TeamMember).join(TeamMember, TeamMember.team_id == Team.id).where(Team.event_id == event_id, TeamMember.user_id == user_id))
    return res.first()

async def _team_locked(db: AsyncSession, team_id: str) -> bool:
    """Roster is frozen once the team has a SUBMITTED project."""
    from app.models import Project, ProjectStatus
    res = await db.execute(select(Project).where(Project.team_id == team_id, Project.status == ProjectStatus.SUBMITTED).limit(1))
    return res.scalar_one_or_none() is not None

@router.get("/teams")
async def my_teams(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(TeamMember.user_id == user.id))
    teams = res.scalars().all()
    return {"teams": [{"id": t.id, "event_id": t.event_id, "name": t.name} for t in teams]}

@router.post("/events/{event_id}/teams")
async def create_team(event_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    if not await _require_event_member(db, event_id, user.id):
        err(403, "forbidden", "Join the event before creating a team")
    if await _user_team_for_event(db, event_id, user.id):
        err(409, "already_joined", "Already in a team for this event")
    name = (body.get("name") or "").strip()
    if not name:
        err(422, "validation_error", "Team name required")
    if len(name) > 100:
        err(422, "validation_error", "Team name is too long")
    import uuid as _u
    t = Team(id=f"tm_{_u.uuid4().hex[:8]}", event_id=event_id, name=name, created_by=user.id)
    db.add(t)
    await db.flush()
    db.add(TeamMember(team_id=t.id, user_id=user.id, role=TeamRole.CAPTAIN))
    await db.commit()
    return {"team": {"id": t.id, "event_id": t.event_id, "name": t.name}}

@router.get("/teams/{team_id}")
async def get_team(team_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    t = await db.get(Team, team_id)
    if not t:
        err(404, "not_found", "Team not found")
    res = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id))
    # A member sees the roster; an outsider only if they run this event.
    if not res.scalar_one_or_none() and not await _require_event_manager(db, t.event_id, user):
        err(403, "forbidden", "Not a team member")
    return {"team": team_out(t, await _members(db, team_id))}

@router.post("/teams/{team_id}/invites")
async def create_invite(team_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    t = await db.get(Team, team_id)
    if not t:
        err(404, "not_found", "Team not found")
    res = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id))
    m = res.scalar_one_or_none()
    if not m or (m.role.value if hasattr(m.role, "value") else str(m.role)) != "CAPTAIN":
        # Captain, or an organizer of this event (not merely any organizer).
        if not await _require_event_manager(db, t.event_id, user):
            err(403, "forbidden", "Only captain can generate invites")
    if await _team_locked(db, team_id):
        err(409, "invalid_state_transition", "Team roster is locked after submission")
    # revoke previous active
    res2 = await db.execute(select(TeamInvite).where(TeamInvite.team_id == team_id, TeamInvite.revoked_at.is_(None), TeamInvite.used_at.is_(None)))
    for inv in res2.scalars().all():
        inv.revoked_at = utcnow()
    raw = secrets.token_urlsafe(32)
    inv = TeamInvite(team_id=team_id, token_hash=sha256_hex(raw), created_by=user.id)
    db.add(inv)
    await db.commit()
    await record(user, "team.invite_created", target_type="team", target_id=team_id, event_id=t.event_id,
                 detail={"team": t.name}, request=request)
    return {"invite_url": f"/teams/join/{raw}", "token": raw}

@router.post("/teams/join/{token}")
async def join_by_token(token: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    th = sha256_hex(token)
    res = await db.execute(select(TeamInvite).where(TeamInvite.token_hash == th))
    inv = res.scalar_one_or_none()
    if not inv:
        err(404, "invitation_expired", "Invite not found")
    if inv.revoked_at:
        err(410, "invitation_revoked", "Invite revoked")
    if inv.used_at:
        err(410, "invitation_expired", "Invite already used")
    if inv.expires_at:
        exp = inv.expires_at
        if exp.tzinfo is None:
            from datetime import timezone
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= utcnow():
            err(410, "invitation_expired", "Invite expired")
    t = await db.get(Team, inv.team_id)
    if not t:
        err(404, "not_found", "Team no longer exists")
    if await _team_locked(db, t.id):
        err(409, "invalid_state_transition", "This team has already submitted; its roster is locked")
    # one team per event rule
    if await _user_team_for_event(db, t.event_id, user.id):
        # if already in this team -> idempotent ok
        r = await db.execute(select(TeamMember).where(TeamMember.team_id == t.id, TeamMember.user_id == user.id))
        if r.scalar_one_or_none():
            return {"ok": True, "already": True}
        err(409, "already_joined", "Already in another team for this event")
    r = await db.execute(select(EventParticipant).where(EventParticipant.event_id == t.event_id, EventParticipant.user_id == user.id))
    if not r.scalar_one_or_none():
        err(403, "registration_required", "You must register for the event before joining a team.")
    db.add(TeamMember(team_id=t.id, user_id=user.id, role=TeamRole.MEMBER))
    inv.used_at = None  # reusable until regenerated; set used only for one-use? keep reusable: do not mark used
    await db.commit()
    return {"ok": True, "team_id": t.id}

@router.delete("/teams/{team_id}/members/me")
async def leave_team(team_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    from app.models import Project, ProjectStatus
    t = await db.get(Team, team_id)
    if not t:
        err(404, "not_found", "Team not found")
    res = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id))
    me = res.scalar_one_or_none()
    if not me:
        err(403, "forbidden", "Not a member of this team")
    # Like HackerEarth/Devfolio: the roster locks once the team has submitted.
    res2 = await db.execute(select(Project).where(Project.team_id == team_id, Project.status == ProjectStatus.SUBMITTED).limit(1))
    if res2.scalar_one_or_none():
        err(409, "invalid_state_transition", "Team roster is locked after submission")
    res3 = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id))
    members = res3.scalars().all()
    if len(members) == 1:
        # Last member out dissolves the team (drafts go with it).
        res4 = await db.execute(select(Project).where(Project.team_id == team_id))
        for p in res4.scalars().all():
            await db.delete(p)
        await db.delete(me)
        await db.delete(t)
        await db.commit()
        return {"ok": True, "dissolved": True}
    my_role = me.role.value if hasattr(me.role, "value") else str(me.role)
    await db.delete(me)
    if my_role == "CAPTAIN":
        # Pass captaincy to the earliest-joined remaining member.
        rest = sorted(members, key=lambda m: (m.joined_at is None, m.joined_at))
        nxt = next(m for m in rest if m.user_id != user.id)
        nxt.role = TeamRole.CAPTAIN
    await db.commit()
    return {"ok": True}
