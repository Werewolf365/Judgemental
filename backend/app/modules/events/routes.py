import re
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Event, EventStatus, Track, Prize, EventParticipant, User, ParticipantRegistration, GalleryVisibility
from app.modules.auth.dependencies import current_user, require_roles
from app.modules.events.schemas import EventIn, TrackIn, PrizeIn, RegistrationForm
from app.shared.errors import err
from app.shared.clock import utcnow

router = APIRouter(tags=["events"])

def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "event"

def parse_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt
    except Exception:
        err(422, "validation_error", f"Invalid datetime: {v}")

def check_ranges(d: dict):
    pairs = [("registration_start", "registration_close"), ("event_start", "event_end"), ("submissions_open", "submissions_close")]
    for a, b in pairs:
        if d.get(a) and d.get(b) and d[a] > d[b]:
            err(422, "validation_error", f"{a} must be <= {b}")

def event_out(e: Event) -> dict:
    f = lambda x: x.isoformat() if x else None
    return {"id": e.id, "slug": e.slug, "name": e.name, "description": e.description,
            "registration_start": f(e.registration_start), "registration_close": f(e.registration_close),
            "event_start": f(e.event_start), "event_end": f(e.event_end),
            "submissions_open": f(e.submissions_open), "submissions_close": f(e.submissions_close),
            "status": e.status.value if hasattr(e.status, "value") else str(e.status),
            "gallery_visibility": e.gallery_visibility.value if hasattr(e.gallery_visibility, "value") else str(e.gallery_visibility or "PUBLIC")}

