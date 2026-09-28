"""Final calculation + results + CSV export (prompt_T2 §7/§12/§14).

POST /events/{id}/results/calculate runs the whole pipeline synchronously
(no workers exist in this stack — PROMPT.md bans new services — and a BFGS
fit over competition-scale data is milliseconds):
  SUBMITTED evaluations → weighted snapshots → within-judge pairs →
  connectivity gate → priors → MAP fit → persist run + observations +
  project/judge results + reliability history.

Guards: calculating requires stage CLOSED (judging_close set and passed) —
never before the judging period closes. Recalculation is allowed (new run
row each time; runs are never mutated, only superseded), and a RUNNING run
younger than 5 minutes blocks a duplicate trigger.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import (Evaluation, EvaluationStatus, JudgeAssignment, ModelJudgeResult,
                        ModelProjectResult, ModelRun, ModelRunStatus, PairwiseObservation,
                        Project, JudgeReliabilityHistory, RubricCriterion, Team, Track, User)
from app.modules.auth.dependencies import require_roles
from app.modules.events.access import managed_event
from app.modules.judging import crowd_bt, reliability as rel
from app.modules.judging import service
from app.modules.judging.pairwise import connected_components, generate_pairs
from app.shared.audit import record
from app.shared.clock import utcnow
from app.shared.errors import err
import uuid

router = APIRouter(tags=["judging"])

RECALC_GUARD_MINUTES = 5


def _status_of(e) -> str:
    return e.status.value if hasattr(e.status, "value") else str(e.status)


@router.post("/events/{event_id}/results/calculate")
async def calculate(event_id: str, request: Request,
                    db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    stage = await service.judging_stage(db, e)
    if stage not in ("CLOSED", "RESULTS_READY"):
        why = {"NOT_STARTED": "judging has not opened yet",
               "OPEN": "judging is still open — close the judging deadline first"}.get(stage, stage)
        err(409, "invalid_state_transition", f"Cannot calculate now: {why}")
    # Recalculation (RESULTS_READY) is allowed: it appends a NEW run row and
    # never mutates the old one, so every version stays auditable. The runs
    # list endpoint shows the full version history.
    # Serialize concurrent triggers per event; the recency guard below then
    # turns the loser into a clean 409 instead of a duplicate run.
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
        err(422, "validation_error", "No submitted evaluations to rank")
    rows = [{"judge_user_id": v.judge_user_id, "project_id": v.project_id,
             "weighted_score": v.weighted_score,
             "evaluation_id": v.id} for v in evals if v.weighted_score is not None]
    pairs = generate_pairs(rows)
    if not pairs:
        err(422, "validation_error",
            "No comparable pairs: every judge scored fewer than two projects, so no ordering exists to model")
    pair_projects = sorted({p["winner_project_id"] for p in pairs} |
                           {p["loser_project_id"] for p in pairs})
    comps = connected_components(pairs, pair_projects)
    if len(comps) > 1:
        stranded = sorted([sorted(c) for c in comps], key=len)[0]
        err(422, "validation_error",
            f"Comparison graph is disconnected: {len(stranded)} project(s) share no judge with the rest "
            f"({', '.join(stranded[:5])}), so they cannot be placed on one common scale")
    # Deterministic origin: lexicographically smallest ranked project.
    reference = pair_projects[0]
    judges = sorted({p["judge_user_id"] for p in pairs})
    priors, prior_src = {}, {}
    for j in judges:
        pr = await rel.prior_for_judge(db, j, e.id)
        priors[j] = (pr["mu"], pr["sigma"])
        prior_src[j] = pr["source"]

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    run = ModelRun(id=run_id, event_id=e.id,
                   model_version=crowd_bt.MODEL_VERSION,
                   status=ModelRunStatus.RUNNING)
    db.add(run)
    await db.flush()
    try:
        out = crowd_bt.fit(pairs, pair_projects, judges,
                           reference_project=reference, priors=priors)
        if not out["success"]:
            raise RuntimeError("optimizer did not converge")
        ranking = crowd_bt.rank(out["thetas"], reference)
        res2 = await db.execute(select(RubricCriterion).where(RubricCriterion.event_id == e.id))
        crits = [c for c in res2.scalars().all() if c.is_active]
        weights = service.resolve_weights(crits) if crits else {}
        run.config = {
            "model_version": out["model_version"], "theta_sigma": crowd_bt.THETA_SIGMA,
            "reference_project": reference,
            "priors": {j: {"mu": priors[j][0], "sigma": priors[j][1], "source": prior_src[j]} for j in judges},
            "rubric": [{"id": c.id, "name": c.name, "weight": c.weight,
                        "normalized": weights.get(c.id)} for c in crits],
            "judges_per_project": e.judges_per_project,
            "n_submitted_evaluations": len(evals),
        }
        for p in pairs:
            db.add(PairwiseObservation(
                id=f"pwo_{uuid.uuid4().hex[:8]}", model_run_id=run.id,
                judge_user_id=p["judge_user_id"], winner_project_id=p["winner_project_id"],
                loser_project_id=p["loser_project_id"], weight=1.0,
                source_evaluation_ids=p["source_evaluation_ids"]))
        for r in ranking:
            db.add(ModelProjectResult(model_run_id=run.id, project_id=r["project_id"],
                                      theta=r["theta"], rank=r["rank"]))
        for j in judges:
            db.add(ModelJudgeResult(model_run_id=run.id, judge_user_id=j,
                                    r=out["reliabilities"][j],
                                    prior_mu=priors[j][0], prior_sigma=priors[j][1],
                                    posterior_mu=out["log_reliabilities"][j]))
            # The Bayesian chain, persisted: this posterior is the next
            # competition's prior.
            db.add(JudgeReliabilityHistory(
                id=f"rel_{uuid.uuid4().hex[:8]}", judge_user_id=j, event_id=e.id,
                model_run_id=run.id, posterior_mu=out["log_reliabilities"][j],
                posterior_sigma=None, r=out["reliabilities"][j]))
        run.status = ModelRunStatus.SUCCEEDED
        run.finished_at = utcnow()
        run.n_projects, run.n_judges, run.n_comparisons = (
            len(pair_projects), len(judges), len(pairs))
        await db.commit()
    except Exception as ex:
        # The whole attempt rolls back; then a fresh FAILED row (same id, so
        # the audit trail can reference the attempt) is committed on its own
        # transaction. Reusing the rolled-back instance would be murky
        # (expiry semantics after rollback), so a new row is built instead.
        await db.rollback()
        db.add(ModelRun(id=run_id, event_id=e.id,
                        model_version=crowd_bt.MODEL_VERSION,
                        status=ModelRunStatus.FAILED, finished_at=utcnow(),
                        n_projects=len(pair_projects), n_judges=len(judges),
                        n_comparisons=len(pairs), error=str(ex)[:500]))
        await db.commit()
        await record(user, "event.results_failed", target_type="model_run",
                     target_id=run_id, event_id=e.id,
                     detail={"error": str(ex)[:200]}, request=request)
        err(500, "calculation_failed", f"Ranking calculation failed: {ex}")
    await record(user, "event.results_calculated", target_type="model_run",
                 target_id=run_id, event_id=e.id,
                 detail={"projects": len(pair_projects), "judges": len(judges),
                         "comparisons": len(pairs)}, request=request)
    return {"run_id": run_id, "projects": len(pair_projects),
            "judges": len(judges), "comparisons": len(pairs)}


async def _run_payload(db: AsyncSession, run: ModelRun) -> dict:
    res = await db.execute(select(ModelProjectResult, Project.title, Team.name, Track.name
                                  ).join(Project, Project.id == ModelProjectResult.project_id
                                  ).join(Team, Team.id == Project.team_id
                                  ).join(Track, Track.id == Project.track_id
                                  ).where(ModelProjectResult.model_run_id == run.id
                                  ).order_by(ModelProjectResult.rank))
    ranking = [{"rank": r.rank, "project_id": r.project_id, "title": title,
                "team": team, "track": track, "theta": r.theta}
               for r, title, team, track in res.all()]
    res2 = await db.execute(select(ModelJudgeResult, User.display_name, User.email).join(
        User, User.id == ModelJudgeResult.judge_user_id).where(
        ModelJudgeResult.model_run_id == run.id).order_by(
        ModelJudgeResult.r.desc()))
    judges = [{"user_id": r.judge_user_id, "display_name": name, "email": email,
               "reliability": r.r, "prior_mu": r.prior_mu,
               "prior_sigma": r.prior_sigma, "posterior_mu": r.posterior_mu}
              for r, name, email in res2.all()]
    f = lambda x: x.isoformat() if x else None
    return {
        "run": {"id": run.id, "event_id": run.event_id,
                "model_version": run.model_version, "status": _status_of(run),
                "started_at": f(run.started_at), "finished_at": f(run.finished_at),
                "n_projects": run.n_projects, "n_judges": run.n_judges,
                "n_comparisons": run.n_comparisons, "config": run.config or {},
                "error": run.error},
        "ranking": ranking, "judges": judges,
    }


@router.get("/events/{event_id}/results")
async def latest_results(event_id: str, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Latest SUCCEEDED run with full ranking + reliabilities. 404 while
    judging is still in flight — the judging status endpoint is the
    progress view until then."""
    e = await managed_event(db, user, event_id)
    run = await service.latest_succeeded_run(db, e.id)
    if not run:
        err(404, "not_found", "No final ranking yet — calculate after the judging deadline")
    return await _run_payload(db, run)


