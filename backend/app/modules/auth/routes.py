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
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "avatar_url": getattr(u, "avatar_url", None),
            "profile": {
                "phone": getattr(u, "profile_phone", None),
                "age": getattr(u, "profile_age", None),
                "degree": getattr(u, "profile_degree", None),
                "year_of_study": getattr(u, "profile_year", None),
                "institution": getattr(u, "profile_institution", None),
                "tshirt_size": getattr(u, "profile_tshirt", None),
                "dietary_restrictions": getattr(u, "profile_dietary", None),
            }}

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

def _ip(request: Request | None) -> str:
    """Right-most X-Forwarded-For from a trusted peer, else the direct peer
    (shared/client_ip) — same rule as voting/routes._ip. Attribution only."""
    from app.shared.client_ip import client_ip
    if request is None:
        return "unknown"
    peer = request.client.host if request.client else None
    return client_ip(request.headers.get("x-forwarded-for"), peer)


async def _limited(request: Request, route: str, action: str) -> None:
    """Auth-surface gate. Runs before any existence check so responses leak
    nothing new, and refusals are audited for the admin trail."""
    from app.modules.voting import ratelimit
    ok, retry = ratelimit.check(_ip(request), route)
    if not ok:
        await record(None, action, detail={"route": route}, request=request)
        err(429, "rate_limited",
            f"too many requests — try again in {retry}s")

@router.post("/register")
async def register(body: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Mass registration is the Sybil front door to auth-mode voting (every
    # account is a fresh user:<id> budget with no team to block), so account
    # creation is throttled per IP. Tunable via REGISTER_PER_HOUR.
    await _limited(request, "register", "auth.register_rate_limited")
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
    # Credential-stuffing backstop (Argon2 already makes each guess
    # expensive). Runs before the lookup so timing leaks nothing.
    await _limited(request, "login", "auth.login_rate_limited")
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
    u = await db.get(User, user.id)
    if "display_name" in body:
        name = (body.get("display_name") or "").strip()
        if not name:
            err(422, "validation_error", "display_name is required")
        if len(name) > 80:
            err(422, "validation_error", "display_name is too long")
        u.display_name = name
    if "avatar_url" in body:
        # Client-resized data: URLs only (offline-safe, no file store).
        # Empty string clears back to initials.
        av = body.get("avatar_url") or None
        if av is not None:
            av = str(av)
            if not av.startswith("data:image/"):
                err(422, "validation_error", "avatar must be an image upload")
            if len(av) > 300_000:
                err(422, "validation_error", "avatar image is too large")
        u.avatar_url = av
    if "profile" in body:
        # Reusable registration details. Every field is optional; empty
        # clears it back to unset. Same bounds as event registration so a
        # value saved here always validates there.
        p = body.get("profile") or {}
        if not isinstance(p, dict):
            err(422, "validation_error", "profile must be an object")
        if "phone" in p:
            ph = (p.get("phone") or "").strip() or None
            if ph is not None:
                import re as _re
                if len(ph) > 40 or not _re.match(r"^\+?[\d\s\-()]{7,18}$", ph):
                    err(422, "validation_error", "Enter a valid phone number")
            u.profile_phone = ph
        if "age" in p:
            raw = p.get("age")
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                u.profile_age = None
            else:
                try:
                    age = int(raw) if not isinstance(raw, bool) else 0
                except (TypeError, ValueError):
                    err(422, "validation_error", "Age must be a whole number")
                if age < 1 or age > 150:
                    err(422, "validation_error", "Age must be between 1 and 150")
                u.profile_age = age
        for key, col, cap in (("degree", "profile_degree", 100),
                              ("year_of_study", "profile_year", 50),
                              ("institution", "profile_institution", 300),
                              ("tshirt_size", "profile_tshirt", 10),
                              ("dietary_restrictions", "profile_dietary", 500)):
            if key in p:
                v = p.get(key)
                v = (str(v).strip() or None) if v is not None else None
                if v is not None and len(v) > cap:
                    err(422, "validation_error", f"profile {key} is too long")
                setattr(u, col, v)
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
