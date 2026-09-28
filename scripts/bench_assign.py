#!/usr/bin/env python3
"""Assignment-engine scale benchmark. Runs INSIDE the api container
(code + DB live there; the repo root is outside the image build context):

    docker compose exec -T api python - < scripts/bench_assign.py [scenarios]

Scenarios are J:P:C triples (judges : projects : coverage per project),
defaulting to the four requested scale cases. Each scenario builds a fresh
draft event with synthetic judges/teams/projects (direct rows — the point
is the engine, not the HTTP layer), rosters the judges, times one
assign_all_pending pass, asserts the balance invariants, and deletes the
event afterwards (CASCADE wipes teams/projects/assignments; bench users
are shared across scenarios and kept). Pass --keep to inspect leftovers.

Workload notes: judge loads are event-scoped, so reusing the same bench
judges across scenarios keeps runs independent. Teams are memberless on
purpose — assignment only reads project rows; 600 throwaway participant
accounts would prove nothing.
"""
import argparse
import asyncio
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (Event, EventJudge, JudgeAssignment, Project,
                        ProjectStatus, Role, Team, Track, User)
from app.modules.judging import assign as assign_svc
from app.shared.security import hash_password

BASE_TS = datetime(2030, 1, 1, tzinfo=timezone.utc)


async def ensure_judges(db, n):
    """Shared bench judges benchj00..; idempotent across runs."""
    ids = []
    pw = hash_password("BenchPass123!")
    for i in range(n):
        em = f"benchj{i:02d}@local.test"
        res = await db.execute(select(User).where(User.email_norm == em))
        u = res.scalar_one_or_none()
        if u is None:
            u = User(id=f"bench-u{i:02d}", email=em, email_norm=em,
                     password_hash=pw, display_name=f"Bench Judge {i}",
                     role=Role.JUDGE)
            db.add(u)
            await db.flush()
        elif str(getattr(u.role, "value", u.role)) != "JUDGE":
            u.role = Role.JUDGE
        ids.append(u.id)
    await db.commit()
    return ids


async def build_event(db, tag, n_projects, judge_ids, coverage, run):
    t0 = time.perf_counter()
    org = (await db.execute(
        select(User.id).where(User.email_norm == "organizer@local.test"))).scalar()
    ev = Event(id=f"bench-{tag}-{run}", slug=f"bench-{tag}-{run}",
               name=f"Bench {tag}", status="DRAFT", created_by=org,
               judges_per_project=coverage, rolling_judging=False)
    db.add(ev)
    trk = Track(id=f"bencht-{tag}-{run}", event_id=ev.id, name="Bench Track")
    db.add(trk)
    await db.flush()
    for jid in judge_ids:
        db.add(EventJudge(event_id=ev.id, user_id=jid, assigned_by=org))
    teams, projs = [], []
    for i in range(n_projects):
        tid, pid = f"benchtm-{tag}-{i:04d}-{run}", f"benchp-{tag}-{i:04d}-{run}"
        teams.append(Team(id=tid, event_id=ev.id, name=f"Bench Team {i}",
                          created_by=org))
        projs.append(Project(
            id=pid, event_id=ev.id, team_id=tid, track_id=trk.id,
            title=f"Bench Project {i}", summary="bench",
            status=ProjectStatus.SUBMITTED,
            submitted_at=BASE_TS + timedelta(seconds=i)))
    for chunk in (teams, projs):
        for i in range(0, len(chunk), 200):
            db.add_all(chunk[i:i + 200])
            await db.flush()
    await db.commit()
    return ev.id, time.perf_counter() - t0


async def run_scenario(tag, n_judges, n_projects, coverage, run, keep):
    async with SessionLocal() as db:
        judge_ids = await ensure_judges(db, n_judges)
    async with SessionLocal() as db:
        ev_id, setup_s = await build_event(
            db, tag, n_projects, judge_ids[:n_judges], coverage, run)
    t0 = time.perf_counter()
    async with SessionLocal() as db:
        out = await assign_svc.assign_all_pending(db, ev_id)
        await db.commit()
        bal = await assign_svc.assignment_health(db, ev_id)
    assign_s = time.perf_counter() - t0
    wl, cov = bal["workload"], bal["coverage"]
    feasible = min(coverage, n_judges)
    expect_created = n_projects * feasible
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" -- {detail}"))
        ok = ok and cond

    print(f"[{tag}] judges={n_judges} projects={n_projects} coverage={coverage}")
    print(f"  setup {setup_s:.1f}s, assign+commit {assign_s:.1f}s, "
          f"created={out['assignments_created']} repairs={len(out['repairs'])}")
    print(f"  workload min/max/spread {wl['min']}/{wl['max']}/{wl['spread']}, "
          f"coverage min/max {cov['min']}/{cov['max']}, "
          f"components={bal['components']} connected={bal['connected']}, "
          f"pairwise_capacity={bal['pairwise_capacity']}")
    check("created == projects x feasible coverage",
          out["assignments_created"] == expect_created,
          f"got {out['assignments_created']}, want {expect_created}")
    check("coverage exact everywhere",
          cov["min"] == feasible and cov["max"] == feasible and not cov["under_covered"],
          f"{cov}")
    check("workload spread <= 1", wl["spread"] <= 1, f"spread={wl['spread']}")
    if coverage == 1:
        # Structural fact, not a bug: nothing is shared, so no linkage can
        # exist. The calculate gate must refuse this shape downstream.
        check("coverage-1 stays disconnected (expected, unrepairable)",
              not bal["connected"] and bal["components"] == n_judges
              and out["repairs"] == [], f"{bal['components']} components")
    else:
        check("connected by construction", bal["connected"], f"{bal['components']} components")
    if not keep:
        async with SessionLocal() as db:
            await db.execute(Event.__table__.delete().where(Event.id == ev_id))
            await db.commit()
    # Bench judges are shared across scenarios and kept (14 rows, documented).
    return ok


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="*",
                    default=["10:400:1", "10:399:2", "10:500:3", "14:600:5"],
                    help="J:P:C triples")
    ap.add_argument("--keep", action="store_true", help="leave probe events behind")
    args = ap.parse_args()
    run = f"{int(time.time()) % 1000000:x}"
    all_ok = True
    for i, spec in enumerate(args.scenarios):
        j, p, c = (int(x) for x in spec.split(":"))
        all_ok = await run_scenario(f"s{i}", j, p, c, run, args.keep) and all_ok
    print("BENCH " + ("ALL PASS" if all_ok else "FAILURES PRESENT"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
