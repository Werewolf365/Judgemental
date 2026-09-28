"""Idempotent fixture importer. Reads ../fixtures.json (or FIXTURE_PATH)."""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from app.database import SessionLocal, engine
from app.models import (Base, User, Role, Session as Sess, Event, EventStatus, EventOrganizer,
    Track, Team, TeamMember, TeamRole, Project, ProjectStatus, Judge, JudgeTrack, Score)
from app.shared.security import hash_password, sha256_hex, utcnow

FIXTURE = os.getenv("FIXTURE_PATH", "/fixtures/fixtures.json")
if not os.path.exists(FIXTURE):
    for cand in ("fixtures.json", "../fixtures.json", "/app/fixtures.json", "C:/Users/Vicky/Desktop/dogfood_gpt/fixtures.json"):
        if os.path.exists(cand):
            FIXTURE = cand
            break

DEV_PASSWORD = os.getenv("DEV_PASSWORD", "Local123!")
SEED_DEMO = os.getenv("SEED_DEMO_ACCOUNTS", "1") == "1"

# Fixed local-only session tokens so .dogfood.toml is stable
TEST_TOKENS = {
    "organizer@local.test": "org_7f2a_local_test_token",
    "admin@local.test": "adm_9c1b_local_test_token",
    "participant@local.test": "prt_2e88_local_test_token",
    "judge@local.test": "jdg_4d29_local_test_token",
}

def parse_dt(v):
    if not v:
        return None
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))

async def get_or_create_user(db, email, display_name, role: Role, enforce_role: bool = False):
    norm = email.lower()
    res = await db.execute(select(User).where(User.email_norm == norm))
    u = res.scalar_one_or_none()
    if u:
        # Demo accounts are re-asserted on every boot so a manual promotion (or
        # a half-finished test run) can never leave the demo in a wrong state.
        if enforce_role and u.role != role:
            u.role = role
        return u, False
    u = User(email=email, email_norm=norm, password_hash=hash_password(DEV_PASSWORD),
             display_name=display_name, role=role)
    db.add(u)
    await db.flush()
    return u, True

async def ensure_session(db, user: User, raw: str):
    res = await db.execute(select(Sess).where(Sess.token_hash == sha256_hex(raw)))
    if res.scalar_one_or_none():
        return
    db.add(Sess(user_id=user.id, token_hash=sha256_hex(raw),
                expires_at=utcnow() + timedelta(days=365), user_agent="seed"))

