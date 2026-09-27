from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Project, ProjectStatus, Event, EventStatus, Track, Team, User, EventParticipant
from app.shared.errors import err
from app.modules.auth.dependencies import optional_user
from app.modules.gallery.schemas import EventsListResponse, EventResponse, ProjectsListResponse, ProjectDetailResponse

router = APIRouter(tags=["public"])

def _is_staff(user) -> bool:
    if not user:
        return False
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role in ("ORGANIZER", "ADMIN")

def _is_published(e) -> bool:
    return (e.status.value if hasattr(e.status, "value") else str(e.status)) == "PUBLISHED"

def _guard_event(e, user):
    """Published events are public. Drafts are organizer/admin-only. Nothing leaks otherwise."""
    if not e:
        err(404, "not_found", "Event not found")
    if _is_published(e):
        return
    if _is_staff(user):
        return
    err(404, "not_found", "Event not found")

def _vis(e) -> str:
    v = e.gallery_visibility
    return (v.value if hasattr(v, "value") else str(v or "PUBLIC")).upper()

async def _guard_gallery(e, user, db: AsyncSession):
    """Who may browse this event's gallery.

    - Missing event, or draft + non-staff → 404 (no existence leak).
    - Published + PUBLIC → everyone.
    - Published + ORGANIZERS_ONLY → staff, else 403.
    - Published + PARTICIPANTS → staff or registered participants, else 403.
    """
    if not e:
        err(404, "not_found", "Event not found")
    if not _is_published(e):
        if _is_staff(user):
            return
        err(404, "not_found", "Event not found")
    vis = _vis(e)
    if vis == "PUBLIC":
        return
    if _is_staff(user):
        return
    if vis == "ORGANIZERS_ONLY":
        err(403, "forbidden", "This gallery is open to organizers only.")
    if vis == "PARTICIPANTS":
        if user:
            res = await db.execute(select(EventParticipant).where(
                EventParticipant.event_id == e.id, EventParticipant.user_id == user.id))
            if res.scalar_one_or_none():
                return
        err(403, "forbidden", "This gallery is open to registered participants and organizers. Join the event to browse it.")
    err(404, "not_found", "Event not found")

@router.get("/public/events", response_model=EventsListResponse)
async def public_events(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Event).where(Event.status == EventStatus.PUBLISHED).order_by(Event.name))
    out = []
    for e in res.scalars().all():
        out.append({"id": e.id, "slug": e.slug, "name": e.name, "description": e.description,
                    "submissions_close": e.submissions_close.isoformat() if e.submissions_close else None,
                    "status": "PUBLISHED"})
    return {"events": out}

@router.get("/public/events/{slug}", response_model=EventResponse)
async def public_event(slug: str, db: AsyncSession = Depends(get_db), user: User | None = Depends(optional_user)):
    res = await db.execute(select(Event).where(or_(Event.slug == slug, Event.id == slug)))
    e = res.scalar_one_or_none()
    _guard_event(e, user)
    staff = _is_staff(user)
    tq = select(Track).where(Track.event_id == e.id)
    if not staff:
        tq = tq.where(Track.is_active == True)  # noqa
    res2 = await db.execute(tq.order_by(Track.name))
    from app.models import Prize
    res3 = await db.execute(select(Prize).where(Prize.event_id == e.id).order_by(Prize.display_order))
    f = lambda x: x.isoformat() if x else None
    gv = e.gallery_visibility
    return {"event": {"id": e.id, "slug": e.slug, "name": e.name, "description": e.description,
                      "registration_start": f(e.registration_start), "registration_close": f(e.registration_close),
                      "event_start": f(e.event_start), "event_end": f(e.event_end),
                      "submissions_open": f(e.submissions_open), "submissions_close": f(e.submissions_close),
                      "gallery_visibility": (gv.value if hasattr(gv, "value") else str(gv or "PUBLIC"))},
            "tracks": [{"id": t.id, "name": t.name} for t in res2.scalars().all()],
            "prizes": [{"id": p.id, "name": p.name, "description": p.description, "value_desc": p.value_desc} for p in res3.scalars().all()]}

@router.get("/public/events/{slug}/projects", response_model=ProjectsListResponse)
async def public_projects(
    slug: str,
    q: str = Query("", max_length=100),
    track: str = Query("", max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user)
):
    res = await db.execute(select(Event).where(or_(Event.slug == slug, Event.id == slug)))
    e = res.scalar_one_or_none()
    await _guard_gallery(e, user, db)
    stmt = select(Project, Team, Track).join(Team, Team.id == Project.team_id).join(Track, Track.id == Project.track_id).where(
        Project.event_id == e.id, Project.status == ProjectStatus.SUBMITTED, Project.is_visible == True)  # noqa
    if track:
        stmt = stmt.where(or_(Track.id == track, Track.name == track))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Project.title.ilike(like), Project.summary.ilike(like), Team.name.ilike(like)))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(Project.submitted_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()
    items = [{"id": p.id, "title": p.title, "summary": p.summary, "team": tm.name, "team_id": tm.id,
              "track": tr.name, "track_id": tr.id, "repo_url": p.repo_url, "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None}
             for p, tm, tr in rows]
    return {"projects": items, "page": page, "page_size": page_size, "total": total}

@router.get("/public/projects/{project_id}", response_model=ProjectDetailResponse)
async def public_project(project_id: str, db: AsyncSession = Depends(get_db), user: User | None = Depends(optional_user)):
    from sqlalchemy import select as sel
    p = await db.get(Project, project_id)
    if not p or (p.status.value if hasattr(p.status, "value") else str(p.status)) != "SUBMITTED" or not p.is_visible:
        err(404, "not_found", "Project not found")
    e = await db.get(Event, p.event_id)
    await _guard_gallery(e, user, db)
    tm = await db.get(Team, p.team_id)
    tr = await db.get(Track, p.track_id)
    from app.models import TeamMember, User
    res = await db.execute(sel(User.display_name).join(TeamMember, TeamMember.user_id == User.id).where(TeamMember.team_id == p.team_id).order_by(User.display_name))
    members = [r[0] for r in res.all()]
    return {"project": {"id": p.id, "title": p.title, "summary": p.summary, "description": p.description,
                        "team": tm.name if tm else None, "members": members, "track": tr.name if tr else None,
                        "repo_url": p.repo_url, "demo_url": p.demo_url,
                        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None}}
