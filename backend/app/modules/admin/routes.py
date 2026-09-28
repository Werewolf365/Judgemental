"""Platform administration. Every route here requires the ADMIN role.

Two jobs:
  1. Role management. An ADMIN is the only account that may change roles, which
     is what makes "organizers are scoped to their own events" a rule rather
     than a convention — the ORGANIZER role on its own grants no access to
     anything.
  2. The audit log reader.

An admin can move any account between any of the four roles. Self-registration
always produces PARTICIPANT (see auth/routes.py), so the console is the one
place a competitor becomes an organizer, a judge, or an admin — and
demotion works the same way, so a mis-promotion is always recoverable.

The two guards that remain are the ones that would break the platform rather
than a single account: you cannot change your own role (no admin lockout by
accident), and the last remaining ADMIN cannot be stepped down.
"""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.models import AuditLog, User
from app.modules.auth.dependencies import require_roles
from app.shared.audit import record
from app.shared.errors import err

router = APIRouter(prefix="/admin", tags=["admin"])

# Every role an ADMIN may hand out, in ascending order of privilege. This is
# the single source of truth: the schema rejects anything outside it, so an
# unknown or misspelled role can never reach the users table.
ASSIGNABLE_ROLES = ("PARTICIPANT", "JUDGE", "ORGANIZER", "ADMIN")


def _role_of(u: User) -> str:
    return u.role.value if hasattr(u.role, "value") else str(u.role)


async def count_admins(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count()).select_from(User).where(User.role == "ADMIN"))).scalar() or 0


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": _role_of(u),
            "created_at": u.created_at.isoformat() if u.created_at else None}


@router.get("/users")
async def list_users(q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=200),
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ADMIN"))):
    """Directory lookup for the role console. Admin-only: it exposes every
    account's email, so it must not be reachable by ORGANIZER."""
    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(User.email).like(like) | func.lower(User.display_name).like(like))
    res = await db.execute(stmt)
    return {"users": [user_out(u) for u in res.scalars().all()]}


class RoleChangeIn(BaseModel):
    """Set an account's role. ADMIN callers only."""
    email: Optional[str] = Field(default="", max_length=320)
    user_id: Optional[str] = Field(default=None, max_length=64)
    role: str = Field(max_length=32)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return (v or "").strip().lower()

    @field_validator("user_id")
    @classmethod
    def _user_id(cls, v):
        return (v or "").strip() or None

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        v = (v or "").strip().upper()
        if v not in ASSIGNABLE_ROLES:
            raise ValueError(f"role must be one of {', '.join(ASSIGNABLE_ROLES)}")
        return v


@router.post("/users/role")
async def set_role(body: RoleChangeIn, request: Request, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_roles("ADMIN"))):
    """Move an account to any of the four roles. ADMIN only.

    Guards (both are platform-level, not per-account):
      - the target must exist;
      - the requested role must be one of ASSIGNABLE_ROLES (the schema rejects
        anything else, so an unknown value never reaches the users table);
      - you cannot change your own role (no accidental admin lockout);
      - the last remaining ADMIN cannot be stepped down, which would leave the
        platform with nobody able to reverse it.
    """
    target_email, target_id, role = body.email, body.user_id, body.role
    if not target_email and not target_id:
        err(422, "validation_error", "Provide the account's email or user_id")
    stmt = select(User).where(User.email_norm == target_email) if target_email else select(User).where(User.id == target_id)
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        err(404, "not_found", "No such account")
    if target.id == user.id:
        await record(user, "user.role_change_refused", target_type="user", target_id=target.id,
                     detail={"email": target.email, "reason": "self-modification refused"},
                     request=request)
        err(409, "invalid_state_transition", "You cannot change your own role")
    before = _role_of(target)
    if before == role:
        return {"user": user_out(target), "changed": False}
    if before == "ADMIN" and role != "ADMIN" and await count_admins(db) <= 1:
        # Recorded even though it raises: a refused attempt to demote the last
        # admin is exactly the kind of thing an audit trail exists to surface.
        await record(user, "user.role_change_refused", target_type="user", target_id=target.id,
                     detail={"email": target.email, "from": before, "to": role,
                             "reason": "last remaining admin"},
                     request=request)
        err(409, "invalid_state_transition", "Cannot step down the last admin")
    target.role = role
    await db.commit()
    await db.refresh(target)
    await record(user, "user.role_changed", target_type="user", target_id=target.id,
                 detail={"email": target.email, "from": before, "to": role}, request=request)
    return {"user": user_out(target), "changed": True}


@router.get("/audit")
async def read_audit(action: str = Query("", max_length=80), actor_id: str = Query("", max_length=64),
                     event_id: str = Query("", max_length=64), q: str = Query("", max_length=200),
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ADMIN"))):
    """Newest-first audit trail. ADMIN only."""
    where = []
    if action.strip():
        where.append(AuditLog.action == action.strip())
    if actor_id.strip():
        where.append(AuditLog.actor_id == actor_id.strip())
    if event_id.strip():
        where.append(AuditLog.event_id == event_id.strip())
    if q.strip():
        like = f"%{q.strip().lower()}%"
        where.append(func.lower(AuditLog.actor_email).like(like) | AuditLog.action.ilike(like)
                     | func.lower(AuditLog.target_id).like(like))
    stmt = select(AuditLog).where(*where).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    distinct = (await db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))).scalars().all()
    return {
        "entries": [{
            "id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
            "actor_id": r.actor_id, "actor_email": r.actor_email, "action": r.action,
            "target_type": r.target_type, "target_id": r.target_id, "event_id": r.event_id,
            "detail": r.detail or {}, "ip": r.ip,
        } for r in rows],
        "total": total, "limit": limit, "offset": offset,
        "actions": list(distinct),
    }
