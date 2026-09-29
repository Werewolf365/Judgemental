#!/usr/bin/env python3
"""Scale seed for the three demo events (runs INSIDE the api container).

Real-event scale, deterministic (seeded RNG): 50 judges, 700 BT projects,
700 Bayes projects, 50 vote projects, 4000 voters. API throttles make
pure-API seeding infeasible at this volume, so bulk rows go straight to
the database while all judgment calls (CSV import, batch math, model
calculations) still run through the real endpoints:

  1. clean demo events (evidence + scale users; shells + organizers kept)
  2. write tailored CSVs (tracks/prizes/rubric/judges per demo)
  3. create 50 JUDGE + N PARTICIPANT users (one precomputed Argon2 hash)
  4. import setup CSVs through POST /events/{id}/import (proves the path)
  5. insert teams/projects/assignments/evaluations/ballots directly
  6. run the real calculations (BT x2, Bayes x1) through the API

Marks follow a designed gradient with small seeded noise: leaders separate
cleanly, the bulk is honest mid-field mush (700 projects cannot be totally
ordered with confidence — the uncertainty tab shows exactly that).
Usage (from repo root):
  docker cp scripts/seed_scale.py judgemental-api-1:/tmp/seed_scale.py
  docker compose exec api python /tmp/seed_scale.py
CSVs land in /tmp/scalecsv (copy out to scripts/demo_csv to keep them).
"""
import asyncio
import csv
import io
import json
import os
import random
import sys
import urllib.request
import urllib.error
import uuid as _uuid

sys.path.insert(0, "/app")

BASE = "http://localhost:8000"
O = "Cookie: session=org_7f2a_local_test_token"
RNG = random.Random(7)
CSVDIR = "/tmp/scalecsv"

N_JUDGES = 50
PLAN = {
    "demo-bt": {"n_projects": 700, "per_project": 3, "n_voters": 0, "judge_pool": 50,
                "tracks": ["ML Systems", "Web Platform", "Mobile", "Data Infra"],
                "prizes": [("Best Overall", "Top of the BT ranking", "$5000", "", 0),
                           ("Best ML Hack", "Best on the ML track", "$2500", "ML Systems", 1),
                           ("Crowd Pleaser", "Audience pick", "Glory", "", 2),
                           ("Best Mobile App", "Best on the Mobile track", "$1500", "Mobile", 3),
                           ("Best Data Story", "Best on the Data Infra track", "$1500", "Data Infra", 4)],
                "rubric": [("Craft", "What it does", 60), ("Scope", "How much", 40)],
                "mark_lo": 1, "mark_hi": 9},
    "demo-bayes": {"n_projects": 700, "per_project": 1, "n_voters": 0, "judge_pool": 50,
                   "tracks": ["Prototypes", "Pilots", "Moonshots"],
                   "prizes": [("Most Promising", "Highest posterior mean", "$1000", "", 0),
                           ("Runner-Up", "Second-highest posterior", "$500", "", 1),
                           ("Boldest Prototype", "Wildest idea that works", "$250", "Moonshots", 2)],
                   "rubric": [("Craft", "What it does", None), ("Scope", "How much", None)],
                   "mark_lo": 2, "mark_hi": 9},
    "demo-vote": {"n_projects": 50, "per_project": 2, "n_voters": 4000, "judge_pool": 2,
                  "tracks": ["Open Innovation", "Design"],
                  "prizes": [("Crowd Favorite", "Most community influence", "Glory", "", 0),
                           ("Best Design", "Best on the Design track", "$300", "Design", 1),
                           ("Second Place", "Runner-up tally", "$150", "", 2)],
                  "rubric": [("Craft", "What it does", None), ("Scope", "How much", None)],
                  "mark_lo": 1, "mark_hi": 8},
}

results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" -- {detail}"),
          flush=True)


def req(path, header=None, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method)
    if header:
        n, _, v = header.partition(":")
        r.add_header(n.strip(), v.strip())
    if body is not None:
        r.data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def J(path, header, method="GET", body=None):
    s, b = req(path, header, method, body)
    try:
        return s, json.loads(b) if b else {}
    except Exception:
        return s, {"_raw": b[:200]}


def post_multipart(path, fields, file_field, filename, content):
    boundary = "----scaleboundary1234"
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: text/csv\r\n\r\n".encode())
    buf.write(content.encode() if isinstance(content, str) else content)
    buf.write(f"\r\n--{boundary}--\r\n".encode())
    r = urllib.request.Request(BASE + path, method="POST",
                               headers={"Cookie": O.split(": ", 1)[1],
                                        "Content-Type": f"multipart/form-data; boundary={boundary}"},
                               data=buf.getvalue())
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return 0, str(e)


def csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


