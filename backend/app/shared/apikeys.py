"""API-key scopes (T4 API-first). Single source of truth for which token
may touch which area.

A key authenticates AS its owning user — role checks and event scoping
apply unchanged — and scopes further restrict by area. Reads need
`<area>:read` (a `:write` grant implies read); anything else needs
`<area>:write`. Cookie sessions (the human UI) are never scope-checked.
"""
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth.dependencies import optional_user
from app.shared.errors import err

AREAS = ("events", "judging", "voting", "transfer", "admin")

SCOPES = tuple(f"{a}:{op}" for a in AREAS for op in ("read", "write"))

# Specific substring wins over the broad event prefix (e.g. an organizer
# voting-settings call lives under /events/{id}/voting but needs the
# voting scope). /health and GET /auth/me are always allowed.
_VOTING_HITS = ("/voting", "/ballot", "/votes", "/comments", "/audit",
                "/standings")
_JUDGING_HITS = ("/judging", "/assignments", "/results", "/bayes",
                 "/rubric", "/judge")
_TRANSFER_HITS = ("/export", "/import", "/transfer")
_EVENTS_HITS = ("/events", "/teams", "/submissions", "/tracks", "/prizes",
                "/form-fields", "/public", "/projects", "/certificate")


def area_for(path: str) -> str | None:
    if path == "/health":
        return None
    if path.startswith("/admin"):
        return "admin"
    if path.startswith("/auth"):
        return "auth"
    for hit in _VOTING_HITS:
        if hit in path:
            return "voting"
    for hit in _JUDGING_HITS:
        if hit in path:
            return "judging"
    for hit in _TRANSFER_HITS:
        if hit in path:
            return "transfer"
    for hit in _EVENTS_HITS:
        if path == hit or path.startswith(hit + "/"):
            return "events"
    return None


def has_scope(scopes: list, area: str, write: bool) -> bool:
    scopes = scopes or []
    if f"{area}:write" in scopes:
        return True
    return not write and f"{area}:read" in scopes


def _bearer(request: Request) -> str | None:
    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        return authz[7:].strip() or None
    return None


async def require_scope(request: Request, db: AsyncSession = Depends(get_db),
                        user=Depends(optional_user)):
    """Router-level guard for key-authenticated calls. Cookie and anonymous
    traffic passes through untouched (each route's own auth decides); a
    presented bearer token must be valid AND scoped for this path+method."""
    raw = _bearer(request)
    if raw is None:
        return
    scopes = getattr(user, "_api_scopes", None) if user else None
    if scopes is None:
        err(401, "unauthenticated", "Invalid or revoked API key")
    path = request.url.path
    if path == "/health":
        return
    if path == "/auth/me" and request.method == "GET":
        return
    area = area_for(path)
    if area is None or area == "auth":
        err(403, "forbidden", "API keys cannot access this endpoint")
    write = request.method != "GET"
    if not has_scope(scopes, area, write):
        err(403, "forbidden",
            f"This API key lacks the '{area}:{'write' if write else 'read'}' scope")