@router.get("/events")
async def list_all_events(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    res = await db.execute(select(Event).order_by(Event.created_at.desc()))
    return {"events": [event_out(e) for e in res.scalars().all()]}

@router.get("/events/{event_id}/stats")
async def event_stats(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from sqlalchemy import func
    from app.models import Team, Project, ProjectStatus, EventParticipant
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    tracks = (await db.execute(select(func.count()).select_from(Track).where(Track.event_id == e.id))).scalar() or 0
    prizes = (await db.execute(select(func.count()).select_from(Prize).where(Prize.event_id == e.id))).scalar() or 0
    participants = (await db.execute(select(func.count()).select_from(EventParticipant).where(EventParticipant.event_id == e.id))).scalar() or 0
    teams = (await db.execute(select(func.count()).select_from(Team).where(Team.event_id == e.id))).scalar() or 0
    projects = (await db.execute(select(func.count()).select_from(Project).where(Project.event_id == e.id))).scalar() or 0
    submitted = (await db.execute(select(func.count()).select_from(Project).where(Project.event_id == e.id, Project.status == ProjectStatus.SUBMITTED))).scalar() or 0
    return {"event": event_out(e), "stats": {"tracks": tracks, "prizes": prizes,
            "participants": participants, "teams": teams,
            "projects": projects, "drafts": projects - submitted, "submitted": submitted}}

@router.post("/events")
async def create_event(body: EventIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    if not (body.name or "").strip():
        err(422, "validation_error", "Event name is required")
    d = {"registration_start": parse_dt(body.registration_start), "registration_close": parse_dt(body.registration_close),
         "event_start": parse_dt(body.event_start), "event_end": parse_dt(body.event_end),
         "submissions_open": parse_dt(body.submissions_open), "submissions_close": parse_dt(body.submissions_close)}
    check_ranges(d)
    slug = body.slug or slugify(body.name)
    ex = await db.execute(select(Event).where(Event.slug == slug))
    if ex.scalar_one_or_none():
        err(409, "already_joined", "Slug already taken")
    import uuid
    e = Event(id=f"evt_{uuid.uuid4().hex[:8]}", slug=slug, name=body.name, description=body.description,
              status=EventStatus.DRAFT, created_by=user.id, **d)
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return {"event": event_out(e)}

@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    e = await db.get(Event, event_id)
    if not e:
        # try slug
        res = await db.execute(select(Event).where(Event.slug == event_id))
        e = res.scalar_one_or_none()
    if not e:
        err(404, "not_found", "Event not found")
    return {"event": event_out(e)}

@router.patch("/events/{event_id}")
async def patch_event(event_id: str, body: EventIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    vals = body.model_dump(exclude_unset=True)
    for k in ("registration_start", "registration_close", "event_start", "event_end", "submissions_open", "submissions_close"):
        if k in vals:
            vals[k] = parse_dt(vals[k])
    merged = {"registration_start": vals.get("registration_start", e.registration_start),
              "registration_close": vals.get("registration_close", e.registration_close),
              "event_start": vals.get("event_start", e.event_start),
              "event_end": vals.get("event_end", e.event_end),
              "submissions_open": vals.get("submissions_open", e.submissions_open),
              "submissions_close": vals.get("submissions_close", e.submissions_close)}
    check_ranges(merged)
    if "gallery_visibility" in vals and vals["gallery_visibility"] is not None:
        try:
            e.gallery_visibility = GalleryVisibility(str(vals["gallery_visibility"]).upper())
        except ValueError:
            err(422, "validation_error", "gallery_visibility must be PUBLIC, PARTICIPANTS or ORGANIZERS_ONLY")
    for k, v in vals.items():
        if k in ("name", "slug") and not v:
            continue  # never wipe name/slug with an empty PATCH value
        if k == "slug" and v:
            setattr(e, k, v)
        elif k != "slug" and k in merged or k in ("name", "description"):
            setattr(e, k, v)
    for k, v in merged.items():
        setattr(e, k, v)
    await db.commit()
    await db.refresh(e)
    return {"event": event_out(e)}

@router.post("/events/{event_id}/publish")
async def publish(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    if not e.name or not e.submissions_close:
        err(422, "validation_error", "Event needs name and submissions_close to publish")
    e.status = EventStatus.PUBLISHED
    await db.commit()
    return {"event": event_out(e)}

@router.post("/events/{event_id}/unpublish")
async def unpublish(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    e.status = EventStatus.DRAFT
    await db.commit()
    return {"event": event_out(e)}

@router.post("/events/{event_id}/join")
async def join_event(event_id: str, body: RegistrationForm, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    now = utcnow()
    def aware(x):
        if x is None:
            return None
        return x if x.tzinfo else x.replace(tzinfo=__import__("datetime").timezone.utc)
    rc = aware(e.registration_close)
    rs = aware(e.registration_start)
    if rc and now > rc:
        err(403, "deadline_passed", "Registration is closed")
    if rs and now < rs:
        err(403, "forbidden", "Registration has not opened")
    from sqlalchemy.dialects.postgresql import insert
    
    # Use UPSERT for EventParticipant in case it exists but was somehow missed
    stmt1 = insert(EventParticipant).values(event_id=e.id, user_id=user.id)
    stmt1 = stmt1.on_conflict_do_nothing(index_elements=['event_id', 'user_id'])
    await db.execute(stmt1)
    
    # Use UPSERT for ParticipantRegistration
    stmt2 = insert(ParticipantRegistration).values(
        event_id=e.id,
        user_id=user.id,
        full_name=body.fullName,
        email=body.email,
        phone=body.phone,
        age=body.age,
        degree=body.degree,
        year_of_study=body.yearOfStudy,
        institution=body.institution,
        category=body.category,
        tshirt_size=body.tshirtSize,
        dietary_restrictions=body.dietaryRestrictions
    )
    stmt2 = stmt2.on_conflict_do_update(
        index_elements=['event_id', 'user_id'],
        set_={
            'full_name': stmt2.excluded.full_name,
            'email': stmt2.excluded.email,
            'phone': stmt2.excluded.phone,
            'age': stmt2.excluded.age,
            'degree': stmt2.excluded.degree,
            'year_of_study': stmt2.excluded.year_of_study,
            'institution': stmt2.excluded.institution,
            'category': stmt2.excluded.category,
            'tshirt_size': stmt2.excluded.tshirt_size,
            'dietary_restrictions': stmt2.excluded.dietary_restrictions,
            'updated_at': utcnow()
        }
    )
    await db.execute(stmt2)
    
    await db.commit()
    return {"ok": True}

@router.get("/events/{event_id}/membership")
async def membership(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    from app.models import Team, TeamMember
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    res = await db.execute(select(EventParticipant).where(EventParticipant.event_id == e.id, EventParticipant.user_id == user.id))
    joined = res.scalar_one_or_none() is not None
    team_id = None
    if joined:
        res2 = await db.execute(select(Team.id).join(TeamMember, TeamMember.team_id == Team.id).where(Team.event_id == e.id, TeamMember.user_id == user.id))
        team_id = res2.scalar_one_or_none()
    return {"joined": joined, "team_id": team_id}

@router.delete("/events/{event_id}/join")
async def leave_event(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    from app.models import Team, TeamMember
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    res = await db.execute(select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(Team.event_id == e.id, TeamMember.user_id == user.id))
    if res.first():
        err(409, "already_joined", "Leave your team before leaving the event")
    res2 = await db.execute(select(EventParticipant).where(EventParticipant.event_id == e.id, EventParticipant.user_id == user.id))
    p = res2.scalar_one_or_none()
    if not p:
        return {"ok": True, "already": True}
    await db.delete(p)
    res3 = await db.execute(select(ParticipantRegistration).where(ParticipantRegistration.event_id == e.id, ParticipantRegistration.user_id == user.id))
    pr = res3.scalar_one_or_none()
    if pr:
        await db.delete(pr)
    await db.commit()
    return {"ok": True}

@router.get("/events/{event_id}/participants")
async def list_participants(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.models import Team, TeamMember
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    res = await db.execute(select(EventParticipant, User).join(User, User.id == EventParticipant.user_id).where(EventParticipant.event_id == e.id).order_by(User.display_name))
    out = []
    for part, u in res.all():
        res2 = await db.execute(select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(Team.event_id == e.id, TeamMember.user_id == u.id))
        t = res2.scalar_one_or_none()
        out.append({"user_id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                    "joined_at": part.joined_at.isoformat() if part.joined_at else None,
                    "team_id": t.id if t else None, "team_name": t.name if t else None})
    return {"participants": out}

@router.get("/events/{event_id}/submissions")
async def list_event_submissions(event_id: str, status: str = "", db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.models import Team, Track, Project, ProjectStatus
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    stmt = select(Project, Team, Track).join(Team, Team.id == Project.team_id).join(Track, Track.id == Project.track_id).where(Project.event_id == e.id)
    if status:
        try:
            stmt = stmt.where(Project.status == ProjectStatus(status.upper()))
        except ValueError:
            err(422, "validation_error", "Unknown status")
    stmt = stmt.order_by(Project.updated_at.desc())
    out = []
    for p, tm, tr in (await db.execute(stmt)).all():
        out.append({"id": p.id, "title": p.title, "summary": p.summary, "team": tm.name, "team_id": tm.id,
                    "track": tr.name, "track_id": tr.id, "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                    "is_visible": p.is_visible, "repo_url": p.repo_url,
                    "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None})
    return {"submissions": out, "total": len(out)}

# Tracks
@router.get("/events/{event_id}/tracks")
async def list_tracks(event_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Track).where(Track.event_id == event_id).order_by(Track.name))
    return {"tracks": [{"id": t.id, "event_id": t.event_id, "name": t.name, "is_active": t.is_active} for t in res.scalars().all()]}

@router.post("/events/{event_id}/tracks")
async def create_track(event_id: str, body: TrackIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await db.get(Event, event_id)
    if not e:
        err(404, "not_found", "Event not found")
    import uuid
    t = Track(id=f"trk_{uuid.uuid4().hex[:8]}", event_id=event_id, name=body.name, is_active=True)
    db.add(t)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        err(409, "already_joined", "Track name already exists for this event")
    await db.refresh(t)
    return {"track": {"id": t.id, "event_id": t.event_id, "name": t.name, "is_active": t.is_active}}

@router.patch("/tracks/{track_id}")
async def patch_track(track_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    t = await db.get(Track, track_id)
    if not t:
        err(404, "not_found", "Track not found")
    if "name" in body:
        t.name = body["name"]
    if "is_active" in body:
        t.is_active = bool(body["is_active"])
    await db.commit()
    return {"track": {"id": t.id, "name": t.name, "is_active": t.is_active}}

@router.delete("/tracks/{track_id}")
async def delete_track(track_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.models import Project
    from sqlalchemy import select as sel
    t = await db.get(Track, track_id)
    if not t:
        err(404, "not_found", "Track not found")
    used = await db.execute(sel(Project).where(Project.track_id == track_id).limit(1))
    if used.scalar_one_or_none():
        t.is_active = False
        await db.commit()
        return {"ok": True, "deactivated": True}
    await db.delete(t)
    await db.commit()
    return {"ok": True}

# Prizes
@router.get("/events/{event_id}/prizes")
async def list_prizes(event_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Prize).where(Prize.event_id == event_id).order_by(Prize.display_order))
    return {"prizes": [{"id": p.id, "event_id": p.event_id, "track_id": p.track_id, "name": p.name, "description": p.description, "value_desc": p.value_desc, "display_order": p.display_order} for p in res.scalars().all()]}

@router.post("/events/{event_id}/prizes")
async def create_prize(event_id: str, body: PrizeIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    import uuid
    p = Prize(id=f"prz_{uuid.uuid4().hex[:8]}", event_id=event_id, track_id=body.track_id, name=body.name,
              description=body.description, value_desc=body.value_desc, display_order=body.display_order)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"prize": {"id": p.id, "name": p.name}}

@router.patch("/prizes/{prize_id}")
async def patch_prize(prize_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    p = await db.get(Prize, prize_id)
    if not p:
        err(404, "not_found", "Prize not found")
    for k in ("name", "description", "value_desc", "track_id", "display_order"):
        if k in body:
            setattr(p, k, body[k])
    await db.commit()
    return {"ok": True}

@router.delete("/prizes/{prize_id}")
async def delete_prize(prize_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    p = await db.get(Prize, prize_id)
    if not p:
        err(404, "not_found", "Prize not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}