@router.get("/events/{event_id}/results/runs")
async def list_runs(event_id: str, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Every model run for the event, newest first: the version history that
    makes recalculation auditable instead of destructive."""
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(ModelRun).where(
        ModelRun.event_id == e.id).order_by(ModelRun.started_at.desc()))
    f = lambda x: x.isoformat() if x else None
    return {"runs": [{
        "id": r.id, "model_version": r.model_version, "status": _status_of(r),
        "started_at": f(r.started_at), "finished_at": f(r.finished_at),
        "n_projects": r.n_projects, "n_judges": r.n_judges,
        "n_comparisons": r.n_comparisons, "error": r.error,
    } for r in res.scalars().all()]}


@router.get("/export.csv")
async def export_csv(event_id: str = "", db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Organizer CSV export of judging work (the checker's csv_export route).

    One row per evaluation (judge x project), readable at EVERY stage —
    drafts included with a status column — so organizers can follow along
    while judging is still in flight, not only after calculation. Columns
    carry everything the process used: project, team (+ captain), track,
    judge, per-criterion raw scores with their weight % and normalized
    share, the weighted total, plus rank/theta once a SUCCEEDED run exists
    (blank before that). Event-scoped: organizers only export events they
    run. Zero evaluations -> header alone, an honest empty export.
    """
    from app.models import (Evaluation, EvaluationStatus, JudgeAssignment, Project,
                            ProjectStatus, RubricCriterion, Team, TeamMember, TeamRole,
                            Track, User as U)
    if not event_id:
        err(422, "validation_error", "event_id is required")
    e = await managed_event(db, user, event_id)

    def q(v):
        s = str(v if v is not None else "")
        return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\"\n') else s

    res = await db.execute(select(RubricCriterion).where(
        RubricCriterion.event_id == e.id, RubricCriterion.is_active == True  # noqa
    ).order_by(RubricCriterion.display_order, RubricCriterion.name))
    crits = res.scalars().all()
    try:
        weights = service.resolve_weights(crits) if crits else {}
    except Exception:
        # Mid-edit rubric (mixed/partial weights): export raw scores with
        # blank shares rather than refusing the whole export.
        weights = {}

    res = await db.execute(select(TeamMember, U.display_name, U.email).join(
        U, U.id == TeamMember.user_id).where(TeamMember.role == TeamRole.CAPTAIN))
    captains = {tm.team_id: (name, email) for tm, name, email in res.all()}

    run = await service.latest_succeeded_run(db, e.id)
    finals = {}
    if run:
        res = await db.execute(select(ModelProjectResult).where(
            ModelProjectResult.model_run_id == run.id))
        finals = {r.project_id: (r.rank, r.theta) for r in res.scalars().all()}

    res = await db.execute(
        select(Evaluation, Project, Team, Track, U).join(
            Project, Project.id == Evaluation.project_id).join(
            Team, Team.id == Project.team_id).join(
            Track, Track.id == Project.track_id).join(
            U, U.id == Evaluation.judge_user_id).where(
            Evaluation.event_id == e.id).order_by(Project.title, U.display_name))
    rows = res.all()

    head = ["project", "team", "team_leader", "team_leader_email", "track",
            "judge", "judge_email", "evaluation_status", "submitted_at"]
    for c in crits:
        head += [f"{c.name} [score]", f"{c.name} [weight%]"]
    head += ["weighted_total", "rank", "theta"]
    lines = [",".join(head)]
    for ev, p, tm, tr, ju in rows:
        st = ev.status.value if hasattr(ev.status, "value") else str(ev.status)
        scores = ev.scores or {}
        cells = [p.title, tm.name, *(captains.get(tm.id, ("", ""))),
                 tr.name if tr else "", ju.display_name, ju.email, st,
                 ev.submitted_at.isoformat() if ev.submitted_at else ""]
        for c in crits:
            w = weights.get(c.id)
            cells += [scores.get(c.id, ""),
                      f"{c.weight:g}%" if c.weight is not None else "",
                      f"{w:.4f}" if w is not None else ""]
        cells.append(f"{ev.weighted_score:.4f}" if ev.weighted_score is not None else "")
        rank, theta = finals.get(p.id, ("", ""))
        cells.append(rank)
        cells.append(f"{theta:.4f}" if isinstance(theta, (int, float)) else "")
        lines.append(",".join(q(c) for c in cells))
    body = "\n".join(lines) + "\n"
    return PlainTextResponse(body, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=\"results-{e.slug}.csv\"",
    })
