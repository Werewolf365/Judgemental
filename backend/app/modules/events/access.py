"""Event-scoped organizer authorization.

Every organizer action is checked here, never in the route bodies. An
organizer may manage an event only when they created it (`events.created_by`)
or appear in `event_organizers`. `ADMIN` keeps platform-wide access so support
and recovery paths still work; everything else is denied.

Denials deliberately avoid confirming that a draft exists: a user who cannot
manage an unpublished event gets 404, the same answer as a bogus id.
"""
from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Event, EventOrganizer, User
from app.shared.errors import err


def role_of(user) -> str:
    if not user:
        return ""
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def is_admin(user) -> bool:
    return role_of(user) == "ADMIN"


def is_staff(user) -> bool:
    return role_of(user) in ("ORGANIZER", "ADMIN")


def is_published(e: Event) -> bool:
    return (e.status.value if hasattr(e.status, "value") else str(e.status)) == "PUBLISHED"


async def manages_event(db: AsyncSession, user, e: Event | None) -> bool:
    """True when `user` may read drafts and mutate `e`."""
    if not user or e is None or not is_staff(user):
        return False
    if is_admin(user):
        return True
    if e.created_by and e.created_by == user.id:
        return True
    res = await db.execute(
        select(EventOrganizer.user_id).where(
            EventOrganizer.event_id == e.id, EventOrganizer.user_id == user.id))
    return res.scalar_one_or_none() is not None


async def manageable_event_ids(db: AsyncSession, user) -> list[str] | None:
    """Event ids `user` may manage. `None` means "all of them" (ADMIN)."""
    if is_admin(user):
        return None
    if not is_staff(user):
        return []
    assigned = select(EventOrganizer.event_id).where(EventOrganizer.user_id == user.id)
    res = await db.execute(
        select(Event.id).where(or_(Event.created_by == user.id, Event.id.in_(assigned))))
    return [r[0] for r in res.all()]


async def managed_event(db: AsyncSession, user, event_id: str, allow_slug: bool = True) -> Event:
    """Load an event the user is allowed to manage, or raise 404/403."""
    e = await db.get(Event, event_id)
    if not e and allow_slug:
        res = await db.execute(select(Event).where(Event.slug == event_id))
        e = res.scalar_one_or_none()
    if not e:
        err(404, "not_found", "Event not found")
    if not await manages_event(db, user, e):
        if not is_published(e):
            err(404, "not_found", "Event not found")
        err(403, "forbidden", "You are not an organizer for this event")
    return e


async def require_manageable(db: AsyncSession, user, event_id: str) -> Event:
    """`managed_event` for ids that are always internal (never a slug)."""
    return await managed_event(db, user, event_id, allow_slug=False)


async def visible_event_or_404(db: AsyncSession, user, e: Event | None) -> Event:
    """Read access for endpoints that are public once the event is published.

    Drafts stay invisible to everyone except their organizers.
    """
    if not e:
        err(404, "not_found", "Event not found")
    if is_published(e):
        return e
    if await manages_event(db, user, e):
        return e
    err(404, "not_found", "Event not found")


def owned_only(stmt, ids: list[str] | None):
    """Narrow an event query to `ids`; `None` (ADMIN) means no narrowing."""
    if ids is None:
        return stmt
    return stmt.where(Event.id.in_(ids) if ids else false())
