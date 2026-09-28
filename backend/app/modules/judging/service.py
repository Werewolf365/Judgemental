"""Shared judging helpers: stage derivation, weight resolution, rubric locking.

Judging stage is DERIVED (PROMPT.md §6.3 forbids redundant event states), from
the event's judging window plus what exists in the database:

  NOT_STARTED   no window set and nothing judged yet... actually: window not
                opened (judging_open set and now < judging_open) and no
                finalized evaluation exists
  OPEN          inside the window, or no window configured at all
  CLOSED        past judging_close with no SUCCEEDED model run yet
  RESULTS_READY a SUCCEEDED model run exists for the event

A missing window means "judge whenever": scoring is allowed on SUBMITTED
projects and the organizer sets an explicit deadline before calculating.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Evaluation, EvaluationStatus, Event, ModelRun, ModelRunStatus
from app.shared.clock import utcnow
from app.shared.errors import err


def _aware(x):
    if x is None:
        return None
    return x if x.tzinfo else x.replace(tzinfo=__import__("datetime").timezone.utc)


async def has_any_evaluation(db: AsyncSession, event_id: str) -> bool:
    res = await db.execute(select(Evaluation.id).where(
        Evaluation.event_id == event_id).limit(1))
    return res.scalar_one_or_none() is not None


async def has_finalized_evaluation(db: AsyncSession, event_id: str) -> bool:
    res = await db.execute(select(Evaluation.id).where(
        Evaluation.event_id == event_id,
        Evaluation.status == EvaluationStatus.SUBMITTED).limit(1))
    return res.scalar_one_or_none() is not None


async def latest_succeeded_run(db: AsyncSession, event_id: str):
    res = await db.execute(select(ModelRun).where(
        ModelRun.event_id == event_id,
        ModelRun.status == ModelRunStatus.SUCCEEDED
    ).order_by(ModelRun.finished_at.desc()))
    return res.scalars().first()


async def judging_stage(db: AsyncSession, event: Event) -> str:
    """One of NOT_STARTED | OPEN | CLOSED | RESULTS_READY.

    RESULTS_READY is CLOSED plus a succeeded run — checked second, so
    reopening the window genuinely returns the event to OPEN (recalc after
    re-close creates a new run version; nothing is ever mutated).
    """
    now = utcnow()
    close = _aware(event.judging_close)
    if close is not None and now > close:
        if await latest_succeeded_run(db, event.id):
            return "RESULTS_READY"
        return "CLOSED"
    opened = _aware(event.judging_open)
    if opened is not None and now < opened:
        # The window has not opened, but finalized work counts as started:
        # an organizer who set the window late must not strand real scores.
        if await has_finalized_evaluation(db, event.id):
            return "OPEN"
        return "NOT_STARTED"
    return "OPEN"


async def rubric_locked(db: AsyncSession, event: Event) -> bool:
    """True once judging has started: the window opened, or any judge has
    saved work. Locked rubrics reject every write (409) so submitted
    evaluations can never be reinterpreted under edited weights."""
    opened = _aware(event.judging_open)
    if opened is not None and utcnow() >= opened:
        return True
    return await has_any_evaluation(db, event.id)


def resolve_weights(criteria: list) -> dict:
    """Normalized {criterion_id: weight} over ACTIVE criteria.

    All-NULL → equal weighting. All explicit → normalized to sum 1.
    Mixed (some NULL, some set) → 422: the rubric is mid-edit and no score
    can be computed honestly under it. Empty → 422.
    """
    active = [c for c in criteria if c.is_active]
    if not active:
        err(422, "validation_error", "This event has no active rubric criteria")
    nully = [c for c in active if c.weight is None]
    if nully and len(nully) != len(active):
        names = ", ".join(f"“{c.name}”" for c in nully[:3])
        err(422, "validation_error",
            f"Rubric weights are incomplete: {names} still need{'s' if len(nully) == 1 else ''} a weight, "
            "or clear every weight to score with equal weighting")
    if not nully:
        total = sum(c.weight for c in active)
        if total <= 0:
            err(422, "validation_error", "Rubric weights must sum to more than zero")
        return {c.id: c.weight / total for c in active}
    return {c.id: 1.0 / len(active) for c in active}


def criterion_out(c) -> dict:
    return {"id": c.id, "event_id": c.event_id, "name": c.name,
            "description": c.description, "weight": c.weight,
            "display_order": c.display_order, "is_active": c.is_active}
