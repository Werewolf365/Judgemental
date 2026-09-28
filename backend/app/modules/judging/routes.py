"""Organizer/admin judging management: rubric, judging configuration, status.

Every route is event-scoped through managed_event (the organizer must run
THIS event; ADMIN bypasses per-event scoping platform-wide), matching the
tracks/prizes convention in modules/events/routes.py.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import RubricCriterion, User
from app.modules.auth.dependencies import require_roles
from app.modules.events.access import managed_event
from app.modules.events.routes import parse_dt
from app.modules.judging import assign as assign_svc
from app.modules.judging import scheduler
from app.modules.judging import service
from app.modules.judging.schemas import CriterionIn, JudgingConfigIn, JudgeAssignIn, ManualAssignIn
from app.shared.audit import record
from app.shared.errors import err
import uuid

router = APIRouter(tags=["judging"])


def _check_ranges(open_dt, close_dt):
    if open_dt and close_dt and open_dt > close_dt:
        err(422, "validation_error", "judging_open must be <= judging_close")


@router.get("/events/{event_id}/rubric")
async def list_criteria(event_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(RubricCriterion).where(
        RubricCriterion.event_id == e.id
    ).order_by(RubricCriterion.display_order, RubricCriterion.name))
    rows = res.scalars().all()
    return {"criteria": [service.criterion_out(c) for c in rows],
            "locked": await service.rubric_locked(db, e)}


@router.post("/events/{event_id}/rubric")
async def create_criterion(event_id: str, body: CriterionIn, request: Request,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    if await service.rubric_locked(db, e):
        err(409, "invalid_state_transition",
            "Judging has started — the rubric is locked so submitted scores keep their meaning")
    if body.weight is not None:
        res = await db.execute(select(RubricCriterion).where(
            RubricCriterion.event_id == e.id, RubricCriterion.is_active == True))  # noqa
        service.check_weight_cap(res.scalars().all(), None, body.weight)
    c = RubricCriterion(id=f"rub_{uuid.uuid4().hex[:8]}", event_id=e.id,
                        name=body.name, description=body.description,
                        weight=body.weight, display_order=body.display_order,
                        score_lo=body.score_lo if body.score_lo is not None else 0.0,
                        score_hi=body.score_hi if body.score_hi is not None else 10.0)
    db.add(c)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        err(409, "already_joined", "A criterion with this name already exists for this event")
    await db.refresh(c)
    await record(user, "event.rubric_created", target_type="rubric_criterion",
                 target_id=c.id, event_id=e.id,
                 detail={"name": c.name, "weight": c.weight}, request=request)
    return {"criterion": service.criterion_out(c)}


@router.patch("/rubric/{criterion_id}")
async def patch_criterion(criterion_id: str, body: CriterionIn, request: Request,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.modules.events.access import require_manageable
    c = await db.get(RubricCriterion, criterion_id)
    if not c:
        err(404, "not_found", "Criterion not found")
    # The criterion id alone is never enough: re-check the parent event.
    e = await require_manageable(db, user, c.event_id)
    if await service.rubric_locked(db, e):
        err(409, "invalid_state_transition",
            "Judging has started — the rubric is locked so submitted scores keep their meaning")
    if body.weight is not None:
        res = await db.execute(select(RubricCriterion).where(
            RubricCriterion.event_id == e.id, RubricCriterion.is_active == True))  # noqa
        service.check_weight_cap(res.scalars().all(), c.id, body.weight)
    c.name = body.name
    c.description = body.description
    c.weight = body.weight
    c.display_order = body.display_order
    # Omitted scale bounds reset to the 0–10 default (same convention as
    # weight: PATCH carries full objects, not diffs).
    c.score_lo = body.score_lo if body.score_lo is not None else 0.0
    c.score_hi = body.score_hi if body.score_hi is not None else 10.0
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        err(409, "already_joined", "A criterion with this name already exists for this event")
    await db.refresh(c)
    await record(user, "event.rubric_updated", target_type="rubric_criterion",
                 target_id=c.id, event_id=e.id,
                 detail={"name": c.name, "weight": c.weight}, request=request)
    return {"criterion": service.criterion_out(c)}


@router.delete("/rubric/{criterion_id}")
async def delete_criterion(criterion_id: str, request: Request,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.modules.events.access import require_manageable
    c = await db.get(RubricCriterion, criterion_id)
    if not c:
        err(404, "not_found", "Criterion not found")
    e = await require_manageable(db, user, c.event_id)
    name = c.name
    if await service.rubric_locked(db, e):
        # Post-start removal deactivates instead of deleting: evaluations
        # already reference criterion ids inside their scores payloads, so
        # the row must survive for history (the tracks pattern). One-way —
        # PATCH stays locked, so a deactivated criterion cannot come back.
        c.is_active = False
        await db.commit()
        await record(user, "event.rubric_deactivated", target_type="rubric_criterion",
                     target_id=criterion_id, event_id=e.id,
                     detail={"name": name, "reason": "judging started"}, request=request)
        return {"ok": True, "deactivated": True}
    await db.delete(c)
    await db.commit()
    await record(user, "event.rubric_deleted", target_type="rubric_criterion",
                 target_id=criterion_id, event_id=e.id,
                 detail={"name": name}, request=request)
    return {"ok": True}


@router.get("/events/{event_id}/judging")
async def judging_status(event_id: str, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Config + derived stage + counts. The console renders from this."""
    from app.models import EventJudge, JudgeAssignment, Evaluation, EvaluationStatus
    from app.modules.judging.pairwise import connected_components, generate_pairs
    from sqlalchemy import func
    e = await managed_event(db, user, event_id)
    judges = (await db.execute(select(func.count()).select_from(EventJudge).where(
        EventJudge.event_id == e.id, EventJudge.is_active == True))).scalar() or 0  # noqa
    assignments = (await db.execute(select(func.count()).select_from(JudgeAssignment).where(
        JudgeAssignment.event_id == e.id))).scalar() or 0
    completed = (await db.execute(select(func.count()).select_from(Evaluation).where(
        Evaluation.event_id == e.id,
        Evaluation.status == EvaluationStatus.SUBMITTED))).scalar() or 0
    res = await db.execute(select(RubricCriterion).where(RubricCriterion.event_id == e.id))
    # Model routing for the console: the Uncertainty tab appears only when
    # Bradley–Terry cannot run (no pairs, or a disconnected graph) — never
    # alongside a viable BT ranking. A past Bayesian run keeps the tab visible
    # so its history is never orphaned.
    sub = (await db.execute(select(Evaluation).where(
        Evaluation.event_id == e.id,
        Evaluation.status == EvaluationStatus.SUBMITTED))).scalars().all()
    rows = [{"judge_user_id": v.judge_user_id, "project_id": v.project_id,
             "weighted_score": v.weighted_score, "evaluation_id": v.id}
            for v in sub if v.weighted_score is not None]
    pairs = generate_pairs(rows)
    bt_viable = False
    if pairs:
        projs = sorted({p["winner_project_id"] for p in pairs} |
                       {p["loser_project_id"] for p in pairs})
        bt_viable = len(connected_components(pairs, projs)) == 1
    bayes_ready = await service.latest_succeeded_run(
        db, e.id, model_prefix="hier-bayes-score") is not None
    f = lambda x: x.isoformat() if x else None
    return {
        "config": {
            "judging_open": f(e.judging_open), "judging_close": f(e.judging_close),
            "judges_per_project": e.judges_per_project, "rolling_judging": e.rolling_judging,
            "crowd_blend_enabled": e.crowd_blend_enabled, "crowd_weight": e.crowd_weight,
        },
        "auto_assign": {
            "enabled": scheduler.state["enabled"],
            "every_seconds": scheduler.state["every_seconds"],
            "last_run": scheduler.state["last_run"],
            "last_created": scheduler.state["last_created"],
        },
        "stage": await service.judging_stage(db, e),
        "rubric_locked": await service.rubric_locked(db, e),
        "models": {"bt_viable": bt_viable, "bayes_ready": bayes_ready},
        "counts": {
            "judges": judges, "assignments": assignments,
            "evaluations_submitted": completed,
            "criteria": len(res.scalars().all()),
        },
    }


