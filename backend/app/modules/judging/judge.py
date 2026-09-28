"""Judge-facing endpoints. Strictly JUDGE role; a judge sees only their own
assignments and evaluations.

Peer isolation is enforced at two levels: require_roles("JUDGE") keeps every
other role out with 403, and every assignment id is re-checked against the
caller's user id, so one judge can never open, score, or submit another
judge's work. The checker's peer_scores URL is GET /judge/scores?judge=<id>:
any id that is not the caller answers 403.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import (AssignmentStatus, Evaluation, EvaluationStatus, Event,
                        JudgeAssignment, Project, RubricCriterion, Team, Track, User)
from app.modules.auth.dependencies import require_roles
from app.modules.judging import service
from app.shared.errors import err
from app.shared.clock import utcnow
import uuid

router = APIRouter(tags=["judge"])

SCORE_MIN, SCORE_MAX = 0, 10


def _judge() -> object:
    return require_roles("JUDGE")


def _assignment_out(a: JudgeAssignment) -> dict:
    f = lambda x: x.isoformat() if x else None
    st = a.status.value if hasattr(a.status, "value") else str(a.status)
    return {"id": a.id, "event_id": a.event_id, "project_id": a.project_id,
            "status": st, "created_at": f(a.created_at),
            "completed_at": f(a.completed_at)}


async def _own_assignment(db: AsyncSession, assignment_id: str, user: User) -> JudgeAssignment:
    a = await db.get(JudgeAssignment, assignment_id)
    if not a or a.judge_user_id != user.id:
        # Same answer for missing and someone else's: no id oracle.
        err(403, "forbidden", "No such assignment")
    return a


def _validate_scores(criteria: list, scores: dict) -> dict:
    """Keys must be active criterion ids; values numbers in [0, 10]."""
    if not isinstance(scores, dict):
        err(422, "validation_error", "scores must be an object of criterion_id to number")
    known = {c.id for c in criteria if c.is_active}
    clean = {}
    for cid, v in scores.items():
        if cid not in known:
            err(422, "validation_error", f"Unknown or inactive criterion: {cid}")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            err(422, "validation_error", f"Score for “{cid}” must be a number")
        if not (SCORE_MIN <= float(v) <= SCORE_MAX):
            err(422, "validation_error",
                f"Scores must be between {SCORE_MIN} and {SCORE_MAX}")
        clean[cid] = float(v)
    return clean


async def _editable_assignment(db: AsyncSession, a: JudgeAssignment, user: User):
    # Ambient state first: past the deadline EVERY write is refused the same
    # way, so clients need only one "judging is over" branch. The finished
    # item then gets its specific 409 only while judging is still open.
    e = await db.get(Event, a.event_id)
    stage = await service.judging_stage(db, e)
    if stage != "OPEN":
        msg = {"NOT_STARTED": "Judging has not opened for this event",
               "CLOSED": "The judging deadline has passed",
               "RESULTS_READY": "Final results are published — judging is closed"}.get(stage, "Judging is not open")
        err(403, "deadline_passed" if stage in ("CLOSED", "RESULTS_READY") else "forbidden", msg)
    st = a.status.value if hasattr(a.status, "value") else str(a.status)
    if st in ("COMPLETED", "REVOKED"):
        err(409, "invalid_state_transition",
            "This assignment is finished and can no longer be edited")
    res = await db.execute(select(RubricCriterion).where(RubricCriterion.event_id == a.event_id))
    return e, res.scalars().all()


@router.get("/judge/assignments")
async def my_assignments(db: AsyncSession = Depends(get_db),
                         user: User = Depends(_judge())):
    res = await db.execute(
        select(JudgeAssignment, Project.title, Track.name).join(
            Project, Project.id == JudgeAssignment.project_id).join(
            Track, Track.id == Project.track_id).where(
            JudgeAssignment.judge_user_id == user.id).order_by(
            JudgeAssignment.created_at.desc()))
    out = []
    for a, title, track in res.all():
        d = _assignment_out(a)
        d.update({"project_title": title, "track": track})
        out.append(d)
    return {"assignments": out}


@router.get("/judge/assignments/{assignment_id}")
async def assignment_detail(assignment_id: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(_judge())):
    a = await _own_assignment(db, assignment_id, user)
    p = await db.get(Project, a.project_id)
    tm = await db.get(Team, p.team_id) if p else None
    tr = await db.get(Track, p.track_id) if p else None
    res = await db.execute(select(RubricCriterion).where(
        RubricCriterion.event_id == a.event_id
    ).order_by(RubricCriterion.display_order, RubricCriterion.name))
    criteria = [service.criterion_out(c) for c in res.scalars().all() if c.is_active]
    res2 = await db.execute(select(Evaluation).where(Evaluation.assignment_id == a.id))
    ev = res2.scalar_one_or_none()
    d = _assignment_out(a)
    d.update({
        "project": {"id": p.id, "title": p.title, "summary": p.summary,
                    "description": p.description, "repo_url": p.repo_url,
                    "demo_url": p.demo_url, "team": tm.name if tm else None,
                    "track": tr.name if tr else None} if p else None,
        "rubric": criteria,
        "evaluation": {"scores": ev.scores or {}, "comment": ev.comment,
                       "status": ev.status.value if hasattr(ev.status, "value") else str(ev.status),
                       "weighted_score": ev.weighted_score} if ev else None,
    })
    return {"assignment": d}


@router.post("/judge/assignments/{assignment_id}/scores")
async def save_scores(assignment_id: str, body: dict,
                      db: AsyncSession = Depends(get_db),
                      user: User = Depends(_judge())):
    """Save a draft evaluation. Partial scores allowed — drafts stay partial,
    mirroring project drafts. Never touches the assignment's finished state."""
    a = await _own_assignment(db, assignment_id, user)
    _, criteria = await _editable_assignment(db, a, user)
    clean = _validate_scores(criteria, (body.get("scores") or {}))
    comment = body.get("comment")
    if comment is not None and len(str(comment)) > 5000:
        err(422, "validation_error", "Comment is too long")
    res = await db.execute(select(Evaluation).where(Evaluation.assignment_id == a.id))
    ev = res.scalar_one_or_none()
    if ev and (ev.status.value if hasattr(ev.status, "value") else str(ev.status)) != "DRAFT":
        err(409, "invalid_state_transition", "Submitted evaluations cannot be edited")
    if not ev:
        ev = Evaluation(id=f"evl_{uuid.uuid4().hex[:8]}", assignment_id=a.id,
                        event_id=a.event_id, project_id=a.project_id,
                        judge_user_id=user.id)
        db.add(ev)
    ev.scores = clean
    ev.comment = (str(comment) if comment is not None else ev.comment)
    ev.updated_at = utcnow()
    if (a.status.value if hasattr(a.status, "value") else str(a.status)) == "ASSIGNED":
        a.status = AssignmentStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(ev)
    return {"evaluation": {"scores": ev.scores, "comment": ev.comment, "status": "DRAFT"}}


