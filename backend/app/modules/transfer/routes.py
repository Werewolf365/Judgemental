"""T4 bulk transfer (organizer-only, event-scoped): full export as a ZIP of
CSVs, and CSV import for organizer-authored setup data.

Export covers every analysis metric the console holds: participants (with
registration details), organizers, judges (roster + loads), tracks, prizes,
rubric, teams (+members), projects, evaluations (per-criterion scores),
assignments, ballots, comments, results (latest rankings, either model), and
the event audit trail. Missing data exports as a header-only CSV — honest
empty, never fabricated rows.

Import is create-only for setup data the organizer owns: tracks, prizes,
rubric criteria, judges roster (by email), organizers (by email). Roster
imports enforce the same role rules as the single-add endpoints (JUDGE role
for judges, ORGANIZER/ADMIN for organizers); duplicates are skipped, never
errored. Everything else (users, scores, votes) is never imported — those
rows are evidence, not configuration.
"""
import csv
import io
import json
import zipfile
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (AuditLog, Ballot, BayesProjectResult, Comment,
                        Evaluation, Event, EventJudge, EventOrganizer,
                        EventParticipant, JudgeAssignment, ModelProjectResult,
                        ModelRun, ModelRunStatus, ParticipantRegistration,
                        Prize, Project, RubricCriterion, Team, TeamMember,
                        Track, User)
from app.modules.auth.dependencies import require_roles
from app.modules.events.access import managed_event
from app.modules.judging import service as judging_service
from app.shared.audit import record
from app.shared.errors import err

router = APIRouter(tags=["transfer"])

EXPORTABLE = ("participants", "organizers", "judges", "tracks", "prizes",
              "rubric", "teams", "projects", "evaluations", "assignments",
              "ballots", "comments", "results", "audit")
IMPORTABLE = ("tracks", "prizes", "rubric", "judges", "organizers")
MAX_IMPORT_BYTES = 1_000_000


def _ev(v):
    return v.value if hasattr(v, "value") else str(v if v is not None else "")


def _iso(v):
    return v.isoformat() if v else ""


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    return buf.getvalue()


async def _users_by_id(db: AsyncSession, ids: set) -> dict:
    if not ids:
        return {}
    res = await db.execute(select(User).where(User.id.in_(ids)))
    return {u.id: u for u in res.scalars().all()}