@router.patch("/events/{event_id}/judging")
async def judging_config(event_id: str, body: JudgingConfigIn, request: Request,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    vals = body.model_dump(exclude_unset=True)
    if "judging_open" in vals:
        e.judging_open = parse_dt(vals["judging_open"])
    if "judging_close" in vals:
        e.judging_close = parse_dt(vals["judging_close"])
    _check_ranges(e.judging_open, e.judging_close)
    # judges_per_project applies to future assignments; existing work is
    # never rewritten, so changing it mid-flight stays coherent.
    if vals.get("judges_per_project") is not None:
        e.judges_per_project = vals["judges_per_project"]
    if vals.get("rolling_judging") is not None:
        e.rolling_judging = vals["rolling_judging"]
    # Judge/crowd blend weights (organizer-owned, persisted per event).
    if vals.get("crowd_blend_enabled") is not None:
        e.crowd_blend_enabled = vals["crowd_blend_enabled"]
    if vals.get("crowd_weight") is not None:
        e.crowd_weight = vals["crowd_weight"]
    await db.commit()
    await db.refresh(e)
    await record(user, "event.judging_configured", target_type="event", target_id=e.id,
                 event_id=e.id, detail={"fields": sorted(vals.keys())}, request=request)
    f = lambda x: x.isoformat() if x else None
    return {"config": {
        "judging_open": f(e.judging_open), "judging_close": f(e.judging_close),
        "judges_per_project": e.judges_per_project, "rolling_judging": e.rolling_judging,
        "crowd_blend_enabled": e.crowd_blend_enabled, "crowd_weight": e.crowd_weight,
    }}


# ---- Judge roster ----
# Assignment grants a seat at this event's judging table, never a role: the
# account must already hold the JUDGE role (mirrors the organizer roster,
# which requires ORGANIZER/ADMIN). Removal deactivates the row and reassigns
# incomplete work; completed evaluations survive untouched.

@router.get("/events/{event_id}/judges")
async def list_judges(event_id: str, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    return {"judges": await assign_svc.utilization(db, e.id),
            "balance": await assign_svc.assignment_health(db, e.id)}


@router.post("/events/{event_id}/judges")
async def add_judge(event_id: str, body: JudgeAssignIn, request: Request,
                    db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    from app.models import EventJudge
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    e = await managed_event(db, user, event_id)
    if not body.email and not body.user_id:
        err(422, "validation_error", "Provide the judge's email or user_id")
    stmt = select(User).where(User.email_norm == body.email) if body.email \
        else select(User).where(User.id == body.user_id)
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        # Same answer whether the account is missing or invisible: no
        # directory enumeration through this endpoint.
        err(404, "not_found", "No account with that email. Ask them to sign up first, then an admin can grant the judge role.")
    role = target.role.value if hasattr(target.role, "value") else str(target.role)
    if role != "JUDGE":
        err(422, "validation_error",
            f"{target.email} is a {role.lower()}, not a judge. Grant the judge role first.")
    ins = pg_insert(EventJudge).values(
        event_id=e.id, user_id=target.id, assigned_by=user.id, is_active=True)
    # Re-adding a removed judge reactivates the same row (history preserved).
    ins = ins.on_conflict_do_update(
        index_elements=["event_id", "user_id"],
        set_={"is_active": True, "assigned_by": user.id})
    await db.execute(ins)
    await db.commit()
    await record(user, "event.judge_assigned", target_type="user", target_id=target.id,
                 event_id=e.id, detail={"email": target.email, "event": e.name},
                 request=request)
    rows = await assign_svc.utilization(db, e.id)
    mine = next((r for r in rows if r["user_id"] == target.id), None)
    return {"judge": mine, "added": True}


@router.delete("/events/{event_id}/judges/{user_id}")
async def remove_judge(event_id: str, user_id: str, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    out = await assign_svc.remove_judge(db, e.id, user_id)
    await db.commit()
    gone = await db.get(User, user_id)
    await record(user, "event.judge_removed", target_type="user", target_id=user_id,
                 event_id=e.id, detail={"email": getattr(gone, "email", None),
                                        "revoked": out["revoked"], "refilled": out["refilled"]},
                 request=request)
    return {"ok": True, **out}


@router.post("/events/{event_id}/assignments/batch")
async def batch_assign(event_id: str, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """One-big-assignment mode: fill every under-assigned SUBMITTED project.

    Idempotent — running it twice changes nothing the second time. This is
    also the explicit trigger for rolling_judging=false events; the
    background sweep (judging/scheduler.py) runs the same pass on its own
    cadence and is never reset, skipped, or doubled by this button.
    """
    e = await managed_event(db, user, event_id)
    if await service.judging_stage(db, e) in ("CLOSED", "RESULTS_READY"):
        err(409, "invalid_state_transition",
            "Judging is closed — new assignments cannot be created. Remove this block by reopening the judging window.")
    out = await assign_svc.assign_all_pending(db, e.id)
    await db.commit()
    await record(user, "event.assignments_batched", target_type="event", target_id=e.id,
                 event_id=e.id, detail=out, request=request)
    return {"ok": True, **out}


@router.post("/events/{event_id}/assignments/manual")
async def manual_assign(event_id: str, body: ManualAssignIn, request: Request,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Organizer-picked judge→project assignment from the existing pool.

    Names one eligible roster judge for one submitted project — the close-call
    workflow (extra judging exactly where uncertainty is highest). Refuses
    closed windows, non-pool judges, and duplicate live pairs. May exceed
    judges_per_project: extra judging is the point, not a coverage fill.
    """
    e = await managed_event(db, user, event_id)
    out = await assign_svc.assign_judge_to_project(
        db, e.id, body.project_id, body.judge_user_id)
    await db.commit()
    await record(user, "event.assignment_manual", target_type="project",
                 target_id=body.project_id, event_id=e.id,
                 detail={"judge": out["assignment"]["judge_user_id"]},
                 request=request)
    return {"ok": True, **out}
