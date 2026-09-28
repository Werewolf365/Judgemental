"""T3 community voting + comments.

Organizer surface (ORGANIZER/ADMIN, event-scoped through managed_event):
  PATCH/GET /events/{id}/voting   ballot-box settings + turnout
  GET     /events/{id}/audit      this event's audit trail, readable without
                                  a database client (subset of the admin
                                  reader: action/search/limit filters)

Voter surface (no login required unless the event's mode says so):
  GET  /public/events/{slug}/ballot          box + my allocations + budget
  POST /public/events/{slug}/ballot          set one cell (0 retracts)
  GET  /public/events/{slug}/votes/results   tally, only after close
  GET/POST /public/projects/{id}/comments    thread (visibility-gated)
  PATCH /comments/{id}                        staff hide/show (organizer)

Anti-abuse lives on every write: quadratic budgets (hard math cap),
one cell per (voter, project) via unique constraint, own-team block for
logged-in voters, per-IP token-bucket rate limits with audited refusals,
and fingerprint-collision turnout signals for organizers.
"""
import random
import hashlib
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (AuditLog, Ballot, Comment, Event, Project, ProjectStatus,
                        User)
from app.modules.auth.dependencies import optional_user, require_roles
from app.modules.events.access import managed_event, require_manageable
from app.modules.events.routes import parse_dt
from app.modules.voting import quadratic, ratelimit
from app.modules.voting import service
from app.modules.voting.schemas import BallotIn, CommentIn, VotingSettingsIn
from app.shared.audit import record
from app.shared.clock import utcnow
from app.shared.errors import err

router = APIRouter(tags=["voting"])


def _ip(request: Request | None) -> str:
    """Left-most X-Forwarded-For (what nginx sets) else direct peer.
    Attribution only — spoofable past the gateway, never authentication."""
    if request is not None:
        fwd = request.headers.get("x-forwarded-for")
        if fwd and fwd.split(",")[0].strip():
            return fwd.split(",")[0].strip()
        if request.client:
            return request.client.host
    return "unknown"


async def _public_event(db: AsyncSession, slug: str) -> Event:
    from sqlalchemy import or_
    res = await db.execute(select(Event).where(
        or_(Event.slug == slug, Event.id == slug)))
    e = res.scalar_one_or_none()
    if not e:
        err(404, "not_found", "Event not found")
    return e


async def _limited(request: Request, user, route: str, action: str,
                 event_id: str) -> None:
    """Token-bucket gate. Refusals are audited (record never raises, so the
    429 below always fires) so organizers see attempts, not just successes."""
    key = user.id if user is not None else _ip(request)
    ok, retry = ratelimit.check(str(key), route)
    if not ok:
        await record(user, action, target_type="event", target_id=event_id,
                     event_id=event_id, detail={"route": route},
                     request=request)
        err(429, "rate_limited",
            f"too many requests — try again in {retry}s")


# ---- organizer settings ----

@router.get("/events/{event_id}/voting")
async def voting_settings(event_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(func.count()).select_from(Ballot).where(
        Ballot.event_id == e.id))
    n_ballots = res.scalar() or 0
    res = await db.execute(select(func.count(func.distinct(Ballot.voter_key))).where(
        Ballot.event_id == e.id))
    n_voters = res.scalar() or 0
    res = await db.execute(
        select(Ballot.fp_hash, func.count(func.distinct(Ballot.voter_key))).where(
            Ballot.event_id == e.id, Ballot.fp_hash.is_not(None)).group_by(
            Ballot.fp_hash).having(func.count(func.distinct(Ballot.voter_key)) > 1))
    collisions = [{"fp": fp, "voters": n} for fp, n in res.all()]
    return {"config": service.voting_config_out(e),
            "turnout": {"voters": n_voters, "ballots": n_ballots,
                        "fp_collisions": collisions}}


