"""Edge-case Bayesian scoring endpoints (single-judge-per-project).

The Bradley–Terry model (results.py) is untouched and remains primary wherever
pairwise data exists. These routes cover the case BT cannot: each project judged
once, no comparable pairs, disconnected graph. Same conventions as results.py —
calculate only after close, recalculation appends a new versioned run, failures
persist a FAILED row, everything audited.

Endpoints (all ORGANIZER/ADMIN, event-scoped through managed_event):
  POST /events/{id}/bayes/calculate — fit R = theta + b + eps, store run
  GET  /events/{id}/bayes/results   — latest SUCCEEDED run: Top-K uncertainty
                                       view in plain language + judges'
                                       severity effects + extra-judging
                                       recommendations
  GET  /events/{id}/bayes/runs      — version history (this model only)

Refitting after additional judgments is POST calculate again: a new run row,
old versions untouched. The judging window must be reopened for the extra
scores first (judge writes are refused while CLOSED), then closed again.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import (BayesJudgeEffect, BayesProjectResult, BayesRankOverride,
                        Evaluation, EvaluationStatus, ModelRun, ModelRunStatus,
                        Project, RubricCriterion, Team, Track, User)
from app.modules.auth.dependencies import require_roles
from app.modules.events.access import managed_event
from app.modules.judging import assign as assign_svc
from app.modules.judging import hier_score
from app.modules.judging import service
from app.modules.judging.schemas import RankSwapIn
from app.shared.audit import record
from app.shared.clock import utcnow
from app.shared.errors import err
import uuid

router = APIRouter(tags=["judging"])

RECALC_GUARD_MINUTES = 5
MODEL_PREFIX = "hier-bayes-score"


def _status_of(e) -> str:
    return e.status.value if hasattr(e.status, "value") else str(e.status)


def _seed_from_run(run_id: str) -> int:
    return hier_score._seed_from(run_id)


async def _bt_feasibility_note(db: AsyncSession, event_id: str) -> str | None:
    """If pairwise data is sufficient, BT remains the official ranking and
    this view is supplementary. Never raises — a broken probe must not block
    the edge-case calculation it is advising about."""
    try:
        from app.modules.judging.pairwise import connected_components, generate_pairs
        res = await db.execute(select(Evaluation).where(
            Evaluation.event_id == event_id,
            Evaluation.status == EvaluationStatus.SUBMITTED))
        rows = [{"judge_user_id": v.judge_user_id, "project_id": v.project_id,
                 "weighted_score": v.weighted_score, "evaluation_id": v.id}
                for v in res.scalars().all() if v.weighted_score is not None]
        pairs = generate_pairs(rows)
        if not pairs:
            return None
        projs = sorted({p["winner_project_id"] for p in pairs} |
                       {p["loser_project_id"] for p in pairs})
        if len(connected_components(pairs, projs)) == 1:
            return ("Pairwise judging data is sufficient for this event, so the "
                    "Bradley–Terry ranking remains the official result — "
                    "treat this Bayesian view as supplementary uncertainty "
                    "information, not a replacement.")
        return None
    except Exception:
        return None


async def _suggest_judge(db: AsyncSession, event_id: str, project_id: str) -> dict:
    """Lowest-load eligible judge not already on this project (advisory only;
    the organizer assigns through the normal roster/batch endpoints)."""
    from app.models import JudgeAssignment, AssignmentStatus
    try:
        eligible = await assign_svc.eligible_judges(db, event_id)
        if not eligible:
            return {"user_id": None, "reason": "no eligible judges on the roster"}
        res = await db.execute(select(JudgeAssignment.judge_user_id).where(
            JudgeAssignment.project_id == project_id,
            JudgeAssignment.status != AssignmentStatus.REVOKED))
        already = {r[0] for r in res.all()}
        loads = await assign_svc.judge_loads(db, event_id)
        cand = sorted(((loads.get(u.id, 0), u.id, u.display_name)
                       for u in eligible if u.id not in already))
        if not cand:
            return {"user_id": None, "reason": "every eligible judge already scored this project"}
        _, uid, name = cand[0]
        return {"user_id": uid, "display_name": name,
                "reason": "lowest current load among judges not yet on this project"}
    except Exception as ex:
        return {"user_id": None, "reason": f"suggestion unavailable: {ex}"}


@router.post("/events/{event_id}/bayes/calculate")
async def calculate_bayes(event_id: str, request: Request,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    stage = await service.judging_stage(db, e)
    if stage not in ("CLOSED", "RESULTS_READY"):
        why = {"NOT_STARTED": "judging has not opened yet",
               "OPEN": "judging is still open — close the judging deadline first"}.get(stage, stage)
        err(409, "invalid_state_transition", f"Cannot calculate now: {why}")
    await db.execute(select(e.__class__).where(e.__class__.id == e.id).with_for_update())
    res = await db.execute(select(ModelRun).where(
        ModelRun.event_id == e.id, ModelRun.status == ModelRunStatus.RUNNING,
        ModelRun.started_at >= utcnow() - timedelta(minutes=RECALC_GUARD_MINUTES)))
    if res.scalar_one_or_none():
        err(409, "invalid_state_transition", "A calculation is already running for this event")

    res = await db.execute(select(Evaluation).where(
        Evaluation.event_id == e.id, Evaluation.status == EvaluationStatus.SUBMITTED))
    evals = res.scalars().all()
    if not evals:
        err(422, "validation_error", "No submitted evaluations to score")

    res2 = await db.execute(select(RubricCriterion).where(RubricCriterion.event_id == e.id))
    crits = [c for c in res2.scalars().all() if c.is_active]
    try:
        weights = service.resolve_weights(crits) if crits else {}
    except Exception as ex:
        err(422, "validation_error", f"Cannot score under the current rubric: {ex}")
    scales = {c.id: (float(c.score_lo if c.score_lo is not None else 0.0),
                     float(c.score_hi if c.score_hi is not None else 10.0))
              for c in crits}

    observations, skipped, fallbacks = [], [], 0
    for v in evals:
        try:
            score = hier_score.score_evaluation(v.scores or {}, weights, scales)
        except ValueError:
            # Stale-criterion fallback: the evaluation's own snapshot (taken
            # under the weights then in force) is already on the 0..10 scale.
            # Counted in config so the audit trail shows it.
            if v.weighted_score is None or not (0.0 <= float(v.weighted_score) <= 10.0):
                skipped.append(v.id)
                continue
            score = float(v.weighted_score)
            fallbacks += 1
        observations.append({"project_id": v.project_id, "judge_id": v.judge_user_id,
                             "score": score, "evaluation_id": v.id})
    if skipped:
        err(422, "validation_error",
            f"{len(skipped)} submitted evaluation(s) match no rubric criterion and have no usable "
            f"snapshot — resolve the rubric or resubmit them before calculating")
    if not observations:
        err(422, "validation_error", "No usable evaluation scores to model")

    run_id = f"bay_{uuid.uuid4().hex[:8]}"
    run = ModelRun(id=run_id, event_id=e.id,
                   model_version=hier_score.MODEL_VERSION,
                   status=ModelRunStatus.RUNNING)
    db.add(run)
    await db.flush()
    try:
        out = hier_score.fit(observations, seed=_seed_from_run(run_id))
        recs = hier_score.recommend_extra_judging(out)
        for r in recs:
            r["suggested_judge"] = await _suggest_judge(db, e.id, r["project_a"])
        notice = await _bt_feasibility_note(db, e.id)
        run.config = {
            "model_version": out["model_version"],
            "hypers": out["hypers"],
            "variance": out["variance"],
            "seed": out["seed"], "n_samples": out["n_samples"],
            "top_k": out["top_k"],
            "rubric": [{"id": c.id, "name": c.name, "weight": c.weight,
                        "normalized": weights.get(c.id)} for c in crits],
            "judges_per_project": e.judges_per_project,
            "n_submitted_evaluations": len(evals),
            "n_snapshot_fallbacks": fallbacks,
            "notice": notice,
        }
        for r in out["ranking"]:
            db.add(BayesProjectResult(
                model_run_id=run.id, project_id=r["project_id"],
                score_mean=r["score"], score_sd=r["score_sd"],
                score_lo=r["likely_range"][0], score_hi=r["likely_range"][1],
                rank=r["rank"], p_top_k=r["p_top"], confidence=r["confidence"]))
        for j, eff in out["judge_effects"].items():
            db.add(BayesJudgeEffect(
                model_run_id=run.id, judge_user_id=j,
                b_mean=eff["b_mean"], b_sd=eff["b_sd"],
                n_evaluations=eff["n"]))
        # Recommendations live in config (JSON) — they advise future work,
        # they are not results, so no table rows.
        run.config["recommendations"] = recs
        run.status = ModelRunStatus.SUCCEEDED
        run.finished_at = utcnow()
        run.n_projects, run.n_judges, run.n_comparisons = (
            len(out["projects"]), len(out["judges"]), len(observations))
        await db.commit()
    except Exception as ex:
        await db.rollback()
        db.add(ModelRun(id=run_id, event_id=e.id,
                        model_version=hier_score.MODEL_VERSION,
                        status=ModelRunStatus.FAILED, finished_at=utcnow(),
                        n_projects=0, n_judges=0,
                        n_comparisons=len(observations), error=str(ex)[:500]))
        await db.commit()
        await record(user, "event.bayes_failed", target_type="model_run",
                     target_id=run_id, event_id=e.id,
                     detail={"error": str(ex)[:200]}, request=request)
        err(500, "calculation_failed", f"Bayesian scoring failed: {ex}")
    await record(user, "event.bayes_calculated", target_type="model_run",
                 target_id=run_id, event_id=e.id,
                 detail={"projects": run.n_projects, "judges": run.n_judges,
                         "observations": run.n_comparisons}, request=request)
    return {"run_id": run_id, "projects": run.n_projects,
            "judges": run.n_judges, "observations": run.n_comparisons}


async def _payload(db: AsyncSession, run: ModelRun) -> dict:
    res = await db.execute(select(BayesProjectResult, Project.title, Team.name, Track.name
                                  ).join(Project, Project.id == BayesProjectResult.project_id
                                  ).join(Team, Team.id == Project.team_id
                                  ).join(Track, Track.id == Project.track_id
                                  ).where(BayesProjectResult.model_run_id == run.id
                                  ).order_by(BayesProjectResult.rank))
    rows = res.all()
    K = (run.config or {}).get("top_k", 10)
    cfg = run.config or {}
    recs = cfg.get("recommendations", [])
    # Per-project closest call, for the one-line row summaries.
    closest: dict = {}
    for r in recs:
        for pid, other in ((r["project_a"], r["project_b"]),
                           (r["project_b"], r["project_a"])):
            if pid not in closest:
                p = r["p_a_above_b"] if pid == r["project_a"] else 1.0 - r["p_a_above_b"]
                closest[pid] = {"project_id": other, "p_above": round(p, 4)}
    ranking = []
    for r, title, team, track in rows:
        plain = hier_score.plain_summary_row(
            {"rank": r.rank, "score": r.score_mean, "p_top": r.p_top_k,
             "confidence": r.confidence,
             "close_competitors": [closest[r.project_id]] if r.project_id in closest else []},
            K, len(rows))
        ranking.append({
            "rank": r.rank, "project_id": r.project_id, "title": title,
            "team": team, "track": track,
            "score": r.score_mean, "score_sd": r.score_sd,
            "likely_range": [r.score_lo, r.score_hi],
            "p_top": r.p_top_k, "confidence": r.confidence,
            "summary": plain})
    res2 = await db.execute(select(BayesJudgeEffect, User.display_name, User.email).join(
        User, User.id == BayesJudgeEffect.judge_user_id).where(
        BayesJudgeEffect.model_run_id == run.id).order_by(
        BayesJudgeEffect.b_mean.desc()))
    judges = [{"user_id": r.judge_user_id, "display_name": name, "email": email,
               "severity": r.b_mean, "severity_sd": r.b_sd,
               "n_evaluations": r.n_evaluations,
               "plain": ("Tends to score strictly — scores were adjusted upward to compensate."
                         if r.b_mean < -0.5 else
                         "Tends to score generously — scores were adjusted downward to compensate."
                         if r.b_mean > 0.5 else
                         "Scores about average — little adjustment needed.")}
              for r, name, email in res2.all()]
    # Resolve close-competitor titles for the Top-K rows.
    titles = {r["project_id"]: r["title"] for r in ranking}
    by_pid = {r["project_id"]: r for r in ranking}
    eff_ids, has_manual = await _effective_order(db, run)
    effective = []
    for pos, pid in enumerate(eff_ids, start=1):
        r = dict(by_pid.get(pid, {"project_id": pid, "title": titles.get(pid, pid)}))
        r["effective_rank"] = pos
        r["rank_source"] = "manual" if has_manual else "model"
        effective.append(r)
    f = lambda x: x.isoformat() if x else None
    return {
        "run": {"id": run.id, "event_id": run.event_id,
                "model_version": run.model_version, "status": _status_of(run),
                "started_at": f(run.started_at), "finished_at": f(run.finished_at),
                "n_projects": run.n_projects, "n_judges": run.n_judges,
                "n_observations": run.n_comparisons,
                "config": {k: v for k, v in cfg.items() if k != "recommendations"},
                "error": run.error},
        "top_k": K,
        "ranking": ranking,
        "effective": effective,
        "has_manual_overrides": has_manual,
        "close_calls": [
            {"project_a": titles.get(r["project_a"], r["project_a"]),
             "project_a_id": r["project_a"],
             "project_b": titles.get(r["project_b"], r["project_b"]),
             "project_b_id": r["project_b"],
             "p_a_above_b": r["p_a_above_b"],
             "plain": (f"{titles.get(r['project_a'], 'A')} is "
                       f"{round(r['p_a_above_b'] * 100)}% likely to rank above "
                       f"{titles.get(r['project_b'], 'B')}."),
             "boundary": r["boundary"], "reason": r["reason"],
             "suggested_judge": r.get("suggested_judge")}
            for r in recs],
        "judges": judges,
        "notice": cfg.get("notice"),
        "flags": {
            "uncertain_boundary": any(
                r["confidence"] == "Low" and r["rank"] <= K for r in ranking),
            "message": ("Some Top-{} positions are Low confidence — consider the "
                        "recommended extra judging below before announcing.".format(K)
                        if any(r["confidence"] == "Low" and r["rank"] <= K
                               for r in ranking) else None),
        },
    }


async def _effective_order(db: AsyncSession, run: ModelRun) -> tuple[list, bool]:
    """(ordered project ids, has_manual). Model rank order unless manual
    override rows exist, in which case the override snapshot wins."""
    res = await db.execute(select(BayesProjectResult.project_id).where(
        BayesProjectResult.model_run_id == run.id))
    model_ids = list(res.scalars().all())
    res = await db.execute(select(BayesRankOverride).where(
        BayesRankOverride.model_run_id == run.id).order_by(
        BayesRankOverride.manual_rank))
    rows = res.scalars().all()
    if not rows:
        return model_ids, False
    return [r.project_id for r in rows], True


@router.post("/events/{event_id}/bayes/swap")
async def swap_ranks(event_id: str, body: RankSwapIn, request: Request,
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Interchange two ranks in the latest Bayesian scoring run.

    For uncertain close calls the organizer — not the model — has the last
    word: swap A above B (or back) with an optional reason. Writes a full
    manual_rank snapshot (1..P) so the effective ranking is always exactly
    what was decided; the model ranking underneath is never mutated.
    DELETE .../bayes/overrides reverts to the model order.
    """
    from sqlalchemy import delete as sa_delete
    e = await managed_event(db, user, event_id)
    run = await service.latest_succeeded_run(db, e.id, model_prefix=MODEL_PREFIX)
    if not run:
        err(404, "not_found", "No Bayesian scoring yet — calculate first")
    order, _ = await _effective_order(db, run)
    try:
        new_order = hier_score.apply_swap(order, body.project_a_id, body.project_b_id)
    except ValueError as ex:
        err(422, "validation_error", str(ex))
    await db.execute(sa_delete(BayesRankOverride).where(
        BayesRankOverride.model_run_id == run.id))
    for pos, pid in enumerate(new_order, start=1):
        db.add(BayesRankOverride(
            id=f"bov_{uuid.uuid4().hex[:8]}", model_run_id=run.id,
            project_id=pid, manual_rank=pos,
            reason=body.reason, created_by=user.id))
    await db.commit()
    await record(user, "event.bayes_ranks_swapped", target_type="model_run",
                 target_id=run.id, event_id=e.id,
                 detail={"a": body.project_a_id, "b": body.project_b_id,
                         "reason": body.reason}, request=request)
    return {"ok": True, "run_id": run.id, "order": new_order}


