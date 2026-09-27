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
    token = request.cookies.get(SESSION_COOKIE)
    # also allow raw Cookie header passthrough variants already parsed by starlette
    if not token:
        # support "session=<raw>" sent via custom header? run.py uses Cookie header normally.
        err(401, "unauthenticated", "Not authenticated")
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