@router.post("/judge/assignments/{assignment_id}/submit")
async def submit_scores(assignment_id: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(_judge())):
    """Finalize: requires every active criterion scored, snapshots the
    weighted total under current normalized weights. One-way, transactional."""
    a = await _own_assignment(db, assignment_id, user)
    _, criteria = await _editable_assignment(db, a, user)
    res = await db.execute(select(Evaluation).where(Evaluation.assignment_id == a.id))
    ev = res.scalar_one_or_none()
    if not ev or not (ev.scores or {}):
        err(422, "validation_error", "Score every criterion before submitting")
    if (ev.status.value if hasattr(ev.status, "value") else str(ev.status)) != "DRAFT":
        err(409, "invalid_state_transition", "Already submitted")
    clean = _validate_scores(criteria, ev.scores)
    weights = service.resolve_weights(criteria)
    missing = [c.name for c in criteria if c.is_active and c.id not in clean]
    if missing:
        err(422, "validation_error",
            f"Still missing scores for: {', '.join(f'“{m}”' for m in missing)}")
    ev.scores = clean
    ev.weighted_score = sum(clean[cid] * w for cid, w in weights.items())
    ev.status = EvaluationStatus.SUBMITTED
    ev.submitted_at = utcnow()
    ev.updated_at = ev.submitted_at
    a.status = AssignmentStatus.COMPLETED
    a.completed_at = ev.submitted_at
    await db.commit()
    return {"ok": True, "weighted_score": ev.weighted_score}


async def _resolve_judge_param(db: AsyncSession, judge: str):
    """The ?judge= selector accepts a user id or an email (emails survive
    database reseeds; generated uuids do not — the checker's peer_scores URL
    uses the stable email form). Unknown values resolve to None, which the
    caller treats exactly like a peer: 403, no oracle."""
    if not judge:
        return None
    if "@" in judge:
        res = await db.execute(select(User).where(User.email_norm == judge.strip().lower()))
        u = res.scalar_one_or_none()
        return u.id if u else None
    return judge


@router.get("/judge/scores")
async def my_scores(judge: str = "", db: AsyncSession = Depends(get_db),
                    user: User = Depends(_judge())):
    """The checker's judge_scores route: the caller's own submitted
    evaluations. ?judge=<id-or-email> for anyone but yourself answers 403 —
    this is also the peer_scores URL, so peer isolation is tested exactly
    here."""
    if judge:
        target = await _resolve_judge_param(db, judge)
        if target != user.id:
            err(403, "forbidden", "Judges can only read their own scores")
    res = await db.execute(
        select(Evaluation, Project.title).join(
            Project, Project.id == Evaluation.project_id).where(
            Evaluation.judge_user_id == user.id,
            Evaluation.status == EvaluationStatus.SUBMITTED
        ).order_by(Evaluation.submitted_at.desc()))
    return {"scores": [{
        "evaluation_id": ev.id, "assignment_id": ev.assignment_id,
        "project_id": ev.project_id, "project_title": title,
        "scores": ev.scores or {}, "weighted_score": ev.weighted_score,
        "submitted_at": ev.submitted_at.isoformat() if ev.submitted_at else None,
    } for ev, title in res.all()]}