async def _build(db: AsyncSession, e: Event, name: str) -> tuple[str, str]:
    """(filename, csv text) for one dataset. Raises err(422) on unknown."""
    if name == "participants":
        res = await db.execute(select(EventParticipant, User, ParticipantRegistration).join(
            User, User.id == EventParticipant.user_id).outerjoin(
            ParticipantRegistration,
            (ParticipantRegistration.event_id == EventParticipant.event_id) &
            (ParticipantRegistration.user_id == EventParticipant.user_id)).where(
            EventParticipant.event_id == e.id).order_by(User.display_name))
        teams = await _team_names(db, e.id)
        rows = [{"email": u.email, "display_name": u.display_name,
                 "team": teams.get(u.id, ""), "joined_at": _iso(p.joined_at),
                 "full_name": r.full_name if r else "", "phone": r.phone if r else "",
                 "age": r.age if r else "", "degree": r.degree if r else "",
                 "year_of_study": r.year_of_study if r else "",
                 "institution": r.institution if r else "",
                 "category": r.category if r else ""}
                for p, u, r in res.all()]
        return "participants.csv", _csv(rows, ["email", "display_name", "team", "joined_at",
            "full_name", "phone", "age", "degree", "year_of_study",
            "institution", "category"])
    if name == "organizers":
        res = await db.execute(select(EventOrganizer, User).join(
            User, User.id == EventOrganizer.user_id).where(
            EventOrganizer.event_id == e.id).order_by(User.display_name))
        pairs = res.all()
        by = await _users_by_id(db, {o.assigned_by for o, _ in pairs if o.assigned_by})
        rows = []
        for o, u in pairs:
            rows.append({"email": u.email, "display_name": u.display_name,
                         "role": _ev(u.role),
                         "assigned_by": by[o.assigned_by].email if o.assigned_by in by else "",
                         "created_at": _iso(o.created_at),
                         "is_creator": e.created_by == u.id})
        return "organizers.csv", _csv(rows, ["email", "display_name", "role",
            "assigned_by", "created_at", "is_creator"])
    if name == "judges":
        res = await db.execute(select(EventJudge, User).join(
            User, User.id == EventJudge.user_id).where(
            EventJudge.event_id == e.id).order_by(User.display_name))
        pairs = res.all()
        loads = {}
        for o, _ in pairs:
            a = (await db.execute(select(func.count()).select_from(JudgeAssignment).where(
                JudgeAssignment.event_id == e.id, JudgeAssignment.judge_user_id == o.user_id,
                JudgeAssignment.status != "REVOKED"))).scalar() or 0
            c = (await db.execute(select(func.count()).select_from(Evaluation).where(
                Evaluation.event_id == e.id, Evaluation.judge_user_id == o.user_id,
                Evaluation.status == "SUBMITTED"))).scalar() or 0
            loads[o.user_id] = (a, c)
        rows = [{"email": u.email, "display_name": u.display_name,
                 "is_active": o.is_active, "assignments": loads[o.user_id][0],
                 "submitted": loads[o.user_id][1]}
                for o, u in pairs]
        return "judges.csv", _csv(rows, ["email", "display_name", "is_active",
            "assignments", "submitted"])
    if name == "tracks":
        res = await db.execute(select(Track).where(Track.event_id == e.id).order_by(Track.name))
        return "tracks.csv", _csv(
            [{"name": t.name, "is_active": t.is_active} for t in res.scalars().all()],
            ["name", "is_active"])
    if name == "prizes":
        res = await db.execute(select(Prize, Track.name).outerjoin(
            Track, Track.id == Prize.track_id).where(
            Prize.event_id == e.id).order_by(Prize.display_order, Prize.name))
        return "prizes.csv", _csv(
            [{"name": p.name, "description": p.description or "",
              "value": p.value_desc or "", "track": tn or "",
              "display_order": p.display_order} for p, tn in res.all()],
            ["name", "description", "value", "track", "display_order"])
    if name == "rubric":
        res = await db.execute(select(RubricCriterion).where(
            RubricCriterion.event_id == e.id).order_by(RubricCriterion.display_order))
        return "rubric.csv", _csv(
            [{"name": c.name, "description": c.description or "", "weight": c.weight,
              "scale_lo": c.score_lo, "scale_hi": c.score_hi,
              "is_active": c.is_active, "display_order": c.display_order}
             for c in res.scalars().all()],
            ["name", "description", "weight", "scale_lo", "scale_hi",
             "is_active", "display_order"])
    if name == "teams":
        res = await db.execute(select(Team).where(Team.event_id == e.id).order_by(Team.name))
        teams = res.scalars().all()
        users = await _users_by_id(db, {m.user_id for t in teams for m in
            (await db.execute(select(TeamMember).where(TeamMember.team_id == t.id))).scalars().all()})
        rows = []
        for t in teams:
            mems = (await db.execute(select(TeamMember).where(TeamMember.team_id == t.id))).scalars().all()
            for m in mems:
                u = users.get(m.user_id)
                rows.append({"team": t.name, "member_email": u.email if u else m.user_id,
                             "member_name": u.display_name if u else "",
                             "role": _ev(m.role), "joined_at": _iso(m.joined_at)})
        return "teams.csv", _csv(rows, ["team", "member_email", "member_name",
            "role", "joined_at"])
    if name == "projects":
        res = await db.execute(select(Project, Team.name, Track.name).join(
            Team, Team.id == Project.team_id).join(
            Track, Track.id == Project.track_id).where(
            Project.event_id == e.id).order_by(Project.created_at))
        return "projects.csv", _csv(
            [{"title": p.title, "team": tn, "track": trn, "status": _ev(p.status),
              "is_visible": p.is_visible, "summary": p.summary or "",
              "repo_url": p.repo_url or "", "demo_url": p.demo_url or "",
              "submitted_at": _iso(p.submitted_at)} for p, tn, trn in res.all()],
            ["title", "team", "track", "status", "is_visible", "summary",
             "repo_url", "demo_url", "submitted_at"])
    if name == "evaluations":
        res = await db.execute(select(Evaluation, Project.title, User.display_name).join(
            Project, Project.id == Evaluation.project_id).join(
            User, User.id == Evaluation.judge_user_id).where(
            Evaluation.event_id == e.id).order_by(Evaluation.created_at))
        crits = {c.id: c.name for c in (await db.execute(
            select(RubricCriterion).where(RubricCriterion.event_id == e.id))).scalars().all()}
        rows = []
        for v, title, judge in res.all():
            scores = v.scores or {}
            rows.append({"project": title, "judge": judge,
                         "status": _ev(v.status), "weighted_score": v.weighted_score,
                         "scores": json.dumps({crits.get(k, k): s for k, s in scores.items()}),
                         "comment": v.comment or "", "submitted_at": _iso(v.submitted_at)})
        return "evaluations.csv", _csv(rows, ["project", "judge", "status",
            "weighted_score", "scores", "comment", "submitted_at"])
    if name == "assignments":
        res = await db.execute(select(JudgeAssignment, Project.title, User.display_name).join(
            Project, Project.id == JudgeAssignment.project_id).join(
            User, User.id == JudgeAssignment.judge_user_id).where(
            JudgeAssignment.event_id == e.id).order_by(JudgeAssignment.created_at))
        return "assignments.csv", _csv(
            [{"project": t, "judge": j, "status": _ev(a.status),
              "created_at": _iso(a.created_at), "completed_at": _iso(a.completed_at)}
             for a, t, j in res.all()],
            ["project", "judge", "status", "created_at", "completed_at"])
    if name == "ballots":
        res = await db.execute(select(Ballot, Project.title).join(
            Project, Project.id == Ballot.project_id).where(
            Ballot.event_id == e.id).order_by(Ballot.created_at))
        return "ballots.csv", _csv(
            [{"project": t, "voter": b.voter_key, "votes": b.votes,
              "created_at": _iso(b.created_at)} for b, t in res.all()],
            ["project", "voter", "votes", "created_at"])
    if name == "comments":
        res = await db.execute(select(Comment, Project.title, User.display_name).join(
            Project, Project.id == Comment.project_id).join(
            User, User.id == Comment.author_user_id).where(
            Comment.event_id == e.id).order_by(Comment.created_at))
        return "comments.csv", _csv(
            [{"project": t, "author": a, "body": c.body,
              "is_hidden": c.is_hidden, "created_at": _iso(c.created_at)}
             for c, t, a in res.all()],
            ["project", "author", "body", "is_hidden", "created_at"])
    if name == "results":
        rows = []
        for prefix, model in (("crowd-bt", "bt"), ("hier-bayes-score", "bayes")):
            run = await judging_service.latest_succeeded_run(db, e.id, model_prefix=prefix)
            if not run:
                continue
            if model == "bt":
                res = await db.execute(select(ModelProjectResult, Project.title).join(
                    Project, Project.id == ModelProjectResult.project_id).where(
                    ModelProjectResult.model_run_id == run.id))
                for r, title in res.all():
                    rows.append({"model": model, "run": run.id, "project": title,
                                 "rank": r.blended_rank if r.blended_rank is not None else r.rank,
                                 "score": r.blended_score if r.blended_score is not None else r.theta,
                                 "blended": r.blended_rank is not None})
            else:
                res = await db.execute(select(BayesProjectResult, Project.title).join(
                    Project, Project.id == BayesProjectResult.project_id).where(
                    BayesProjectResult.model_run_id == run.id))
                for r, title in res.all():
                    rows.append({"model": model, "run": run.id, "project": title,
                                 "rank": r.blended_rank if r.blended_rank is not None else r.rank,
                                 "score": r.blended_score if r.blended_score is not None else r.score_mean,
                                 "blended": r.blended_rank is not None})
        return "results.csv", _csv(rows, ["model", "run", "project", "rank",
            "score", "blended"])
    if name == "audit":
        res = await db.execute(select(AuditLog).where(
            AuditLog.event_id == e.id).order_by(AuditLog.created_at))
        return "audit.csv", _csv(
            [{"action": a.action, "actor": a.actor_email or a.actor_id or "",
              "target": f"{a.target_type or ''}:{a.target_id or ''}",
              "detail": json.dumps(a.detail or {}), "ip": a.ip or "",
              "created_at": _iso(a.created_at)} for a in res.scalars().all()],
            ["action", "actor", "target", "detail", "ip", "created_at"])
    err(422, "validation_error", f"Unknown dataset: {name}. Choose from: {', '.join(EXPORTABLE)}")


