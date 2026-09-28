"""Audit trail writer.

`record()` opens its own short-lived session so the row is committed
independently of the request's transaction: a denied or rolled-back action is
exactly the thing you want to see in the log, and a failed write must never
take down the request that triggered it.

Call sites pass server-derived values only. Never pass a password, a session
token, or a raw request body into `detail`.
"""
import logging
import uuid
from app.database import SessionLocal
from app.models import AuditLog
from app.shared.clock import utcnow

log = logging.getLogger("dogfood.audit")

MAX_TEXT = 300
# Anything matching these keys is dropped rather than truncated: a truncated
# secret is still a secret.
BANNED_KEYS = ("password", "token", "secret", "cookie", "authorization", "hash", "csrf")


def _clean(value, limit: int = MAX_TEXT):
    if value is None:
        return None
    return str(value)[:limit]


def _clean_detail(detail: dict | None) -> dict:
    if not isinstance(detail, dict):
        return {}
    out = {}
    for k, v in list(detail.items())[:20]:
        if any(b in str(k).lower() for b in BANNED_KEYS):
            continue
        out[str(k)[:60]] = v if isinstance(v, (int, float, bool, type(None))) else _clean(v)
    return out


def _client_ip(request):
    """Best-effort client address.

    Behind the bundled nginx gateway `request.client.host` is the proxy's own
    address, so prefer the left-most X-Forwarded-For entry, which nginx sets to
    the original client. That header is trivially spoofable by anything that
    reaches the API directly, so treat this as attribution, never as
    authentication.
    """
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return _clean(first, 64)
    client = getattr(request, "client", None)
    return _clean(client.host if client else None, 64)


async def record(actor, action: str, *, target_type: str | None = None, target_id=None,
                 event_id=None, detail: dict | None = None, request=None) -> None:
    """Append one audit row. Never raises, never blocks the caller."""
    try:
        async with SessionLocal() as db:
            db.add(AuditLog(
                id=uuid.uuid4().hex,
                created_at=utcnow(),
                actor_id=_clean(getattr(actor, "id", None)),
                actor_email=_clean(getattr(actor, "email", None)),
                action=_clean(action, 80),
                target_type=_clean(target_type, 40),
                target_id=_clean(target_id, 80),
                event_id=_clean(event_id, 80),
                detail=_clean_detail(detail),
                ip=_client_ip(request),
            ))
            await db.commit()
        log.info("action=%s actor=%s target=%s:%s", action, getattr(actor, "email", "anonymous"),
                 target_type, target_id)
    except Exception:
        log.exception("failed to write audit row for action=%s", action)
