"""Event security: explicit flags, blocks, and the organizer audit view.

Before this module, abuse signals were implicit — in-memory rate buckets,
on-the-fly fingerprint math, scattered audit rows. Now every detection
writes a `security_flags` row (one per event/kind/subject; repeats reopen),
and organizers answer with `security_blocks` (user id or IP) that the
voting write paths enforce. Reads and writes are ORGANIZER/ADMIN through
the existing event-scoping guards; nothing here invents new auth.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog, SecurityBlock, SecurityFlag, User
from app.modules.auth.dependencies import require_roles
from app.modules.events.access import managed_event
from app.shared.audit import record
from app.shared.clock import utcnow
from app.shared.errors import err

router = APIRouter(tags=["security"])

FLAG_KINDS = ("rate_limit", "own_team_vote", "shared_device", "comment_flood")
BLOCK_TARGETS = ("user", "ip", "voter")


async def flag(db: AsyncSession, event_id: str, kind: str,
               subject_type: str, subject: str, detail: dict | None = None) -> None:
    """Record one abuse signal. Never raises — detection must not break writes."""
    try:
        stmt = pg_insert(SecurityFlag).values(
            id=f"flg_{uuid.uuid4().hex[:8]}", event_id=event_id, kind=kind,
            subject_type=subject_type, subject=subject, detail=detail or {},
            status="open")
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id", "kind", "subject"],
            set_={"detail": stmt.excluded.detail, "updated_at": utcnow(),
                  "status": "open"})
        await db.execute(stmt)
        await db.commit()
    except Exception:
        await db.rollback()


async def blocked(db: AsyncSession, event_id: str, *,
                  user_id: str | None = None,
                  voter_key: str | None = None,
                  ip: str | None = None) -> SecurityBlock | None:
    """Active block matching this writer, if any. User blocks match the
    account id and its `user:<id>` voter key; voter blocks match a raw voter
    key (covers email-mode ballots, which have no account); IP blocks match
    the address."""
    ors = []
    if user_id:
        ors.append((SecurityBlock.target_type == "user") & (SecurityBlock.target == user_id))
    if voter_key:
        ors.append(((SecurityBlock.target_type == "user") & (SecurityBlock.target == voter_key)) |
                   ((SecurityBlock.target_type == "voter") & (SecurityBlock.target == voter_key)))
    if ip:
        ors.append((SecurityBlock.target_type == "ip") & (SecurityBlock.target == ip))
    if not ors:
        return None
    from sqlalchemy import or_
    res = await db.execute(select(SecurityBlock).where(
        SecurityBlock.event_id == event_id,
        SecurityBlock.revoked_at.is_(None), or_(*ors)).limit(1))
    return res.scalar_one_or_none()


def _flag_out(f: SecurityFlag) -> dict:
    return {"id": f.id, "kind": f.kind, "subject_type": f.subject_type,
            "subject": f.subject, "detail": f.detail or {},
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None}


def _block_out(b: SecurityBlock) -> dict:
    return {"id": b.id, "target_type": b.target_type, "target": b.target,
            "reason": b.reason,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "revoked_at": b.revoked_at.isoformat() if b.revoked_at else None}


@router.get("/events/{event_id}/security/flags")
async def list_flags(event_id: str, status: str = Query("", max_length=20),
                     limit: int = Query(100, ge=1, le=500),
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Stored abuse signals for one event, newest first."""
    e = await managed_event(db, user, event_id)
    where = [SecurityFlag.event_id == e.id]
    if status.strip():
        where.append(SecurityFlag.status == status.strip())
    rows = (await db.execute(select(SecurityFlag).where(*where).order_by(
        SecurityFlag.updated_at.desc(), SecurityFlag.id.desc()).limit(limit))).scalars().all()
    return {"flags": [_flag_out(f) for f in rows]}