@router.patch("/events/{event_id}/voting")
async def voting_configure(event_id: str, body: VotingSettingsIn, request: Request,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    vals = body.model_dump(exclude_unset=True)
    if "voting_close" in vals:
        vals["voting_close"] = parse_dt(vals["voting_close"]) if vals["voting_close"] else None
    for k in ("voting_enabled", "voting_close", "voting_mode", "comments_visibility"):
        if k in vals and vals[k] is not None:
            setattr(e, k, vals[k])
    e.updated_at = utcnow()
    await db.commit()
    await db.refresh(e)
    await record(user, "event.voting_configured", target_type="event", target_id=e.id,
                 event_id=e.id, detail={"fields": sorted(vals.keys())}, request=request)
    return {"config": service.voting_config_out(e)}


@router.get("/events/{event_id}/audit")
async def event_audit(event_id: str, action: str = Query("", max_length=80),
                      q: str = Query("", max_length=80),
                      limit: int = Query(100, ge=1, le=500),
                      db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """This event's audit trail for organizers — same rows the admin reader
    sees, scoped to one event so no database client is ever needed."""
    e = await managed_event(db, user, event_id)
    where = [AuditLog.event_id == e.id]
    if action.strip():
        where.append(AuditLog.action == action.strip())
    if q.strip():
        like = f"%{q.strip()}%"
        where.append(AuditLog.action.ilike(like) | AuditLog.actor_email.ilike(like)
                     | AuditLog.target_id.ilike(like))
    rows = (await db.execute(select(AuditLog).where(*where).order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit))).scalars().all()
    return {"entries": [{
        "id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
        "actor_email": r.actor_email, "action": r.action,
        "target_type": r.target_type, "target_id": r.target_id,
        "detail": r.detail or {}, "ip": r.ip} for r in rows]}


# ---- ballot box ----

def _box_projects(projects: list, voter_key: str | None) -> list:
    items = [{"id": p.id, "title": p.title, "summary": p.summary} for p in projects]
    if voter_key:
        seed = int(hashlib.sha256(f"{voter_key}".encode()).hexdigest(), 16) % (2 ** 32)
        random.Random(seed).shuffle(items)  # stable per voter, random across voters
    return items


@router.get("/public/events/{slug}/ballot")
async def ballot_box(slug: str, voter_id: str = Query("", max_length=64),
                     email: str = Query("", max_length=320),
                     db: AsyncSession = Depends(get_db),
                     user: User | None = Depends(optional_user)):
    e = await _public_event(db, slug)
    service.require_live_or_staff(e, user)
    cfg = service.voting_config_out(e)
    open_, _ = service.voting_open(e)
    projects = await service.eligible_projects(db, e.id) if open_ else []
    key = None
    mine: dict = {}
    if open_:
        try:
            key = service.voter_key_for(e, user, email or None, voter_id or None)
            mine = await service.voter_allocations(db, e.id, key)
        except Exception:
            key = None  # no identity yet: show the box, allocations on first write
    priced = {"spent": 0, "remaining": quadratic.VOTE_CAP}
    if mine:
        try:
            priced = quadratic.check_budget(mine)
        except ValueError:
            pass
    return {"event": {"id": e.id, "slug": e.slug, "name": e.name, **cfg},
            "open": open_, "budget": quadratic.VOTE_CAP,
            "projects": _box_projects(projects, key),
            "my_votes": mine, "spent": priced["spent"],
            "remaining": priced["remaining"]}


@router.post("/public/events/{slug}/ballot")
async def cast_ballot(slug: str, body: BallotIn, request: Request,
                      db: AsyncSession = Depends(get_db),
                      user: User | None = Depends(optional_user)):
    e = await _public_event(db, slug)
    service.require_live_or_staff(e, user)
    open_, reason = service.voting_open(e)
    if not open_:
        err(403, "forbidden", reason or "voting is not open")
    key = service.voter_key_for(e, user, body.email, body.voter_id)
    await _limited(request, user, "vote", "vote.rate_limited", e.id)
    p = await db.get(Project, body.project_id)
    if (not p or p.event_id != e.id
            or (p.status.value if hasattr(p.status, "value") else str(p.status)) != "SUBMITTED"
            or not p.is_visible):
        err(404, "not_found", "Project is not open for voting")
    if user is not None:
        mine_team = await service.voter_team_id(db, e.id, user.id)
        if mine_team is not None and mine_team == p.team_id:
            err(403, "forbidden", "you cannot vote for your own team's project")
    priced = await service.price_allocation(db, e.id, key, p.id, body.votes)
    res = await db.execute(select(Ballot).where(
        Ballot.event_id == e.id, Ballot.voter_key == key, Ballot.project_id == p.id))
    row = res.scalar_one_or_none()
    ua = request.headers.get("user-agent") if request else None
    fp = service.fingerprint(_ip(request), ua, e.id)
    if body.votes == 0:
        if row:
            await db.delete(row)
    elif row:
        row.votes = body.votes
        row.fp_hash = fp
        row.updated_at = utcnow()
    else:
        db.add(Ballot(event_id=e.id, project_id=p.id, voter_key=key,
                      votes=body.votes, fp_hash=fp))
    await db.commit()
    await record(user, "vote.cast", target_type="project", target_id=p.id,
                 event_id=e.id,
                 detail={"votes": body.votes, "spent": priced["spent"],
                         "remaining": priced["remaining"],
                         "mode": (e.voting_mode or "auth")},
                 request=request)
    return {"ok": True, "project_id": p.id, "votes": body.votes,
            "spent": priced["spent"], "remaining": priced["remaining"]}


async def _rank_event(db: AsyncSession, e: Event) -> tuple[list, dict]:
    """Live tally shared by public results (post-close) and the organizer
    standings preview (anytime). Ballots on currently-ineligible projects
    don't count — same rule both places."""
    eligible = await service.eligible_projects(db, e.id)
    ok_ids = {p.id for p in eligible}
    res = await db.execute(select(Ballot).where(Ballot.event_id == e.id))
    rows = [{"project_id": b.project_id, "votes": b.votes}
            for b in res.scalars().all() if b.project_id in ok_ids]
    by_id = {p.id: p for p in eligible}
    ranking = []
    for r in quadratic.tally(rows):
        p = by_id[r["project_id"]]
        ranking.append({"project_id": p.id, "title": p.title,
                        "votes": r["votes"], "influence": r["influence"],
                        "rank": r["rank"]})
    res = await db.execute(select(func.count(func.distinct(Ballot.voter_key))).where(
        Ballot.event_id == e.id))
    turnout = {"voters": res.scalar() or 0, "ballots": len(rows)}
    return ranking, turnout


@router.get("/events/{event_id}/voting/standings")
async def voting_standings(event_id: str, db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Live standings for organizers while voting runs. The public results
    endpoint stays gated until close — this one never leaks publicly."""
    e = await managed_event(db, user, event_id)
    ranking, turnout = await _rank_event(db, e)
    close = service._aware(e.voting_close)
    return {"ranking": ranking, "turnout": turnout,
            "closed": close is not None and utcnow() >= close}


@router.get("/public/events/{slug}/votes/results")
async def vote_results(slug: str, db: AsyncSession = Depends(get_db),
                       user: User | None = Depends(optional_user)):
    e = await _public_event(db, slug)
    service.require_live_or_staff(e, user)
    if not e.voting_enabled:
        err(404, "not_found", "Event not found")
    close = service._aware(e.voting_close)
    if close is None or utcnow() < close:
        err(403, "forbidden",
            "results stay hidden until the voting deadline passes")
    if not service.is_published(e) and not service.is_staff(user):
        err(404, "not_found", "Event not found")
    ranking, turnout = await _rank_event(db, e)
    return {"event": {"id": e.id, "slug": e.slug, "name": e.name},
            "ranking": ranking,
            "turnout": turnout}


# ---- comments ----

async def _can_read_comments(db: AsyncSession, e: Event, p: Project,
                             user: User | None) -> bool:
    if service.is_staff(user):
        return True
    if (e.comments_visibility or "public").lower() != "team":
        return True
    if user is None:
        return False
    team = await service.voter_team_id(db, e.id, user.id)
    return team is not None and team == p.team_id


@router.get("/public/projects/{project_id}/comments")
async def list_comments(project_id: str, db: AsyncSession = Depends(get_db),
                        user: User | None = Depends(optional_user)):
    from app.models import Team, User as U
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    e = await db.get(Event, p.event_id)
    if not e:
        err(404, "not_found", "Project not found")
    service.require_live_or_staff(e, user)
    if not await _can_read_comments(db, e, p, user):
        err(403, "forbidden",
            "comments on this project are visible to its team and organizers only")
    stmt = select(Comment, U.display_name, U.avatar_url).join(
        U, U.id == Comment.author_user_id).where(
        Comment.project_id == p.id)
    if not service.is_staff(user):
        stmt = stmt.where(Comment.is_hidden == False)  # noqa
    rows = (await db.execute(stmt.order_by(Comment.created_at))).all()
    return {"comments": [{
        "id": c.id, "author": name, "author_avatar": avatar, "body": c.body,
        "is_hidden": c.is_hidden,
        "created_at": c.created_at.isoformat() if c.created_at else None}
        for c, name, avatar in rows]}


@router.post("/public/projects/{project_id}/comments")
async def post_comment(project_id: str, body: CommentIn, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User | None = Depends(optional_user)):
    if user is None:
        err(401, "unauthenticated", "log in to comment")
    text = body.body.strip()
    if not text:
        err(422, "validation_error", "comment cannot be empty")
    await _limited(request, user, "comment", "comment.rate_limited", "")
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    e = await db.get(Event, p.event_id)
    if not e:
        err(404, "not_found", "Project not found")
    service.require_live_or_staff(e, user)
    import uuid as _uuid
    c = Comment(id=f"cmt_{_uuid.uuid4().hex[:8]}", event_id=p.event_id,
                project_id=p.id, author_user_id=user.id, body=text[:2000])
    db.add(c)
    await db.commit()
    await db.refresh(c)
    await record(user, "comment.posted", target_type="project", target_id=p.id,
                 event_id=p.event_id, detail={}, request=request)
    return {"comment": {"id": c.id, "body": c.body,
                        "created_at": c.created_at.isoformat() if c.created_at else None}}


@router.patch("/comments/{comment_id}")
async def moderate_comment(comment_id: str, body: dict,
                           request: Request,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    c = await db.get(Comment, comment_id)
    if not c:
        err(404, "not_found", "Comment not found")
    await require_manageable(db, user, c.event_id)
    c.is_hidden = bool(body.get("is_hidden", True))
    await db.commit()
    await record(user, "comment.hidden" if c.is_hidden else "comment.shown",
                 target_type="comment", target_id=c.id, event_id=c.event_id,
                 request=request)
    return {"ok": True, "is_hidden": c.is_hidden}
