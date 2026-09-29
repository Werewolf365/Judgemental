import re
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Event, EventStatus, Track, Prize, EventParticipant, EventOrganizer, User, ParticipantRegistration, GalleryVisibility, EventFormField
from app.modules.auth.dependencies import current_user, optional_user, require_roles
from app.modules.events.access import (managed_event, manageable_event_ids, owned_only,
                                       require_manageable, visible_event_or_404, role_of)
from app.modules.events.schemas import EventIn, TrackIn, PrizeIn, RegistrationForm, FormFieldIn, OrganizerAssignIn
from app.shared.errors import err
from app.shared.audit import record
from app.shared.clock import utcnow

router = APIRouter(tags=["events"])

# Roles that run a hackathon rather than compete in one. Staff and the judging
# panel are never competitors, so they are refused registration outright: an
# organizer's own event must not put them in its participant roster, and a
# judge must not end up eligible to submit into the event they are judging.
# The check is on the account's role, not on which event is being joined, so
# there is no event that lets a staff account slip through.
NON_PARTICIPANT_ROLES = ("ORGANIZER", "ADMIN", "JUDGE")

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
            "timezone": e.timezone or "UTC",
            "certificates_enabled": e.certificates_enabled,
            "status": e.status.value if hasattr(e.status, "value") else str(e.status),
            "gallery_visibility": e.gallery_visibility.value if hasattr(e.gallery_visibility, "value") else str(e.gallery_visibility or "PUBLIC")}

