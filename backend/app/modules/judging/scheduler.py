"""Automatic batch-assignment sweep (prompt_T2 follow-up).

Why this exists: previously the only way to cover submissions was the
organizer pressing "Run batch assignment" by hand. This loop does the same
idempotent `assign_all_pending` pass on a fixed cadence, so judging work
flows without babysitting.

Design notes (read before touching):
- No new dependencies: plain asyncio, so the offline image build is
  untouched. No workers, no queues, no threads — same "no scheduler
  service" constraint as the rest of T2, just an in-process loop.
- Fixed cadence, NOT reset by manual runs: the loop sleeps
  AUTO_ASSIGN_EVERY_SECONDS between ticks and nothing else touches that
  timer, so pressing the manual button can never shift, skip, or double
  a scheduled sweep.
- Overlap-safe two ways: an asyncio.Lock makes a slow tick skip the next
  one instead of piling up, and underneath, the per-event
  SELECT … FOR UPDATE plus ON CONFLICT DO NOTHING makes even a manual
  batch racing a sweep converge on the same rows (idempotent by
  construction — a sweep that finds nothing to do changes nothing).
- Single-worker assumption: stock uvicorn runs one worker, so exactly one
  loop runs. If workers are ever added, concurrent sweeps stay correct
  (same idempotency argument) but would duplicate effort; revisit then.
- No audit spam: scheduled sweeps log to stdout only. The manual button
  keeps writing audit rows, so human actions stay distinguishable.

Tuning: AUTO_ASSIGN_EVERY_SECONDS (default 180 = 3 min, testing cadence).
Set it to 1800 for the 30-minute production cadence — no code change.
AUTO_ASSIGN_ENABLED=0 disables the loop entirely (manual button unaffected).
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Project, ProjectStatus
from app.modules.judging import assign as assign_svc

log = logging.getLogger("dogfood.auto_assign")

DEFAULT_EVERY_SECONDS = 180  # 3 min testing cadence; production wants 1800.

_task: asyncio.Task | None = None

# Served read-only through GET /events/{id}/judging (no extra endpoint, no
# frontend polling): what the cadence is and what the last sweep did.
state: dict = {
    "enabled": True,
    "every_seconds": DEFAULT_EVERY_SECONDS,
    "last_run": None,          # ISO UTC timestamp of the last finished sweep
    "last_created": 0,         # assignments created by the last sweep
    "last_events": 0,          # events swept
    "running": False,
}


def _every_seconds() -> int:
    try:
        return max(15, int(os.getenv("AUTO_ASSIGN_EVERY_SECONDS", str(DEFAULT_EVERY_SECONDS))))
    except ValueError:
        return DEFAULT_EVERY_SECONDS


def _enabled() -> bool:
    return os.getenv("AUTO_ASSIGN_ENABLED", "1") != "0"


async def sweep_once() -> dict:
    """One full pass. Never raises: per-event failures roll back just that
    event and are logged; the loop itself must be immortal."""
    created_total, events_seen = 0, 0
    try:
        async with SessionLocal() as db:
            res = await db.execute(
                select(Project.event_id).where(
                    Project.status == ProjectStatus.SUBMITTED).distinct())
            event_ids = [r[0] for r in res.all()]
        for eid in event_ids:
            try:
                async with SessionLocal() as db:
                    out = await assign_svc.assign_all_pending(db, eid)
                    await db.commit()
                n = out.get("assignments_created", 0)
                created_total += n
                events_seen += 1
                if n:
                    log.info("auto-assign: event %s +%d assignment(s)", eid, n)
            except Exception:
                log.exception("auto-assign: event %s failed, rolled back", eid)
    except Exception:
        log.exception("auto-assign: sweep listing failed")
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["last_created"] = created_total
    state["last_events"] = events_seen
    return {"events": events_seen, "assignments_created": created_total}


async def _loop(lock: asyncio.Lock) -> None:
    log.info("auto-assign loop started (every %ds)", state["every_seconds"])
    while True:
        await asyncio.sleep(_every_seconds())
        if not _enabled():
            continue
        if lock.locked():
            log.warning("auto-assign: previous sweep still running, skipping tick")
            continue
        async with lock:
            state["running"] = True
            try:
                await sweep_once()
            finally:
                state["running"] = False


async def start() -> None:
    """Idempotent: calling twice (e.g. reloader) keeps exactly one loop."""
    global _task
    state["enabled"] = _enabled()
    state["every_seconds"] = _every_seconds()
    if _task is not None and not _task.done():
        return
    if not state["enabled"]:
        log.info("auto-assign disabled (AUTO_ASSIGN_ENABLED=0)")
        return
    _task = asyncio.create_task(_loop(asyncio.Lock()))


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