async def _team_names(db: AsyncSession, event_id: str) -> dict:
    res = await db.execute(select(TeamMember, Team.name).join(
        Team, Team.id == TeamMember.team_id).where(Team.event_id == event_id))
    out = {}
    for m, name in res.all():
        out.setdefault(m.user_id, name)
    return out


@router.get("/events/{event_id}/export")
async def export_zip(event_id: str, datasets: str = "all",
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """One ZIP of CSVs for the requested datasets (default: everything).
    Organizer-only, event-scoped through managed_event."""
    e = await managed_event(db, user, event_id)
    if (datasets or "all").strip().lower() == "all":
        names = list(EXPORTABLE)
    else:
        names = [d.strip().lower() for d in datasets.split(",") if d.strip()]
        for n in names:
            if n not in EXPORTABLE:
                err(422, "validation_error",
                    f"Unknown dataset: {n}. Choose from: all, {', '.join(EXPORTABLE)}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            fn, text = await _build(db, e, n)
            zf.writestr(fn, text)
    await record(user, "event.exported", target_type="event", target_id=e.id,
                 event_id=e.id, detail={"datasets": names})
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="event-{e.slug}-export.zip"'})


def _rows_of(content: bytes, required: list[str]) -> tuple[list[dict], list[str]]:
    """Parse CSV bytes; returns (rows, errors). Missing headers are fatal."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["file is not valid UTF-8 CSV"]
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["empty file: no header row"]
    missing = [h for h in required if h not in (reader.fieldnames or [])]
    if missing:
        return [], [f"missing required column(s): {', '.join(missing)}"]
    return list(reader), []


@router.post("/events/{event_id}/import")
async def import_csv(event_id: str, dataset: str = Form(...),
                     file: UploadFile = File(...),
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    """Create-only CSV import for organizer-owned setup data. Duplicates are
    skipped (reported), never errored; roster imports enforce role rules."""
    e = await managed_event(db, user, event_id)
    # Plain ID strings: rollback() expires ORM instances, so nothing below
    # may touch e./user. attributes after the first rollback in this request.
    eid, uid, uemail = e.id, user.id, user.email
    actor = SimpleNamespace(id=uid, email=uemail)
    ds = (dataset or "").strip().lower()
    if ds not in IMPORTABLE:
        err(422, "validation_error",
            f"Importable datasets: {', '.join(IMPORTABLE)}")
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        err(422, "validation_error", "File too large (1MB cap)")
    created, skipped, errors = 0, 0, []
    if ds == "tracks":
        rows, errors = _rows_of(content, ["name"])
        seen = set()
        for i, r in enumerate(rows, start=2):
            name = (r.get("name") or "").strip()[:100]
            if not name or name in seen:
                skipped += 1
                continue
            seen.add(name)
            try:
                from app.models import Track as _T
                db.add(_T(event_id=eid, name=name))
                await db.flush()
                created += 1
            except IntegrityError:
                await db.rollback()
                skipped += 1
    elif ds == "prizes":
        rows, errors = _rows_of(content, ["name"])
        res = await db.execute(select(Track).where(Track.event_id == eid))
        tracks = {t.name.lower(): t.id for t in res.scalars().all()}
        for i, r in enumerate(rows, start=2):
            name = (r.get("name") or "").strip()[:200]
            if not name:
                skipped += 1
                continue
            track_id = None
            tn = (r.get("track") or "").strip().lower()
            if tn:
                track_id = tracks.get(tn)
                if not track_id:
                    errors.append(f"row {i}: unknown track '{r.get('track')}'")
                    skipped += 1
                    continue
            try:
                order = int((r.get("display_order") or "0").strip() or 0)
            except ValueError:
                errors.append(f"row {i}: bad display_order")
                skipped += 1
                continue
            db.add(Prize(event_id=eid, name=name,
                         description=(r.get("description") or "").strip()[:2000] or None,
                         value_desc=(r.get("value") or "").strip()[:500] or None,
                         track_id=track_id, display_order=order))
            created += 1
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            errors.append("duplicate prize rows were skipped")
    elif ds == "rubric":
        rows, errors = _rows_of(content, ["name"])
        res = await db.execute(select(RubricCriterion).where(
            RubricCriterion.event_id == eid, RubricCriterion.is_active == True))  # noqa
        total = sum(c.weight or 0 for c in res.scalars().all())
        order = 0
        for i, r in enumerate(rows, start=2):
            name = (r.get("name") or "").strip()[:200]
            if not name:
                skipped += 1
                continue
            wraw = (r.get("weight") or "").strip()
            try:
                w = None if not wraw else float(wraw)
            except ValueError:
                errors.append(f"row {i}: bad weight '{wraw}'")
                skipped += 1
                continue
            if w is not None and not (0 < w <= 100):
                errors.append(f"row {i}: weight must be 0 < w <= 100")
                skipped += 1
                continue
            if w is not None and total + w > 100 + 1e-9:
                errors.append(f"row {i}: would push the rubric past 100%")
                skipped += 1
                continue
            try:
                lo = float((r.get("scale_lo") or "0").strip() or 0)
                hi = float((r.get("scale_hi") or "10").strip() or 10)
            except ValueError:
                errors.append(f"row {i}: bad scale")
                skipped += 1
                continue
            if not (hi > lo):
                errors.append(f"row {i}: scale max must exceed min")
                skipped += 1
                continue
            try:
                db.add(RubricCriterion(event_id=eid, name=name,
                    description=(r.get("description") or "").strip()[:2000] or None,
                    weight=w, display_order=order, score_lo=lo, score_hi=hi))
                await db.flush()
                order += 1
                if w is not None:
                    total += w
                created += 1
            except IntegrityError:
                await db.rollback()
                skipped += 1
    elif ds in ("judges", "organizers"):
        rows, errors = _rows_of(content, ["email"])
        want_role = ("JUDGE",) if ds == "judges" else ("ORGANIZER", "ADMIN")
        for i, r in enumerate(rows, start=2):
            email = (r.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            res = await db.execute(select(User).where(User.email_norm == email))
            target = res.scalars().first()
            if not target:
                errors.append(f"row {i}: no account for {email}")
                skipped += 1
                continue
            role = target.role.value if hasattr(target.role, "value") else str(target.role)
            if role not in want_role:
                errors.append(f"row {i}: {email} is a {role.lower()} (needs {ds[:-1]} role)")
                skipped += 1
                continue
            if ds == "judges":
                from app.models import EventJudge as _EJ
                row = _EJ(event_id=eid, user_id=target.id, assigned_by=uid)
                db.add(row)
                try:
                    await db.flush()
                    created += 1
                except IntegrityError:
                    await db.rollback()
                    skipped += 1
            else:
                from app.models import EventOrganizer as _EO
                row = _EO(event_id=eid, user_id=target.id, assigned_by=uid)
                db.add(row)
                try:
                    await db.flush()
                    created += 1
                except IntegrityError:
                    await db.rollback()
                    skipped += 1
    await db.commit()
    await record(actor, "event.imported", target_type="event", target_id=eid,
                 event_id=eid, detail={"dataset": ds, "created": created,
                                       "skipped": skipped})
    return {"dataset": ds, "created": created, "skipped": skipped,
            "errors": errors[:20]}
