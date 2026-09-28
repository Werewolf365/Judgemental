"""T4 certificates: organizer template upload + participant issue/view.

Certificates are HTML-rendered from the organizer's base image with the
participant's details overlaid — no PDF/image service exists in this stack
(PROMPT.md bans new services) and no imaging dependency is vendored, so
rendering stays client-side and printable via the browser.

Issuing is lazy and idempotent: the first authenticated view after results
are declared (a SUCCEEDED run exists) creates the row; repeat views return
it. WINNER = member of the rank-1 team under the blended-aware order
(blended_rank when the run blended, else model rank); everyone registered
gets at least PARTICIPATION.
"""
import hashlib

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models import (BayesProjectResult, Certificate, CertificateKind,
                        CertificateTemplate, Event, EventParticipant,
                        ModelProjectResult, ModelRun, ModelRunStatus,
                        Project, Team, TeamMember, User)
from app.modules.auth.dependencies import current_user, require_roles
from app.modules.events.access import managed_event
from app.modules.judging import service as judging_service
from app.shared.audit import record
from app.shared.errors import err

router = APIRouter(tags=["certificates"])

MAX_TEMPLATE_CHARS = 2_000_000


class TemplateIn(BaseModel):
    image: str = Field(max_length=MAX_TEMPLATE_CHARS + 64)


def _code(event_id: str, user_id: str) -> str:
    return hashlib.sha256(f"cert:{event_id}:{user_id}".encode()).hexdigest()[:16].upper()


async def _declared_run(db: AsyncSession, event_id: str):
    """Latest SUCCEEDED run of either model, or None (results not declared)."""
    best = None
    for prefix in ("crowd-bt", "hier-bayes-score"):
        run = await judging_service.latest_succeeded_run(db, event_id, model_prefix=prefix)
        if run and (best is None or (run.finished_at and best.finished_at and
                                     run.finished_at > best.finished_at)):
            best = run
    return best


def _is_bt(run) -> bool:
    return (run.model_version or "").startswith("crowd-bt")


async def _winner_project_id(db: AsyncSession, run) -> Optional[str]:
    """Project id at effective rank 1 (blended-aware), or None."""
    if _is_bt(run):
        res = await db.execute(select(ModelProjectResult).where(
            ModelProjectResult.model_run_id == run.id))
        rows = res.scalars().all()
        key = lambda r: (r.blended_rank if r.blended_rank is not None else r.rank)
    else:
        res = await db.execute(select(BayesProjectResult).where(
            BayesProjectResult.model_run_id == run.id))
        rows = res.scalars().all()
        key = lambda r: (r.blended_rank if r.blended_rank is not None else r.rank)
    if not rows:
        return None
    return min(rows, key=key).project_id


async def _my_project(db: AsyncSession, event_id: str, user_id: str):
    """(project_id, team_name, rank-or-None) for the caller's team, if any."""
    res = await db.execute(select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(
        Team.event_id == event_id, TeamMember.user_id == user_id))
    team = res.scalars().first()
    if not team:
        return None, None, None
    res = await db.execute(select(Project).where(Project.team_id == team.id))
    proj = res.scalars().first()
    return (proj.id if proj else None), team.name, None


@router.put("/events/{event_id}/certificate-template")
async def put_template(event_id: str, body: TemplateIn, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    img = (body.image or "").strip()
    if not img.startswith("data:image/"):
        err(422, "validation_error", "Template must be an image data: URL")
    if len(img) > MAX_TEMPLATE_CHARS:
        err(422, "validation_error", "Template image too large (2MB cap)")
    res = await db.execute(select(CertificateTemplate).where(
        CertificateTemplate.event_id == e.id))
    tpl = res.scalars().first()
    if tpl:
        tpl.image = img
        tpl.updated_by = user.id
    else:
        tpl = CertificateTemplate(event_id=e.id, image=img, updated_by=user.id)
        db.add(tpl)
    await db.commit()
    await record(user, "event.certificate_template_updated", target_type="event",
                 target_id=e.id, event_id=e.id, detail={}, request=request)
    return {"ok": True}


@router.get("/events/{event_id}/certificate-template")
async def get_template(event_id: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_roles("ORGANIZER", "ADMIN"))):
    e = await managed_event(db, user, event_id)
    res = await db.execute(select(CertificateTemplate).where(
        CertificateTemplate.event_id == e.id))
    tpl = res.scalars().first()
    if not tpl:
        err(404, "not_found", "No certificate template uploaded for this event")
    return {"image": tpl.image}