@router.get("/events/{event_id}/security/flags/{flag_id}/subjects")
async def flag_subjects(event_id: str, flag_id: str,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Actionable writers behind a flag. Fingerprint flags resolve to the
    voter keys sharing the hash (with ballot counts); direct flags return
    their own subject. Everything returned is blockable as-is."""
    from app.models import Ballot
    e = await managed_event(db, user, event_id)
    f = await db.get(SecurityFlag, flag_id)
    if not f or f.event_id != e.id:
        err(404, "not_found", "Flag not found")
    if f.subject_type == "fingerprint":
        res = await db.execute(select(
            Ballot.voter_key, func.count(Ballot.id)).where(
            Ballot.event_id == e.id, Ballot.fp_hash == f.subject).group_by(
            Ballot.voter_key).order_by(func.count(Ballot.id).desc()))
        return {"subjects": [
            {"type": "voter", "target": vk, "ballots": n} for vk, n in res.all()]}
    return {"subjects": [{"type": f.subject_type, "target": f.subject,
                          "ballots": None}]}


@router.post("/events/{event_id}/security/flags/{flag_id}/dismiss")
async def dismiss_flag(event_id: str, flag_id: str, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    f = await db.get(SecurityFlag, flag_id)
    if not f or f.event_id != e.id:
        err(404, "not_found", "Flag not found")
    f.status = "dismissed"
    await db.commit()
    await record(user, "security.flag_dismissed", target_type="flag",
                 target_id=flag_id, event_id=e.id,
                 detail={"kind": f.kind}, request=request)
    return {"ok": True}


@router.get("/events/{event_id}/security/blocks")
async def list_blocks(event_id: str, include_revoked: bool = Query(False),
                      db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    where = [SecurityBlock.event_id == e.id]
    if not include_revoked:
        where.append(SecurityBlock.revoked_at.is_(None))
    rows = (await db.execute(select(SecurityBlock).where(*where).order_by(
        SecurityBlock.created_at.desc()))).scalars().all()
    return {"blocks": [_block_out(b) for b in rows]}


@router.post("/events/{event_id}/security/blocks")
async def create_block(event_id: str, body: dict, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Block a user (id or email), a raw voter key, or an IP from
    voting/commenting on this event. Email targets resolve to the account id
    at write time so later login-state changes cannot dodge the block."""
    e = await managed_event(db, user, event_id)
    ttype = (body.get("target_type") or "").strip().lower()
    target = (body.get("target") or "").strip()
    reason = (body.get("reason") or "").strip() or None
    if ttype not in BLOCK_TARGETS:
        err(422, "validation_error", "target_type must be user, voter, or ip")
    if not target or len(target) > 320:
        err(422, "validation_error", "target is required")
    if ttype == "user" and "@" in target:
        res = await db.execute(select(User).where(
            User.email_norm == target.lower()))
        u = res.scalar_one_or_none()
        if not u:
            err(404, "not_found", "No account with that email")
        target = u.id
    b = SecurityBlock(id=f"blk_{uuid.uuid4().hex[:8]}", event_id=e.id,
                      target_type=ttype, target=target, reason=reason,
                      created_by=user.id)
    db.add(b)
    await db.commit()
    await record(user, "security.block_created", target_type="block",
                 target_id=b.id, event_id=e.id,
                 detail={"target_type": ttype, "target": target,
                         "reason": reason}, request=request)
    # A fresh block answers any open flags on the same subject.
    res = await db.execute(select(SecurityFlag).where(
        SecurityFlag.event_id == e.id, SecurityFlag.status == "open",
        SecurityFlag.subject.in_([target, f"user:{target}"])))
    for f in res.scalars().all():
        f.status = "blocked"
    await db.commit()
    return {"block": _block_out(b)}


@router.delete("/events/{event_id}/security/blocks/{block_id}")
async def revoke_block(event_id: str, block_id: str, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    b = await db.get(SecurityBlock, block_id)
    if not b or b.event_id != e.id:
        err(404, "not_found", "Block not found")
    b.revoked_at = utcnow()
    await db.commit()
    await record(user, "security.block_revoked", target_type="block",
                 target_id=block_id, event_id=e.id, request=request)
    return {"ok": True}


@router.get("/events/{event_id}/security/overview")
async def overview(event_id: str, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """One-screen summary: open flag counts by kind, active blocks, and
    recent refusal-audit volume. The panel header renders from this."""
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(SecurityFlag.kind, func.count()).where(
        SecurityFlag.event_id == e.id,
        SecurityFlag.status == "open").group_by(SecurityFlag.kind))
    open_flags = {k: n for k, n in res.all()}
    n_blocks = (await db.execute(select(func.count()).select_from(
        SecurityBlock).where(SecurityBlock.event_id == e.id,
                             SecurityBlock.revoked_at.is_(None)))).scalar() or 0
    n_refusals = (await db.execute(select(func.count()).select_from(
        AuditLog).where(
        AuditLog.event_id == e.id,
        AuditLog.action.in_(["vote.rate_limited", "comment.rate_limited",
                             "comment.duplicate"])))).scalar() or 0
    return {"open_flags": open_flags,
            "open_flag_total": sum(open_flags.values()),
            "active_blocks": n_blocks, "refusals": n_refusals}
