"""Balanced judge assignment service (prompt_T2 §4/§6).

Not embedded in routes: routes validate authZ and commit; everything about
*who* gets *what* lives here.

Baseline rule: for every required slot, pick the eligible judge with the
lowest current load (active ASSIGNED + IN_PROGRESS rows), tie-broken by
user_id so concurrent runs choose identically. The in-memory load map is
updated as each slot is filled, so slots chosen in one call never use a
stale snapshot.

Concurrency: callers run inside a transaction; assign_* takes a
SELECT … FOR UPDATE lock on the event row first, serializing assignment
decisions per event. The partial unique index on judge_assignments is the
second line of defence — duplicate pairs are impossible even if two
transactions interleave, and inserts use ON CONFLICT DO NOTHING so a retry
is always safe (idempotent).

Deliberately NOT done: stealing. Rebalance only *fills* under-assigned
projects; an ASSIGNED row is a commitment to that judge and is never moved
to even out loads. Evening out happens through future picks preferring the
idled judge.
"""
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (AssignmentStatus, EvaluationStatus, Event, EventJudge,
                        Evaluation, JudgeAssignment, Project, ProjectStatus, User)
from app.modules.judging import service as _svc
from app.shared.errors import err
import uuid

ACTIVE = (AssignmentStatus.ASSIGNED, AssignmentStatus.IN_PROGRESS)


async def _lock_event(db: AsyncSession, event_id: str) -> Event:
    e = (await db.execute(
        select(Event).where(Event.id == event_id).with_for_update())).scalar_one_or_none()
    if not e:
        err(404, "not_found", "Event not found")
    return e


def _role_of(u) -> str:
    return u.role.value if hasattr(u.role, "value") else str(u.role)


async def eligible_judges(db: AsyncSession, event_id: str) -> list:
    """Active roster rows whose account still holds the JUDGE role.

    A demoted account is skipped rather than erroring: the roster row stays
    for history, but no new work flows to someone who is no longer a judge.
    """
    res = await db.execute(
        select(User).join(EventJudge, EventJudge.user_id == User.id).where(
            EventJudge.event_id == event_id, EventJudge.is_active == True))  # noqa
    return [u for u in res.scalars().all() if _role_of(u) == "JUDGE"]


async def judge_loads(db: AsyncSession, event_id: str) -> dict:
    """{user_id: active assignment count} for the whole event, one query."""
    res = await db.execute(
        select(JudgeAssignment.judge_user_id, func.count()).where(
            JudgeAssignment.event_id == event_id,
            JudgeAssignment.status.in_(ACTIVE)).group_by(JudgeAssignment.judge_user_id))
    return {uid: n for uid, n in res.all()}


async def project_active_count(db: AsyncSession, project_id: str) -> int:
    res = await db.execute(select(func.count()).select_from(JudgeAssignment).where(
        JudgeAssignment.project_id == project_id,
        JudgeAssignment.status.in_(ACTIVE)))
    return res.scalar() or 0


async def _insert_slots(db: AsyncSession, event: Event, project_id: str,
                        judge_ids: list[str]) -> int:
    """Insert ASSIGNED rows, ignoring pairs that appeared concurrently."""
    if not judge_ids:
        return 0
    stmt = pg_insert(JudgeAssignment).values([{
        "id": f"asg_{uuid.uuid4().hex[:8]}",
        "event_id": event.id, "project_id": project_id,
        "judge_user_id": j, "status": AssignmentStatus.ASSIGNED,
    } for j in judge_ids])
    # Arbiter matches uq_assignment_project_judge_active exactly (columns
    # AND predicate): without the predicate Postgres cannot infer the
    # partial index and a concurrent duplicate would raise instead of
    # being ignored. Retry-safe idempotency.
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["project_id", "judge_user_id"],
        index_where=text("status <> 'REVOKED'"))
    res = await db.execute(stmt)
    return res.rowcount or 0


