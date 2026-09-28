#!/usr/bin/env python3
"""Fill the demo events with rich judging data (idempotent, rerun-safe).

Requires scripts/seed_demos.py first (event shells with tracks/prizes).
Creates what a human would click through in the UI, at a scale that shows
off each model rather than a toy:

  demo-bt    8 users x teams x SUBMITTED projects (both tracks), 4 judges,
             batch-assigned (2 per project), scored with a designed
             gradient + slight judge disagreement, closed, Crowd-BT
             calculated -> full ranking, reliabilities, close calls.
  demo-bayes 4 projects, 2 judges (1 evaluation each), closed, hier-Bayes
             calculated -> means, ranges, Top-K.
  demo-vote  5 submitted projects, 4 voters with varied ballots, comments,
             window closed -> public tally + thread visible.

Reruns only fill gaps: if the latest SUCCEEDED run already covers every
submitted project (or the tally shows all projects), the phase is skipped.
Judging is reopened before filling and closed + recalculated after, so
adding data never 409s. Leaves evt_01 and fixture data alone: everything
is demo-* scoped.
Usage:  python scripts/seed_demo_data.py
"""
import http.cookiejar
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
O = "Cookie: session=org_7f2a_local_test_token"
FUTURE = "2030-06-01T00:00:00Z"
PAST = "2020-01-01T00:00:00Z"
USER_PW = "DemoPass123!"
JUDGE_PW = "Local123!"

REG = {"fullName": "Demo", "email": "demo@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "Demo University", "category": "Open Innovation"}


def req(path, header=None, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method)
    if header:
        n, _, v = header.partition(":")
        r.add_header(n.strip(), v.strip())
    if body is not None:
        r.data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
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


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))


