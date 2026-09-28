from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Project, ProjectStatus, Team, TeamMember, Track, Event, EventStatus, EventParticipant, User, EventFormField
from app.modules.auth.dependencies import current_user, require_roles
from app.modules.events.access import require_manageable
from app.shared.errors import err
from app.shared.audit import record
from app.shared.clock import utcnow
from app.modules.submissions.schemas import ProjectCreate, ProjectUpdate, VisibilityUpdate
import uuid

router = APIRouter(tags=["submissions"])

def proj_out(p: Project) -> dict:
    f = lambda x: x.isoformat() if x else None
    return {"id": p.id, "event_id": p.event_id, "team_id": p.team_id, "track_id": p.track_id,
            "title": p.title, "summary": p.summary, "description": p.description, "repo_url": p.repo_url,
            "demo_url": p.demo_url, "live_url": p.live_url, "thumbnail_url": p.thumbnail_url,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "custom_data": p.custom_data or {},
            "submitted_at": f(p.submitted_at), "created_at": f(p.created_at), "updated_at": f(p.updated_at)}

def aware(x):
    if x is None:
        return None
    return x if x.tzinfo else x.replace(tzinfo=__import__("datetime").timezone.utc)

async def _check_membership(db, user_id, team_id) -> Team:
    r = await db.execute(select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    if not r.scalar_one_or_none():
        err(403, "forbidden", "Not a member of this team")
    t = await db.get(Team, team_id)
    if not t:
        err(404, "not_found", "Team not found")
    return t

def _deadline_open(event: Event) -> tuple[bool, str]:
    now = utcnow()
    so, sc = aware(event.submissions_open), aware(event.submissions_close)
    if so and now < so:
        return False, "Submissions have not opened"
    if sc and now > sc:
        return False, "Submission deadline has passed"
    return True, ""

async def _validate_common(db, event_id, track_id, team_id):
    track = await db.get(Track, track_id)
    if not track or track.event_id != event_id or not track.is_active:
        err(422, "invalid_track", "Invalid track for this event")

async def _form_fields(db, event_id) -> list:
    res = await db.execute(select(EventFormField).where(EventFormField.event_id == event_id).order_by(EventFormField.created_at))
    return res.scalars().all()

def _check_custom(fields: list, data: dict):
    """Enforce organizer-defined required fields at submit time."""
    data = data or {}
    for f in fields:
        v = data.get(f.id)
        if f.required and (v is None or str(v).strip() == ""):
            err(422, "validation_error", f"“{f.label}” is required to submit")
        if v is None or str(v).strip() == "":
            continue
        if f.field_type == "number":
            try:
                float(str(v))
            except ValueError:
                err(422, "validation_error", f"“{f.label}” must be a number")
        elif f.field_type == "select":
            if str(v) not in (f.options or []):
                err(422, "validation_error", f"“{f.label}” has an invalid option")
        elif len(str(v)) > 5000:
            err(422, "validation_error", f"“{f.label}” is too long")

@router.get("/submissions")
async def list_mine(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(Project, Team).join(TeamMember, TeamMember.team_id == Project.team_id).join(Team, Team.id == Project.team_id).where(TeamMember.user_id == user.id))
    return {"projects": [proj_out(p) for p, _ in res.all()]}

@router.post("/submissions")
async def create_sub(body: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    team_id = body.team_id
    event_id = body.event_id
    track_id = body.track_id
    title = (body.title or "").strip()
    if not team_id or not event_id or not track_id or not title:
        err(422, "validation_error", "team_id, event_id, track_id, title required")
    team = await _check_membership(db, user.id, team_id)
    if team.event_id != event_id:
        err(422, "validation_error", "Team does not belong to event")
    event = await db.get(Event, event_id)
    if not event:
        err(404, "not_found", "Event not found")
    await _validate_common(db, event_id, track_id, team_id)
    ok, msg = _deadline_open(event)
    if not ok:
        err(403, "deadline_passed", msg)
    # one project per team? allow multiple but keep simple: allow multiple
    p = Project(id=f"prj_{uuid.uuid4().hex[:8]}", event_id=event_id, team_id=team_id, track_id=track_id,
                title=title, summary=body.summary, description=body.description,
                repo_url=body.repo_url, demo_url=body.demo_url, live_url=body.live_url,
                thumbnail_url=body.thumbnail_url, custom_data=dict(body.custom_data or {}),
                status=ProjectStatus.DRAFT, submitted_at=None)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"project": proj_out(p)}

@router.get("/submissions/{project_id}")
async def get_sub(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    await _check_membership(db, user.id, p.team_id)
    return {"project": proj_out(p)}

@router.patch("/submissions/{project_id}")
async def patch_sub(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    team = await _check_membership(db, user.id, p.team_id)
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) != "DRAFT":
        err(409, "invalid_state_transition", "Only drafts can be edited")
    event = await db.get(Event, p.event_id)
    ok, msg = _deadline_open(event)
    if not ok:
        err(403, "deadline_passed", msg)
    if body.track_id is not None and body.track_id != p.track_id:
        await _validate_common(db, p.event_id, body.track_id, p.team_id)
        p.track_id = body.track_id
    update_data = body.dict(exclude_unset=True)
    for k in ("title", "summary", "description", "repo_url", "demo_url", "live_url", "thumbnail_url"):
        if k in update_data:
            setattr(p, k, update_data[k])
    if "custom_data" in update_data and isinstance(update_data["custom_data"], dict):
        merged = dict(p.custom_data or {})
        merged.update(update_data["custom_data"])
        p.custom_data = merged
    p.updated_at = utcnow()
    await db.commit()
    await db.refresh(p)
    return {"project": proj_out(p)}

@router.post("/submissions/{project_id}/submit")
async def submit_proj(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    await _check_membership(db, user.id, p.team_id)
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) == "SUBMITTED":
        err(409, "invalid_state_transition", "Already submitted")
    event = await db.get(Event, p.event_id)
    await _validate_common(db, p.event_id, p.track_id, p.team_id)
    if not p.title or not p.summary:
        err(422, "validation_error", "Title and summary required to submit")
    _check_custom(await _form_fields(db, p.event_id), p.custom_data)
    ok, msg = _deadline_open(event)
    if not ok:
        err(403, "deadline_passed", msg)
    p.status = ProjectStatus.SUBMITTED
    p.submitted_at = utcnow()
    p.updated_at = p.submitted_at
    await db.commit()
    await db.refresh(p)
    # Rolling judging (prompt_T2 §5): the submission becomes eligible the
    # moment it lands. This must never fail the submission itself — the
    # project is already committed, so any assignment failure is swallowed
    # after a best-effort audit row (record() never raises either).
    if event.rolling_judging:
        try:
            from app.modules.judging import assign as assign_svc
            out = await assign_svc.assign_project(db, p.id)
            await db.commit()
            if out["ok"] and out["assigned"]:
                await record(user, "event.assignment_created", target_type="project",
                             target_id=p.id, event_id=p.event_id,
                             detail={"title": p.title, "judges": out["assigned"]},
                             request=None)
        except Exception:
            await db.rollback()
            log = __import__("logging").getLogger("dogfood.judging")
            log.exception("rolling assignment failed for project=%s", p.id)
    return {"project": proj_out(p)}

@router.delete("/submissions/{project_id}")
async def delete_draft(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    await _check_membership(db, user.id, p.team_id)
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) != "DRAFT":
        err(409, "invalid_state_transition", "Only drafts can be deleted")
    await db.delete(p)
    await db.commit()
    return {"ok": True}

@router.post("/submissions/{project_id}/visibility")
async def set_visibility(project_id: str, body: VisibilityUpdate, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    # Gallery moderation is scoped: only this project's organizers may act.
    await require_manageable(db, user, p.event_id)
    was = p.is_visible
    p.is_visible = body.visible
    p.updated_at = utcnow()
    await db.commit()
    await record(user, "project.visibility_changed", target_type="project", target_id=p.id,
                 event_id=p.event_id, detail={"title": p.title, "from": was, "to": body.visible},
                 request=request)
    return {"ok": True, "is_visible": p.is_visible}
