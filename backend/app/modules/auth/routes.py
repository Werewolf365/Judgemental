from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from app.database import get_db
from app.models import User, Session as Sess, Role
from app.modules.auth.schemas import RegisterIn, LoginIn, UserOut
from app.modules.auth.dependencies import current_user, SESSION_COOKIE, SESSION_DAYS
from app.shared.security import hash_password, verify_password, new_session_token, sha256_hex, utcnow
from app.shared.audit import record
from app.shared.errors import err

router = APIRouter(prefix="/auth", tags=["auth"])

def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role.value if hasattr(u.role, "value") else str(u.role)}

async def _create_session(db: AsyncSession, user: User, ua: str | None) -> str:
    raw = new_session_token()
    s = Sess(user_id=user.id, token_hash=sha256_hex(raw),
             expires_at=utcnow() + timedelta(days=SESSION_DAYS), user_agent=ua)
    db.add(s)
    await db.commit()
    return raw

def _cookie(resp: Response, raw: str):
    import os
    # Secure is opt-in via env so plain-HTTP local dev keeps working unchanged.
    secure = os.getenv("COOKIE_SECURE", "0") == "1"
    resp.set_cookie(SESSION_COOKIE, raw, httponly=True, samesite="lax",
                    secure=secure, path="/", max_age=SESSION_DAYS * 86400)

@router.post("/register")
async def register(body: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    email = body.email.strip()
    norm = email.lower()
    ex = await db.execute(select(User).where(User.email_norm == norm))
    if ex.scalar_one_or_none():
        err(409, "already_joined", "Email already registered")
    role = body.role.upper() if body.role else "PARTICIPANT"
    # Self-registration is always PARTICIPANT; elevated roles come from seed/promotion.
    if role != "PARTICIPANT":
        role = "PARTICIPANT"
    u = User(email=email, email_norm=norm, password_hash=hash_password(body.password),
             display_name=body.display_name or email.split("@")[0], role=Role(role))
    db.add(u)
    await db.commit()
    await db.refresh(u)
    raw = await _create_session(db, u, request.headers.get("user-agent"))
    _cookie(response, raw)
    await record(u, "auth.registered", target_type="user", target_id=u.id, request=request)
    return {"user": user_out(u)}

@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    norm = body.email.strip().lower()
    ex = await db.execute(select(User).where(User.email_norm == norm))
    u = ex.scalar_one_or_none()
    if not u or not verify_password(u.password_hash, body.password):
        # Log the attempt either way: a burst of failures against one address is
        # the signal an admin needs. No password is ever recorded.
        await record(u, "auth.login_failed", target_type="user", target_id=getattr(u, "id", None),
                     detail={"email": norm}, request=request)
        err(401, "unauthenticated", "Invalid credentials")
    raw = await _create_session(db, u, request.headers.get("user-agent"))
    _cookie(response, raw)
    await record(u, "auth.login", target_type="user", target_id=u.id, request=request)
    return {"user": user_out(u)}

@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        res = await db.execute(select(Sess).where(Sess.token_hash == sha256_hex(token)))
        s = res.scalar_one_or_none()
        if s:
            s.revoked_at = utcnow()
            await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    if s:
        await record(await db.get(User, s.user_id), "auth.logout", request=request)
    return {"ok": True}

@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"user": user_out(user)}

@router.patch("/me")
async def update_me(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    name = (body.get("display_name") or "").strip()
    if not name:
        err(422, "validation_error", "display_name is required")
    if len(name) > 80:
        err(422, "validation_error", "display_name is too long")
    u = await db.get(User, user.id)
    u.display_name = name
    await db.commit()
    await db.refresh(u)
    return {"user": user_out(u)}

@router.post("/password")
async def change_password(request: Request, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    cur = body.get("current_password") or ""
    new = body.get("new_password") or ""
    if len(new) < 8:
        err(422, "validation_error", "New password must be at least 8 characters")
    if len(new) > 128:
        err(422, "validation_error", "New password is too long")
    u = await db.get(User, user.id)
    if not verify_password(u.password_hash, cur):
        await record(u, "auth.password_change_failed", target_type="user", target_id=u.id, request=request)
        err(401, "unauthenticated", "Current password is incorrect")
    u.password_hash = hash_password(new)
    # Revoke every other session; the caller stays logged in on this one.
    raw = request.cookies.get(SESSION_COOKIE)
    res = await db.execute(select(Sess).where(Sess.user_id == u.id, Sess.revoked_at.is_(None)))
    revoked = 0
    for s in res.scalars().all():
        if not raw or s.token_hash != sha256_hex(raw):
            s.revoked_at = utcnow()
            revoked += 1
    await db.commit()
    await record(u, "auth.password_changed", target_type="user", target_id=u.id,
                 detail={"other_sessions_revoked": revoked}, request=request)
    return {"ok": True}