async def assign_project(db: AsyncSession, project_id: str,
                         allow_closed: bool = False) -> dict:
    """Fill one SUBMITTED project up to its event's judges_per_project.

    Returns {"assigned": [...user_ids newly picked...], "needed": n, "ok": bool}.
    No-op (ok=True, empty) when already covered or when no judge is eligible.
    Refused (ok=False + reason) once judging has closed: post-deadline work
    could never be scored, so it is never created — except for refills
    (allow_closed), which preserve coverage granted before the close rather
    than creating anything new.
    """
    p = await db.get(Project, project_id)
    if not p:
        err(404, "not_found", "Project not found")
    if (p.status.value if hasattr(p.status, "value") else str(p.status)) != "SUBMITTED":
        err(422, "validation_error", "Only submitted projects can be assigned for judging")
    event = await _lock_event(db, p.event_id)
    if not allow_closed and await _svc.judging_stage(db, event) in ("CLOSED", "RESULTS_READY"):
        return {"assigned": [], "needed": event.judges_per_project,
                "ok": False, "reason": "judging is closed for this event"}
    eligible = await eligible_judges(db, event.id)
    if not eligible:
        return {"assigned": [], "needed": event.judges_per_project, "ok": False,
                "reason": "no eligible judges assigned to this event"}
    # Coverage counts every live row — active AND completed. A finished
    # evaluation is still a judgment by that judge; ignoring it would both
    # over-assign finished projects and re-pick their judges, hitting the
    # partial unique index as an unhandled 500. Only REVOKED rows free a slot.
    res = await db.execute(select(JudgeAssignment.judge_user_id).where(
        JudgeAssignment.project_id == project_id,
        JudgeAssignment.status != AssignmentStatus.REVOKED))
    already = set(r[0] for r in res.all())
    need = max(0, event.judges_per_project - len(already))
    if need <= 0:
        return {"assigned": [], "needed": 0, "ok": True}
    loads = await judge_loads(db, event.id)
    cand = sorted(((loads.get(u.id, 0), u.id) for u in eligible if u.id not in already))
    picked = [uid for _, uid in cand[:need]]
    # Update the effective load before "selecting the next slot": later slots
    # in this same call see the picks above, never a stale snapshot.
    for i, uid in enumerate(picked):
        loads[uid] = loads.get(uid, 0) + 1
    created = await _insert_slots(db, event, project_id, picked)
    return {"assigned": picked, "needed": need, "ok": True, "created": created}


async def assign_all_pending(db: AsyncSession, event_id: str) -> dict:
    """Batch mode: every SUBMITTED project below its target gets filled."""
    event = await _lock_event(db, event_id)
    res = await db.execute(select(Project.id).where(
        Project.event_id == event.id, Project.status == ProjectStatus.SUBMITTED
    ).order_by(Project.submitted_at))
    touched, created = 0, 0
    for (pid,) in res.all():
        out = await assign_project(db, pid)
        if out["ok"] and out["assigned"]:
            touched += 1
            created += out.get("created", 0)
    return {"projects_touched": touched, "assignments_created": created}


async def remove_judge(db: AsyncSession, event_id: str, judge_user_id: str) -> dict:
    """Deactivate a roster row, revoke its incomplete work, and refill.

    COMPLETED assignments (and their evaluations) are never touched — history
    survives removal. Incomplete rows become REVOKED, then each affected
    project is refilled through the same balanced selection, excluding the
    removed judge and never duplicating an existing active pair.
    """
    event = await _lock_event(db, event_id)
    row = await db.get(EventJudge, (event.id, judge_user_id))
    if not row:
        err(404, "not_found", "This judge is not on this event's roster")
    row.is_active = False
    res = await db.execute(select(JudgeAssignment).where(
        JudgeAssignment.event_id == event.id,
        JudgeAssignment.judge_user_id == judge_user_id,
        JudgeAssignment.status.in_(ACTIVE)))
    incomplete = res.scalars().all()
    for a in incomplete:
        a.status = AssignmentStatus.REVOKED
    await db.flush()
    refilled, still_open = 0, 0
    for a in incomplete:
        # Refills preserve pre-close coverage, so they bypass the
        # closed-event gate.
        out = await assign_project(db, a.project_id, allow_closed=True)
        if out["assigned"]:
            refilled += 1
        else:
            still_open += 1
    return {"revoked": len(incomplete), "refilled": refilled,
            "still_open": still_open,
            "note": "completed work is untouched" if incomplete else "judge had no incomplete work"}


async def utilization(db: AsyncSession, event_id: str) -> list[dict]:
    """Per-judge load table for the organizer console."""
    res = await db.execute(
        select(User, EventJudge.is_active).join(
            EventJudge, EventJudge.user_id == User.id).where(
            EventJudge.event_id == event_id).order_by(User.display_name))
    loads = await judge_loads(db, event_id)
    done = await db.execute(
        select(Evaluation.judge_user_id, func.count()).where(
            Evaluation.event_id == event_id,
            Evaluation.status == EvaluationStatus.SUBMITTED
        ).group_by(Evaluation.judge_user_id))
    done_map = {uid: n for uid, n in done.all()}
    total = await db.execute(
        select(JudgeAssignment.judge_user_id, func.count()).where(
            JudgeAssignment.event_id == event_id
        ).group_by(JudgeAssignment.judge_user_id))
    total_map = {uid: n for uid, n in total.all()}
    out = []
    for u, active in res.all():
        out.append({
            "user_id": u.id, "email": u.email, "display_name": u.display_name,
            "role": _role_of(u), "is_active": active,
            "active_load": loads.get(u.id, 0),
            "completed": done_map.get(u.id, 0),
            "total_assigned": total_map.get(u.id, 0),
        })
    return out