def login(email, password):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = urllib.request.Request(
        BASE + "/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        opener.open(r, timeout=30)
    except Exception:
        return None
    tok = [c.value for c in cj if c.name == "session"]
    return f"Cookie: session={tok[0]}" if tok else None


def mkuser(email, name):
    s, _ = J("/auth/register", None, "POST",
             {"email": email, "password": USER_PW, "display_name": name})
    if s != 200 and s != 409:
        return None
    return login(email, USER_PW)


def event_id(slug):
    s, b = J(f"/events/{slug}", O)
    return b["event"]["id"] if s == 200 else None


def my_team(header, ev):
    _, b = J("/teams", header)
    for t in b.get("teams", []):
        if t["event_id"] == ev:
            return t["id"]
    return None


def all_projects(ev):
    _, b = J(f"/events/{ev}/submissions", O)
    return b.get("submissions", b.get("projects", []))


def team_project(ev, team_id):
    for p in all_projects(ev):
        if p.get("team_id") == team_id:
            return p.get("id"), p.get("status")
    return None, None


def submitted_projects(ev):
    return [p for p in all_projects(ev) if p.get("status") == "SUBMITTED"]


def ensure_project(header, email, ev, track_id, team_name, title):
    """One joined team + one submitted project for this user. Idempotent."""
    team = my_team(header, ev)
    if not team:
        J(f"/events/{ev}/join", header, "POST", dict(REG, email=email,
                                                     fullName=email.split("@")[0]))
        s, b = J(f"/events/{ev}/teams", header, "POST", {"name": team_name})
        team = b["team"]["id"] if s == 200 else my_team(header, ev)
        if not team:
            return None
    pid, status = team_project(ev, team)
    if not pid:
        s, b = J("/submissions", header, "POST",
                 {"team_id": team, "event_id": ev, "track_id": track_id,
                  "title": title, "summary": f"{title} demo submission"})
        pid = b["project"]["id"] if s == 200 else None
        status = "DRAFT"
    if pid and status != "SUBMITTED":
        req(f"/submissions/{pid}/submit", header, "POST", {})
    return pid


def score_event(ev, judge_wants):
    """judge_wants: [(cookie, {title: mark_or_(mark, mark)})]. Scores every
    open assignment of this event. Returns True when all posts succeed."""
    ok = True
    for tok, want in judge_wants:
        _, mine = J("/judge/assignments", tok)
        for a in [x for x in mine.get("assignments", [])
                  if x["event_id"] == ev and x["status"] != "COMPLETED"]:
            det = J(f"/judge/assignments/{a['id']}", tok)[1]["assignment"]
            title = det["project"]["title"]
            if title not in want:
                continue
            marks = want[title]
            cids = [c["id"] for c in sorted(det["rubric"], key=lambda c: c["name"])]
            if isinstance(marks, tuple):
                scores = {cid: marks[i] for i, cid in enumerate(cids)}
            else:
                scores = {cid: marks for cid in cids}
            s, _ = J(f"/judge/assignments/{a['id']}/scores", tok, "POST",
                     {"scores": scores})
            ok = ok and s == 200
            s, _ = J(f"/judge/assignments/{a['id']}/submit", tok, "POST", {})
            ok = ok and s == 200
    return ok


def latest_succeeded(ev, kind="bt"):
    path = f"/events/{ev}/results/runs" if kind == "bt" else f"/events/{ev}/bayes/runs"
    s, b = J(path, O)
    if s != 200:
        return None
    for r in b.get("runs", []):
        if r.get("status") == "SUCCEEDED":
            return r
    return None


def up_to_date(ev, kind, want_projects):
    """A SUCCEEDED run covering every submitted project means: skip."""
    n_sub = len(submitted_projects(ev))
    if n_sub < want_projects:
        return False
    run = latest_succeeded(ev, kind)
    return bool(run) and (run.get("n_projects", run.get("projects", 0)) or 0) >= n_sub


def reopen(ev):
    J(f"/events/{ev}/judging", O, "PATCH", {"judging_close": FUTURE})


def close(ev):
    J(f"/events/{ev}/judging", O, "PATCH", {"judging_close": PAST})


BT_JUDGES = ["tomas.varga@example.org", "wei.lindqvist@example.org",
             "priya.nair@example.org", "noor.haddad@example.org"]
# Designed gradient, gaps >= 1 everywhere (mostly 2) so unit-weight BT
# keeps the strict order; Noor disagrees mildly on P4/P5 for reliability
# spread without flipping any pairwise direction.
BT_MARKS = {
    "Demo P1": (10, 10, 10, 10), "Demo P2": (8, 8, 8, 8),
    "Demo P3": (7, 7, 7, 7), "Demo P4": (5, 5, 5, 6),
    "Demo P5": (4, 4, 4, 3), "Demo P6": (3, 3, 3, 3),
    "Demo P7": (1, 1, 1, 1), "Demo P8": (0, 0, 0, 0),
}
BAYES_MARKS = {"Demo H1": (9, 8), "Demo H2": (7, 6),
               "Demo H3": (5, 5), "Demo H4": (3, 2)}

# ---------------------------------------------------------------- BT model
EV = event_id("demo-bt")
if EV:
    if up_to_date(EV, "bt", 8):
        check("demo-bt: ranking covers all 8 projects (skipped)", True)
    else:
        reopen(EV)
        _, tb = J(f"/events/{EV}/tracks", O)
        trks = tb["tracks"]
        for em in BT_JUDGES:
            J(f"/events/{EV}/judges", O, "POST", {"email": em})
        headers = []
        for i in range(1, 9):
            em = f"demo-bt-{i}@local.test"
            h = mkuser(em, f"Demo BT {i}")
            headers.append(h)
            ensure_project(h, em, EV, trks[i % len(trks)]["id"],
                           f"Demo BT Team {i}", f"Demo P{i}")
        n_sub = len(submitted_projects(EV))
        check("demo-bt: 8 submitted projects", n_sub == 8, f"got {n_sub}")
        J(f"/events/{EV}/assignments/batch", O, "POST", {})
        toks = [login(em, JUDGE_PW) for em in BT_JUDGES]
        ok = score_event(EV, [(t, {title: marks[i] for title, marks in
                                         BT_MARKS.items()})
                              for i, t in enumerate(toks)])
        check("demo-bt: 4 judges scored (16 evaluations)", ok)
        close(EV)
        s, b = J(f"/events/{EV}/results/calculate", O, "POST", {})
        check("demo-bt: calculated (8 projects, 4 judges)",
              s == 200 and b.get("projects") == 8 and b.get("judges") == 4,
              f"got {s} {b}")
        s, b = J(f"/events/{EV}/results", O)
        order = [r["title"] for r in b.get("ranking", [])]
        want = [f"Demo P{i}" for i in range(1, 9)]
        check("demo-bt: ranking P1>..>P8", order == want, f"{order}")
else:
    check("demo-bt: event present", False, "run seed_demos.py first")

# ------------------------------------------------------------- Bayes score
EV = event_id("demo-bayes")
if EV:
    if up_to_date(EV, "bayes", 4):
        check("demo-bayes: scoring covers all 4 projects (skipped)", True)
    else:
        reopen(EV)
        _, tb = J(f"/events/{EV}/tracks", O)
        trk = tb["tracks"][0]["id"]
        J(f"/events/{EV}/judges", O, "POST", {"email": BT_JUDGES[1]})
        headers = []
        for i, title in ((1, "Demo H1"), (2, "Demo H2"),
                         (3, "Demo H3"), (4, "Demo H4")):
            em = f"demo-bayes-{i}@local.test"
            h = mkuser(em, f"Demo Bayes {i}")
            headers.append(h)
            ensure_project(h, em, EV, trk, f"Demo Bayes Team {i}", title)
        J(f"/events/{EV}/assignments/batch", O, "POST", {})
        toks = [login(em, JUDGE_PW) for em in BT_JUDGES[:2]]
        ok = score_event(EV, [(t, dict(BAYES_MARKS)) for t in toks])
        check("demo-bayes: judges scored H1..H4", ok)
        close(EV)
        s, b = J(f"/events/{EV}/bayes/calculate", O, "POST", {})
        check("demo-bayes: calculated", s == 200, f"got {s} {b}")
        s, b = J(f"/events/{EV}/bayes/results", O)
        titles = [r.get("title", r.get("project_id"))
                  for r in b.get("ranking", b.get("projects", []))]
        check("demo-bayes: order H1>H2>H3>H4",
              titles == ["Demo H1", "Demo H2", "Demo H3", "Demo H4"],
              f"{titles}")
else:
    check("demo-bayes: event present", False, "run seed_demos.py first")

# --------------------------------------------------------------- Vote demo
EV = event_id("demo-vote")
if EV:
    s, b = J(f"/public/events/{EV}/votes/results", None)
    rnk = [r.get("title", r.get("project_id")) for r in b.get("ranking", [])]
    if s == 200 and rnk == ["Vote P1", "Vote P2", "Vote P3",
                            "Vote P5", "Vote P4"]:
        check("demo-vote: tally P1>P2>P3>P5>P4 (skipped)", True)
    else:
        _, tb = J(f"/events/{EV}/tracks", O)
        trks = tb["tracks"]
        # Reopen: earlier runs leave the window closed, which refuses ballots.
        J(f"/events/{EV}/voting", O, "PATCH",
          {"voting_enabled": True, "voting_mode": "open",
           "voting_close": FUTURE, "comments_visibility": "public"})
        pids = {}
        for i in range(1, 6):
            em = f"demo-vote-{i}@local.test"
            h = mkuser(em, f"Demo Vote {i}")
            pids[i] = ensure_project(h, em, EV, trks[i % len(trks)]["id"],
                                     f"Demo Vote Team {i}", f"Vote P{i}")
        check("demo-vote: 5 submitted projects", all(pids.values()), f"{pids}")
        # Retract the stray ballot an earlier revision left behind, or the
        # tally math below will not hold.
        for pid in pids.values():
            J(f"/public/events/{EV}/ballot", None, "POST",
              {"project_id": pid, "votes": 0, "email": "voter@local.test"})
        VA, VB = ("11111111-1111-4111-8111-111111111111",
                  "22222222-2222-4222-8222-222222222222")
        VC, VD = ("33333333-3333-4333-8333-333333333333",
                  "44444444-4444-4434-8444-444444444444")
        # Clear the single stale cell from an earlier revision's split
        # (same voter id, different project). Ballots upsert per voter, and
        # a bulk wipe would trip the ballot rate limit — keep this surgical.
        J(f"/public/events/{EV}/ballot", None, "POST",
          {"project_id": pids[2], "votes": 0, "voter_id": VB})
        ballots = [(VA, pids[1], 2), (VA, pids[2], 2), (VA, pids[3], 1),
                   (VB, pids[1], 2), (VB, pids[4], 1),
                   (VC, pids[5], 3),
                   (VD, pids[2], 1), (VD, pids[3], 1)]
        ok = True
        for vid, pid, votes in ballots:
            s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
                     {"project_id": pid, "votes": votes, "voter_id": vid})
            ok = ok and s == 200
        check("demo-vote: 8 ballots cast", ok)
        # A living thread on the front-runner (skip when already there).
        h1 = login("demo-vote-1@local.test", USER_PW)
        s, th = J(f"/public/projects/{pids[1]}/comments", h1)
        if s == 200 and not th.get("comments"):
            h3 = login("demo-vote-3@local.test", USER_PW)
            J(f"/public/projects/{pids[1]}/comments", h1, "POST",
              {"body": "Cleanest demo of the bunch!"})
            J(f"/public/projects/{pids[1]}/comments", h3, "POST",
              {"body": "Agree — the live tally sold me."})
        J(f"/events/{EV}/voting", O, "PATCH", {"voting_close": PAST})
        s, b = J(f"/public/events/{EV}/votes/results", None)
        rnk = [r.get("title", r.get("project_id")) for r in b.get("ranking", [])]
        check("demo-vote: public tally P1>P2>P3>P5>P4",
              s == 200 and rnk == ["Vote P1", "Vote P2", "Vote P3",
                                   "Vote P5", "Vote P4"], f"{rnk}")
else:
    check("demo-vote: event present", False, "run seed_demos.py first")

print("DEMO DATA SEED")
ok = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok = ok and c
print("ALL PASS" if ok else "FAILURES PRESENT")
raise SystemExit(0 if ok else 1)