@router.get("/events")
async def list_all_events(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    # Scoped: an organizer only ever sees the events they run.
    ids = await manageable_event_ids(db, user)
    res = await db.execute(owned_only(select(Event).order_by(Event.created_at.desc()), ids))
    return {"events": [event_out(e) for e in res.scalars().all()]}

@router.get("/events/{event_id}/stats")
async def event_stats(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from sqlalchemy import func
    from app.models import Team, Project, ProjectStatus, EventParticipant
    e = await managed_event(db, user, event_id)
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
async def create_event(body: EventIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
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
              status=EventStatus.DRAFT, created_by=user.id, timezone=(body.timezone or "UTC")[:64], **d)
    db.add(e)
    # The creator is the first organizer of their own event.
    db.add(EventOrganizer(event_id=e.id, user_id=user.id, assigned_by=user.id))
    await db.commit()
    await db.refresh(e)
    await record(user, "event.created", target_type="event", target_id=e.id, event_id=e.id,
                 detail={"name": e.name, "slug": e.slug}, request=request)
    return {"event": event_out(e)}

@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    e = await db.get(Event, event_id)
    if not e:
        # try slug
        res = await db.execute(select(Event).where(Event.slug == event_id))
        e = res.scalar_one_or_none()
    # Published events are readable by anyone; drafts only by their organizers.
    await visible_event_or_404(db, user, e)
    return {"event": event_out(e)}

@router.patch("/events/{event_id}")
async def patch_event(event_id: str, body: EventIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
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
    if "timezone" in vals and vals["timezone"]:
        e.timezone = str(vals["timezone"])[:64]
    if vals.get("certificates_enabled") is not None:
        e.certificates_enabled = vals["certificates_enabled"]
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
    await record(user, "event.updated", target_type="event", target_id=e.id, event_id=e.id,
                 detail={"fields": sorted(vals.keys())}, request=request)
    return {"event": event_out(e)}

@router.post("/events/{event_id}/publish")
async def publish(event_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if not e.name or not e.submissions_close:
        err(422, "validation_error", "Event needs name and submissions_close to publish")
    e.status = EventStatus.PUBLISHED
    await db.commit()
    await record(user, "event.published", target_type="event", target_id=e.id, event_id=e.id,
                 detail={"name": e.name}, request=request)
    return {"event": event_out(e)}

@router.post("/events/{event_id}/unpublish")
async def unpublish(event_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    e.status = EventStatus.DRAFT
    await db.commit()
    await record(user, "event.unpublished", target_type="event", target_id=e.id, event_id=e.id,
                 detail={"name": e.name}, request=request)
    return {"event": event_out(e)}

@router.post("/events/{event_id}/join")
async def join_event(event_id: str, body: RegistrationForm, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    # Staff and judges run events, they do not compete in them. Refused before
    # the event is even loaded so the answer does not depend on the event.
    role = role_of(user)
    if role in NON_PARTICIPANT_ROLES:
        err(403, "forbidden",
            f"{role.title()} accounts do not register for events. Run one from the organizer console instead.")
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

    # The submitted form counts as updating the reusable profile: next
    # event's registration prefills from these values (still editable there).
    u = await db.get(User, user.id)
    u.profile_phone = body.phone.strip()
    u.profile_age = body.age
    u.profile_degree = body.degree.strip()
    u.profile_year = body.yearOfStudy.strip()
    u.profile_institution = body.institution.strip()
    u.profile_tshirt = (body.tshirtSize or "").strip() or None
    u.profile_dietary = (body.dietaryRestrictions or "").strip() or None

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
    e = await managed_event(db, user, event_id)
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
    e = await managed_event(db, user, event_id)
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
                    "is_visible": p.is_visible, "repo_url": p.repo_url, "custom_data": p.custom_data or {},
                    "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None})
    return {"submissions": out, "total": len(out)}

# Tracks
@router.get("/events/{event_id}/tracks")
async def list_tracks(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(optional_user)):
    # Public once the event is published; drafts stay organizer-only.
    await visible_event_or_404(db, user, await db.get(Event, event_id))
    res = await db.execute(select(Track).where(Track.event_id == event_id).order_by(Track.name))
    return {"tracks": [{"id": t.id, "event_id": t.event_id, "name": t.name, "is_active": t.is_active} for t in res.scalars().all()]}

@router.post("/events/{event_id}/tracks")
async def create_track(event_id: str, body: TrackIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if not (body.name or "").strip():
        err(422, "validation_error", "Track name is required")
    import uuid
    t = Track(id=f"trk_{uuid.uuid4().hex[:8]}", event_id=e.id, name=body.name, is_active=True)
    db.add(t)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        err(409, "already_joined", "Track name already exists for this event")
    await db.refresh(t)
    await record(user, "event.track_created", target_type="track", target_id=t.id, event_id=e.id,
                 detail={"name": t.name}, request=request)
    return {"track": {"id": t.id, "event_id": t.event_id, "name": t.name, "is_active": t.is_active}}

@router.patch("/tracks/{track_id}")
async def patch_track(track_id: str, body: dict, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    t = await db.get(Track, track_id)
    if not t:
        err(404, "not_found", "Track not found")
    # The track id alone must not be enough: check the parent event too.
    await require_manageable(db, user, t.event_id)
    if "name" in body:
        t.name = body["name"]
    if "is_active" in body:
        t.is_active = bool(body["is_active"])
    await db.commit()
    await record(user, "event.track_updated", target_type="track", target_id=t.id, event_id=t.event_id,
                 detail={"fields": sorted(body.keys())}, request=request)
    return {"track": {"id": t.id, "name": t.name, "is_active": t.is_active}}

@router.delete("/tracks/{track_id}")
async def delete_track(track_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.models import Project
    from sqlalchemy import select as sel
    t = await db.get(Track, track_id)
    if not t:
        err(404, "not_found", "Track not found")
    await require_manageable(db, user, t.event_id)
    used = await db.execute(sel(Project).where(Project.track_id == track_id).limit(1))
    if used.scalar_one_or_none():
        t.is_active = False
        await db.commit()
        await record(user, "event.track_deactivated", target_type="track", target_id=t.id,
                     event_id=t.event_id, detail={"name": t.name, "reason": "in use by projects"}, request=request)
        return {"ok": True, "deactivated": True}
    await db.delete(t)
    await db.commit()
    await record(user, "event.track_deleted", target_type="track", target_id=t.id,
                 event_id=t.event_id, detail={"name": t.name}, request=request)
    return {"ok": True}

# Prizes
@router.get("/events/{event_id}/prizes")
async def list_prizes(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(optional_user)):
    await visible_event_or_404(db, user, await db.get(Event, event_id))
    res = await db.execute(select(Prize).where(Prize.event_id == event_id).order_by(Prize.display_order))
    return {"prizes": [{"id": p.id, "event_id": p.event_id, "track_id": p.track_id, "name": p.name, "description": p.description, "value_desc": p.value_desc, "display_order": p.display_order} for p in res.scalars().all()]}

@router.post("/events/{event_id}/prizes")
async def create_prize(event_id: str, body: PrizeIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if not (body.name or "").strip():
        err(422, "validation_error", "Prize name is required")
    if body.track_id:
        tr = await db.get(Track, body.track_id)
        # A prize may only hang off a track of its own event.
        if not tr or tr.event_id != e.id:
            err(422, "validation_error", "Invalid track for this event")
    import uuid
    p = Prize(id=f"prz_{uuid.uuid4().hex[:8]}", event_id=e.id, track_id=body.track_id, name=body.name,
              description=body.description, value_desc=body.value_desc, display_order=body.display_order)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await record(user, "event.prize_created", target_type="prize", target_id=p.id, event_id=e.id,
                 detail={"name": p.name}, request=request)
    return {"prize": {"id": p.id, "name": p.name}}

@router.patch("/prizes/{prize_id}")
async def patch_prize(prize_id: str, body: dict, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    p = await db.get(Prize, prize_id)
    if not p:
        err(404, "not_found", "Prize not found")
    await require_manageable(db, user, p.event_id)
    for k in ("name", "description", "value_desc", "track_id", "display_order"):
        if k in body:
            setattr(p, k, body[k])
    await db.commit()
    await record(user, "event.prize_updated", target_type="prize", target_id=p.id, event_id=p.event_id,
                 detail={"fields": sorted(body.keys())}, request=request)
    return {"ok": True}

@router.delete("/prizes/{prize_id}")
async def delete_prize(prize_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    p = await db.get(Prize, prize_id)
    if not p:
        err(404, "not_found", "Prize not found")
    await require_manageable(db, user, p.event_id)
    name = p.name
    await db.delete(p)
    await db.commit()
    await record(user, "event.prize_deleted", target_type="prize", target_id=prize_id,
                 event_id=p.event_id, detail={"name": name}, request=request)
    return {"ok": True}

# ---- Organizer-defined submission form fields ----
# Participants read these (public, like tracks) to render the project form.
# Only organizers manage them. Stored answers live on projects.custom_data.

def field_out(f: EventFormField) -> dict:
    return {"id": f.id, "event_id": f.event_id, "label": f.label,
            "field_type": f.field_type, "required": f.required,
            "options": f.options or []}

@router.get("/events/{event_id}/form-fields")
async def list_form_fields(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(optional_user)):
    # Participants need these to render the submit form, but only for a
    # published event; an unpublished form is organizer-only.
    await visible_event_or_404(db, user, await db.get(Event, event_id))
    res = await db.execute(select(EventFormField).where(EventFormField.event_id == event_id).order_by(EventFormField.created_at))
    return {"fields": [field_out(f) for f in res.scalars().all()]}

@router.post("/events/{event_id}/form-fields")
async def create_form_field(event_id: str, body: FormFieldIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    import uuid as _u
    f = EventFormField(id=f"fld_{_u.uuid4().hex[:8]}", event_id=e.id, label=body.label.strip(),
                       field_type=body.field_type, required=body.required, options=body.options)
    if not f.label:
        err(422, "validation_error", "Field label is required")
    db.add(f)
    await db.commit()
    await db.refresh(f)
    await record(user, "event.form_field_created", target_type="form_field", target_id=f.id, event_id=e.id,
                 detail={"label": f.label, "field_type": f.field_type}, request=request)
    return {"field": field_out(f)}

@router.patch("/form-fields/{field_id}")
async def patch_form_field(field_id: str, body: FormFieldIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    f = await db.get(EventFormField, field_id)
    if not f:
        err(404, "not_found", "Field not found")
    await require_manageable(db, user, f.event_id)
    # Full-object edit: label/type/required/options all organizer-editable.
    if not body.label.strip():
        err(422, "validation_error", "Field label is required")
    f.label = body.label.strip()
    f.field_type = body.field_type
    f.required = body.required
    f.options = body.options
    await db.commit()
    await db.refresh(f)
    await record(user, "event.form_field_updated", target_type="form_field", target_id=f.id,
                 event_id=f.event_id, detail={"label": f.label, "required": f.required}, request=request)
    return {"field": field_out(f)}

@router.delete("/form-fields/{field_id}")
async def delete_form_field(field_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    f = await db.get(EventFormField, field_id)
    if not f:
        err(404, "not_found", "Field not found")
    await require_manageable(db, user, f.event_id)
    label = f.label
    # Already-stored answers stay on projects; they render only for live fields.
    await db.delete(f)
    await db.commit()
    await record(user, "event.form_field_deleted", target_type="form_field", target_id=field_id,
                 event_id=f.event_id, detail={"label": label}, request=request)
    return {"ok": True}

# ---- Organizer roster ----
# Membership decides who can manage this event. Assignment never grants a
# role: the account must already be an ORGANIZER or ADMIN, so this endpoint
# cannot be used to promote a participant into one.

def organizer_out(u: User, e: Event, assigned_by: str | None = None, assigned_at=None) -> dict:
    return {"user_id": u.id, "email": u.email, "display_name": u.display_name,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "is_owner": e.created_by == u.id,
            "assigned_by": assigned_by,
            "assigned_at": assigned_at.isoformat() if assigned_at else None}

@router.get("/events/{event_id}/organizers")
async def list_organizers(event_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    res = await db.execute(
        select(User, EventOrganizer.assigned_by, EventOrganizer.created_at)
        .join(EventOrganizer, EventOrganizer.user_id == User.id)
        .where(EventOrganizer.event_id == e.id).order_by(User.display_name))
    rows = {u.id: organizer_out(u, e, by, at) for u, by, at in res.all()}
    # The creator stays listed even if their row predates this table.
    if e.created_by and e.created_by not in rows:
        owner = await db.get(User, e.created_by)
        if owner:
            rows[e.created_by] = organizer_out(owner, e)
    return {"organizers": list(rows.values())}

@router.post("/events/{event_id}/organizers")
async def add_organizer(event_id: str, body: OrganizerAssignIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if not body.email and not body.user_id:
        err(422, "validation_error", "Provide the organizer's email")
    stmt = select(User).where(User.email_norm == body.email) if body.email else select(User).where(User.id == body.user_id)
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        # Same answer whether the account is missing or invisible to us: no
        # directory enumeration through this endpoint.
        err(404, "not_found", "No account with that email. Ask them to sign up first, then an admin can grant the organizer role.")
    role = target.role.value if hasattr(target.role, "value") else str(target.role)
    if role not in ("ORGANIZER", "ADMIN"):
        err(422, "validation_error", f"{target.email} is a {role.lower()}, not an organizer. Grant the organizer role first.")
    ins = pg_insert(EventOrganizer).values(event_id=e.id, user_id=target.id, assigned_by=user.id)
    ins = ins.on_conflict_do_nothing(index_elements=["event_id", "user_id"])
    await db.execute(ins)
    await db.commit()
    res = await db.execute(select(EventOrganizer).where(EventOrganizer.event_id == e.id, EventOrganizer.user_id == target.id))
    row = res.scalar_one_or_none()
    await record(user, "event.organizer_added", target_type="user", target_id=target.id, event_id=e.id,
                 detail={"email": target.email, "role": role, "event": e.name}, request=request)
    return {"organizer": organizer_out(target, e, row.assigned_by if row else None, row.created_at if row else None), "added": True}

@router.delete("/events/{event_id}/organizers/{user_id}")
async def remove_organizer(event_id: str, user_id: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if e.created_by == user_id:
        err(409, "invalid_state_transition", "The event creator cannot be removed")
    res = await db.execute(select(EventOrganizer).where(EventOrganizer.event_id == e.id, EventOrganizer.user_id == user_id))
    row = res.scalar_one_or_none()
    if not row:
        # Idempotent: already gone.
        return {"ok": True, "removed": False}
    gone = await db.get(User, user_id)
    await db.delete(row)
    await db.commit()
    await record(user, "event.organizer_removed", target_type="user", target_id=user_id, event_id=e.id,
                 detail={"email": getattr(gone, "email", None), "event": e.name}, request=request)
    return {"ok": True, "removed": True}
