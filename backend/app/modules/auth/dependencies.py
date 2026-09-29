from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from app.database import get_db
from app.models import Session as Sess, User
from app.shared.security import sha256_hex, utcnow
from app.shared.errors import err

SESSION_COOKIE = "session"
SESSION_DAYS = 14

async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    # API keys (T4) take precedence: an explicit `Authorization: Bearer`
    # header authenticates as the owning user, with scopes attached for
    # require_scope. Invalid keys fail closed even when a session cookie is
    # also present — mixed credentials must never silently downgrade.
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        raw = authz[7:].strip()
        if raw:
            return await _user_for_api_key(db, raw)
        err(401, "unauthenticated", "Not authenticated")
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        return await _user_for_session(db, token)
    err(401, "unauthenticated", "Not authenticated")


async def _user_for_session(db: AsyncSession, token: str) -> User:
    # also allow raw Cookie header passthrough variants already parsed by starlette
    th = sha256_hex(token)
    res = await db.execute(select(Sess, User).join(User, User.id == Sess.user_id).where(Sess.token_hash == th))
    row = res.first()
    if not row:
        err(401, "unauthenticated", "Invalid session")
    sess, user = row
    now = utcnow()
    # ensure tz-aware compare
    exp = sess.expires_at
    if exp.tzinfo is None:
        from datetime import timezone
        exp = exp.replace(tzinfo=timezone.utc)
    if sess.revoked_at is not None or exp <= now:
        err(401, "unauthenticated", "Session expired")
    user._api_scopes = None
    return user


async def _user_for_api_key(db: AsyncSession, raw: str) -> User:
    from app.models import ApiKey
    th = sha256_hex(raw)
    res = await db.execute(select(ApiKey, User).join(User, User.id == ApiKey.user_id).where(
        ApiKey.token_hash == th))
    row = res.first()
    if not row:
        err(401, "unauthenticated", "Invalid API key")
    key, user = row
    now = utcnow()
    exp = key.expires_at
    if exp is not None:
        if exp.tzinfo is None:
            from datetime import timezone
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            err(401, "unauthenticated", "API key expired")
    if key.revoked_at is not None:
        err(401, "unauthenticated", "API key revoked")
    key.last_used_at = now
    await db.commit()
    user._api_scopes = list(key.scopes or [])
    return user

async def optional_user(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await current_user(request, db)
    except Exception:
        return None

def require_roles(*roles: str):
    async def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            err(403, "forbidden", "Insufficient role")
        return user
    return dep