def _cert_out(cert, user, event, template_image):
    f = lambda x: x.isoformat() if x else None
    return {"id": cert.id, "event_id": event.id, "event_name": event.name,
            "kind": cert.kind.value if hasattr(cert.kind, "value") else str(cert.kind),
            "display_name": user.display_name, "email": user.email,
            "team_name": cert.team_name, "project_id": cert.project_id,
            "rank": cert.rank, "code": cert.code, "issued_at": f(cert.issued_at),
            "template_image": template_image}


@router.get("/events/{event_id}/certificate")
async def my_certificate(event_id: str, request: Request,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(current_user)):
    """Issue (first view) or return the caller's certificate. Requires
    registration on the event and declared results; otherwise 404."""
    e = None
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role in ("ORGANIZER", "ADMIN"):
        try:
            e = await managed_event(db, user, event_id)
        except Exception:
            e = None
    if e is None:
        res = await db.execute(select(Event).where(Event.id == event_id))
        e = res.scalars().first()
        if not e:
            err(404, "not_found", "Event not found")
    res = await db.execute(select(EventParticipant).where(
        EventParticipant.event_id == e.id, EventParticipant.user_id == user.id))
    if not res.scalars().first():
        err(404, "not_found", "No certificate: you are not registered for this event")
    run = await _declared_run(db, e.id)
    if not run:
        err(404, "not_found", "Results are not declared yet — certificates unlock after calculation")
    res = await db.execute(select(Certificate).where(
        Certificate.event_id == e.id, Certificate.user_id == user.id))
    cert = res.scalars().first()
    if cert is None:
        winner_pid = await _winner_project_id(db, run)
        my_pid, team_name, _ = await _my_project(db, e.id, user.id)
        kind = (CertificateKind.WINNER if my_pid and winner_pid and my_pid == winner_pid
                else CertificateKind.PARTICIPATION)
        rank = 1 if kind == CertificateKind.WINNER else None
        cert = Certificate(event_id=e.id, user_id=user.id, kind=kind,
                           project_id=my_pid, team_name=team_name, rank=rank,
                           code=_code(e.id, user.id))
        db.add(cert)
        await db.commit()
        await db.refresh(cert)
        await record(user, "event.certificate_issued", target_type="event",
                     target_id=e.id, event_id=e.id,
                     detail={"kind": kind.value}, request=request)
    res = await db.execute(select(CertificateTemplate).where(
        CertificateTemplate.event_id == e.id))
    tpl = res.scalars().first()
    return _cert_out(cert, user, e, tpl.image if tpl else None)


@router.get("/certificates/mine")
async def my_certificates(db: AsyncSession = Depends(get_db),
                          user: User = Depends(current_user)):
    """Every event the caller joined, with certificate state. Kind is
    computed, never stored, until the first full view issues the row."""
    res = await db.execute(select(EventParticipant, Event).join(
        Event, Event.id == EventParticipant.event_id).where(
        EventParticipant.user_id == user.id).order_by(Event.created_at.desc()))
    out = []
    for part, e in res.all():
        run = await _declared_run(db, e.id)
        kind = None
        code = None
        if run:
            res2 = await db.execute(select(Certificate).where(
                Certificate.event_id == e.id, Certificate.user_id == user.id))
            cert = res2.scalars().first()
            if cert:
                kind = cert.kind.value if hasattr(cert.kind, "value") else str(cert.kind)
                code = cert.code
            else:
                winner_pid = await _winner_project_id(db, run)
                my_pid, _, _ = await _my_project(db, e.id, user.id)
                kind = ("WINNER" if my_pid and winner_pid and my_pid == winner_pid
                        else "PARTICIPATION")
        out.append({"event_id": e.id, "event_name": e.name,
                    "event_status": e.status.value if hasattr(e.status, "value") else str(e.status),
                    "declared": run is not None,
                    "kind": kind, "code": code})
    return {"certificates": out}