@router.delete("/events/{event_id}/bayes/overrides")
async def clear_overrides(event_id: str, request: Request,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Revert to the model ranking: drop the manual snapshot (kept as is is
    the default — this endpoint only undoes a previous swap)."""
    from sqlalchemy import delete as sa_delete
    e = await managed_event(db, user, event_id)
    run = await service.latest_succeeded_run(db, e.id, model_prefix=MODEL_PREFIX)
    if not run:
        err(404, "not_found", "No Bayesian scoring yet — calculate first")
    res = await db.execute(sa_delete(BayesRankOverride).where(
        BayesRankOverride.model_run_id == run.id))
    await db.commit()
    await record(user, "event.bayes_overrides_cleared", target_type="model_run",
                 target_id=run.id, event_id=e.id, detail={}, request=request)
    return {"ok": True, "run_id": run.id, "cleared": True}


@router.get("/events/{event_id}/bayes/results")
async def latest_bayes(event_id: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Latest SUCCEEDED Bayesian scoring run: the Top-K uncertainty view.
    404 while nothing has been calculated yet."""
    e = await managed_event(db, user, event_id)
    run = await service.latest_succeeded_run(db, e.id, model_prefix=MODEL_PREFIX)
    if not run:
        err(404, "not_found",
            "No Bayesian scoring yet — calculate after the judging deadline")
    return await _payload(db, run)


@router.get("/events/{event_id}/bayes/runs")
async def list_bayes_runs(event_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Every Bayesian scoring run for the event, newest first."""
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(ModelRun).where(
        ModelRun.event_id == e.id,
        ModelRun.model_version.like(f"{MODEL_PREFIX}%")
    ).order_by(ModelRun.started_at.desc()))
    f = lambda x: x.isoformat() if x else None
    return {"runs": [{
        "id": r.id, "model_version": r.model_version, "status": _status_of(r),
        "started_at": f(r.started_at), "finished_at": f(r.finished_at),
        "n_projects": r.n_projects, "n_judges": r.n_judges,
        "n_observations": r.n_comparisons, "error": r.error,
    } for r in res.scalars().all()]}