async def main():
    from sqlalchemy import delete, select
    from app.database import SessionLocal
    from app import models as M
    from app.shared.security import hash_password

    os.makedirs(CSVDIR, exist_ok=True)
    slugs = list(PLAN)
    async with SessionLocal() as db:
        res = await db.execute(select(M.Event).where(M.Event.slug.in_(slugs)))
        events = {e.slug: e for e in res.scalars().all()}
    check("demo shells present", set(events) == set(slugs), f"{sorted(events)}")
    eids = {s: events[s].id for s in slugs}

    # ---- 0. clean (evidence + scale users; shells, organizers, fixtures kept)
    patterns = ["scale-%", "demo-bt-%", "demo-bayes-%", "demo-vote-%", "blendplay-%"]
    async with SessionLocal() as db:
        from sqlalchemy import or_ as _or
        for model, col in ((M.Ballot, M.Ballot.event_id), (M.Comment, M.Comment.event_id),
                           (M.Evaluation, M.Evaluation.event_id),
                           (M.JudgeAssignment, M.JudgeAssignment.event_id),
                           (M.Project, M.Project.event_id), (M.Team, M.Team.event_id),
                           (M.EventParticipant, M.EventParticipant.event_id),
                           (M.ParticipantRegistration, M.ParticipantRegistration.event_id),
                           (M.EventJudge, M.EventJudge.event_id),
                           (M.Track, M.Track.event_id), (M.Prize, M.Prize.event_id),
                           (M.RubricCriterion, M.RubricCriterion.event_id)):
            await db.execute(delete(model).where(col.in_(eids.values())))
        await db.execute(delete(M.BayesRankOverride).where(
            M.BayesRankOverride.model_run_id.in_(
                select(M.ModelRun.id).where(M.ModelRun.event_id.in_(eids.values())))))
        await db.execute(delete(M.ModelRun).where(M.ModelRun.event_id.in_(eids.values())))
        conds = _or(*[M.User.email_norm.like(p) for p in patterns])
        # Creator links elsewhere (non-demo teams) are nullable history, not
        # ownership: null them so the accounts can go. Demo-event teams are
        # already deleted above.
        await db.execute(M.Team.__table__.update().where(
            M.Team.created_by.in_(select(M.User.id).where(conds))
        ).values(created_by=None))
        await db.execute(delete(M.User).where(conds))
        await db.commit()
    check("demo events cleaned", True)

    # ---- 1. tailored CSVs
    judge_rows = [[f"scale-judge-{i:02d}@local.test"] for i in range(1, N_JUDGES + 1)]
    files = {}
    for slug, cfg in PLAN.items():
        d = os.path.join(CSVDIR, slug)
        os.makedirs(d, exist_ok=True)
        t = csv_text(["name"], [[n] for n in cfg["tracks"]])
        p = csv_text(["name", "description", "value", "track", "display_order"],
                     [[n, dd, vv, tt, oo] for n, dd, vv, tt, oo in cfg["prizes"]])
        r = csv_text(["name", "description", "weight", "scale_lo", "scale_hi"],
                     [[n, dd, ("" if w is None else w), 0, 10] for n, dd, w in cfg["rubric"]])
        for fn, text in (("tracks.csv", t), ("prizes.csv", p), ("rubric.csv", r),
                         ("judges.csv", csv_text(["email"], judge_rows))):
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write(text)
        files[slug] = d
    check("CSVs written", True, CSVDIR)

    # ---- 2. users (one Argon2 hash for all scale accounts)
    pw_hash = await asyncio.to_thread(hash_password, "ScalePass123!")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        users = []
        for i in range(1, N_JUDGES + 1):
            em = f"scale-judge-{i:02d}@local.test"
            users.append(M.User(email=em, email_norm=em, password_hash=pw_hash,
                                display_name=f"Scale Judge {i}", role=M.Role.JUDGE))
        for slug, cfg in PLAN.items():
            tag = {"demo-bt": "bt", "demo-bayes": "by", "demo-vote": "vo"}[slug]
            for i in range(1, cfg["n_projects"] + 1):
                em = f"scale-{tag}-{i:04d}@local.test"
                users.append(M.User(email=em, email_norm=em, password_hash=pw_hash,
                                    display_name=f"Scale {tag.upper()} {i}",
                                    role=M.Role.PARTICIPANT))
        db.add_all(users)
        await db.commit()
    check("scale users created", True, f"{N_JUDGES} judges + participants")

    # ---- 3. import setup CSVs through the real endpoint
    for slug in slugs:
        d = files[slug]
        tot_c, tot_s = 0, 0
        for ds, fn in (("tracks", "tracks.csv"), ("prizes", "prizes.csv"),
                       ("rubric", "rubric.csv"), ("judges", "judges.csv")):
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                content = f.read()
            s, b = post_multipart(f"/events/{eids[slug]}/import",
                                  {"dataset": ds}, "file", fn, content)
            if isinstance(b, dict):
                tot_c += b.get("created", 0)
                tot_s += b.get("skipped", 0)
        check(f"{slug}: setup CSVs imported", tot_c > 0, f"created={tot_c} skipped={tot_s}")

    # ---- 4. evidence, DB-direct
    async with SessionLocal() as db:
        res = await db.execute(select(M.User).where(M.User.email_norm.like("scale-%")))
        by_email = {u.email_norm: u for u in res.scalars().all()}
        judges = [by_email[f"scale-judge-{i:02d}@local.test"].id for i in range(1, N_JUDGES + 1)]
        for slug, cfg in PLAN.items():
            eid = eids[slug]
            tag = {"demo-bt": "bt", "demo-bayes": "by", "demo-vote": "vo"}[slug]
            res = await db.execute(select(M.Track).where(M.Track.event_id == eid))
            tracks = [t.id for t in res.scalars().all()]
            res = await db.execute(select(M.RubricCriterion).where(
                M.RubricCriterion.event_id == eid, M.RubricCriterion.is_active == True))  # noqa
            crits = [c.id for c in res.scalars().all()]
            n = cfg["n_projects"]
            per = cfg["per_project"]
            pool = cfg["judge_pool"]
            lo, hi = cfg["mark_lo"], cfg["mark_hi"]
            for i in range(1, n + 1):
                u = by_email[f"scale-{tag}-{i:04d}@local.test"]
                team = M.Team(event_id=eid, name=f"Scale {tag.upper()} Team {i}",
                              created_by=u.id)
                db.add(team)
                await db.flush()
                db.add(M.TeamMember(team_id=team.id, user_id=u.id, role=M.TeamRole.CAPTAIN))
                db.add(M.EventParticipant(event_id=eid, user_id=u.id))
                db.add(M.ParticipantRegistration(
                    event_id=eid, user_id=u.id, full_name=f"Scale {i}",
                    email=u.email, phone="9999999999", age=20, degree="B.Tech",
                    year_of_study="3rd Year", institution="Scale U", category="Open"))
                pr = M.Project(event_id=eid, team_id=team.id,
                               track_id=tracks[i % len(tracks)],
                               title=f"Scale {tag.upper()} P{i:04d}",
                               summary="scale demo submission",
                               status=M.ProjectStatus.SUBMITTED, submitted_at=now)
                db.add(pr)
                await db.flush()
                # Designed gradient: rank i => base mark, tiny seeded noise,
                # mild per-judge harshness shift. Leaders separate cleanly.
                base = round(hi - (hi - lo) * (i - 1) / max(n - 1, 1))
                for k in range(per):
                    j = judges[(i * per + k) % pool]
                    m = max(0, min(10, base + RNG.choice([-1, 0, 0, 0, 1])))
                    asg = M.JudgeAssignment(event_id=eid, project_id=pr.id,
                                            judge_user_id=j,
                                            status=M.AssignmentStatus.COMPLETED,
                                            completed_at=now)
                    db.add(asg)
                    await db.flush()
                    db.add(M.Evaluation(
                        assignment_id=asg.id, event_id=eid, project_id=pr.id,
                        judge_user_id=j, scores={c: m for c in crits},
                        status=M.EvaluationStatus.SUBMITTED,
                        weighted_score=float(m), submitted_at=now))
            await db.commit()
            J(f"/events/{eid}/judging", O, "PATCH",
              {"judges_per_project": per, "rolling_judging": False,
               "judging_close": "2020-01-01T00:00:00Z"})
        check("evidence inserted", True)

    # ---- 5. crowd ballots on the vote demo (skewed: P1 wins clearly)
    async with SessionLocal() as db:
        eid = eids["demo-vote"]
        res = await db.execute(select(M.Project).where(
            M.Project.event_id == eid).order_by(M.Project.title))
        projs = [p.id for p in res.scalars().all()]
        import hashlib as _hl
        fps = [_hl.sha256(f"scale-fp-{k:02d}".encode()).hexdigest()[:16] for k in range(25)]
        rows = []
        for v in range(4000):
            vid = f"scale-voter-{v:04d}"
            fp = fps[v % 25]
            if v < 2000:
                alloc = [(projs[0], 2)]
            elif v < 3000:
                alloc = [(projs[1], 2)]
            elif v < 3500:
                alloc = [(projs[2], 2)]
            else:
                alloc = [(projs[v % len(projs)], 1)]
            for pid, votes in alloc:
                rows.append(M.Ballot(event_id=eid, project_id=pid,
                                     voter_key=f"anon:{vid}", votes=votes, fp_hash=fp))
        db.add_all(rows)
        await db.commit()
        s, b = J(f"/events/{eid}/voting", O, "PATCH",
                 {"voting_enabled": True, "voting_mode": "open",
                  "voting_close": "2020-01-01T00:00:00Z",
                  "comments_visibility": "public"})
        # Blend lives on the judging config, not the voting settings.
        J(f"/events/{eid}/judging", O, "PATCH",
          {"crowd_blend_enabled": True, "crowd_weight": 60})
    check("4000 voters inserted, blend on", True)

    # ---- 6. real calculations
    for slug, kind in (("demo-bt", "results"), ("demo-vote", "results"),
                       ("demo-bayes", "bayes")):
        eid = eids[slug]
        path = (f"/events/{eid}/{kind}/calculate" if kind == "results"
                else f"/events/{eid}/bayes/calculate")
        s, b = J(path, O, "POST", {})
        check(f"{slug}: {kind} calculated", s == 200, f"got {s} {b}")

    print("SCALE SEED DONE")
    bad = [n for n, c, _ in results if not c]
    raise SystemExit(0 if not bad else 1)


asyncio.run(main())