async def ensure_event_organizer(db, event, user) -> None:
    """The event creator is always an organizer of their own event."""
    if not event.created_by:
        event.created_by = user.id
    res = await db.execute(select(EventOrganizer).where(
        EventOrganizer.event_id == event.id, EventOrganizer.user_id == user.id))
    if not res.scalar_one_or_none():
        db.add(EventOrganizer(event_id=event.id, user_id=user.id, assigned_by=user.id))

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    with open(FIXTURE, encoding="utf-8") as f:
        fx = json.load(f)
    async with SessionLocal() as db:
        # Demo accounts first: the organizer is needed to own the seeded event.
        org = adm = prt = None
        if SEED_DEMO:
            org, _ = await get_or_create_user(db, "organizer@local.test", "Organizer", Role.ORGANIZER, enforce_role=True)
            adm, _ = await get_or_create_user(db, "admin@local.test", "Admin", Role.ADMIN, enforce_role=True)
            prt, _ = await get_or_create_user(db, "participant@local.test", "Participant", Role.PARTICIPANT, enforce_role=True)
            await get_or_create_user(db, "judge@local.test", "Judge", Role.JUDGE, enforce_role=True)
        # Event
        ev = fx.get("event", {})
        slug = ev.get("name", "Sample Hack 2026").lower().replace(" ", "-") + "-2026"
        slug = "sample-hack-2026"
        res = await db.execute(select(Event).where(Event.id == ev.get("id", "evt_01")))
        e = res.scalar_one_or_none()
        if not e:
            e = Event(id=ev.get("id", "evt_01"), slug=slug, name=ev.get("name", "Sample Hack 2026"),
                      description="Seeded from fixtures.json", status=EventStatus.PUBLISHED,
                      submissions_close=parse_dt(ev.get("submissions_close")))
            db.add(e)
            await db.flush()
        else:
            e.status = EventStatus.PUBLISHED
            e.submissions_close = parse_dt(ev.get("submissions_close"))
            e.slug = slug
        # The seeded event predates event_organizers, so claim it for the demo
        # organizer (and admin) instead of leaving it ownerless.
        if org:
            await ensure_event_organizer(db, e, org)
        if adm:
            res = await db.execute(select(EventOrganizer).where(
                EventOrganizer.event_id == e.id, EventOrganizer.user_id == adm.id))
            if not res.scalar_one_or_none():
                db.add(EventOrganizer(event_id=e.id, user_id=adm.id, assigned_by=org.id if org else None))
        # Tracks
        for t in fx.get("tracks", []):
            tr = await db.get(Track, t["id"])
            if not tr:
                db.add(Track(id=t["id"], event_id=e.id, name=t["name"], is_active=True))
            else:
                tr.name = t["name"]
                tr.event_id = e.id
        await db.flush()
        # Users from team members
        emails = set()
        for tm in fx.get("teams", []):
            for m in tm.get("members", []):
                emails.add(m)
        for em in sorted(emails):
            await get_or_create_user(db, em, em.split("@")[0], Role.PARTICIPANT)
        # Judges -> users (role JUDGE) + judges table
        judge_users = {}
        for j in fx.get("judges", []):
            u, _ = await get_or_create_user(db, j["email"], j["name"], Role.JUDGE)
            judge_users[j["id"]] = u
            jw = await db.get(Judge, j["id"])
            if not jw:
                db.add(Judge(id=j["id"], name=j["name"], email=j["email"]))
            for trk in j.get("tracks", []):
                res = await db.execute(select(JudgeTrack).where(JudgeTrack.judge_id == j["id"], JudgeTrack.track_id == trk))
                if not res.first():
                    db.add(JudgeTrack(judge_id=j["id"], track_id=trk))
        await db.flush()
        # Teams + members
        for tm in fx.get("teams", []):
            t = await db.get(Team, tm["id"])
            if not t:
                # creator = first member user
                res = await db.execute(select(User).where(User.email_norm == tm["members"][0].lower())) if tm.get("members") else None
                creator = res.scalar_one_or_none().id if res is not None else None
                t = Team(id=tm["id"], event_id=e.id, name=tm["name"], created_by=creator)
                db.add(t)
                await db.flush()
            for i, em in enumerate(tm.get("members", [])):
                res = await db.execute(select(User).where(User.email_norm == em.lower()))
                u = res.scalar_one_or_none()
                if not u:
                    continue
                res2 = await db.execute(select(TeamMember).where(TeamMember.team_id == t.id, TeamMember.user_id == u.id))
                if not res2.scalar_one_or_none():
                    db.add(TeamMember(team_id=t.id, user_id=u.id, role=TeamRole.CAPTAIN if i == 0 else TeamRole.MEMBER))
                from app.models import EventParticipant as EP
                res3 = await db.execute(select(EP).where(EP.event_id == e.id, EP.user_id == u.id))
                if not res3.scalar_one_or_none():
                    db.add(EP(event_id=e.id, user_id=u.id))
        await db.flush()
        # Projects
        for p in fx.get("projects", []):
            pr = await db.get(Project, p["id"])
            if not pr:
                db.add(Project(id=p["id"], event_id=e.id, team_id=p["team"], track_id=p["track"],
                               title=p["title"], summary=p.get("summary", ""), repo_url=p.get("repo_url"),
                               status=ProjectStatus.SUBMITTED, submitted_at=parse_dt(p.get("submitted_at"))))
            else:
                pr.status = ProjectStatus.SUBMITTED
                pr.submitted_at = parse_dt(p.get("submitted_at"))
                pr.title = p["title"]
        await db.flush()
        # Scores (no T2 logic, just preserve)
        for s in fx.get("scores", []):
            res = await db.execute(select(Score).where(Score.judge_id == s["judge"], Score.project_id == s["project"]))
            if not res.scalar_one_or_none():
                db.add(Score(judge_id=s["judge"], project_id=s["project"], criteria=s.get("criteria", {}), comment=s.get("comment", "")))
        # Demo account sessions
        if SEED_DEMO:
            for em, tok in TEST_TOKENS.items():
                res = await db.execute(select(User).where(User.email_norm == em))
                u = res.scalar_one_or_none()
                if u:
                    await ensure_session(db, u, tok)
            # judge_a/b sessions for checker
            judges = fx.get("judges", [])[:2]
            for idx, key in enumerate(("judge_a", "judge_b")):
                if idx < len(judges):
                    res = await db.execute(select(User).where(User.email_norm == judges[idx]["email"].lower()))
                    u = res.scalar_one_or_none()
                    if u:
                        await ensure_session(db, u, f"jdg_{key}_91bc_local_token")
        await db.commit()
        # counts
        print(f"seeded from {FIXTURE}")
        print("test logins:")
        print("  organizer    Cookie: session=org_7f2a_local_test_token")
        print("  participant  Cookie: session=prt_2e88_local_test_token")
        print("  judge_a      Cookie: session=jdg_judge_a_91bc_local_token")
        print("  judge_b      Cookie: session=jdg_judge_b_91bc_local_token")

if __name__ == "__main__":
    asyncio.run(main())
