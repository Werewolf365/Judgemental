#!/usr/bin/env python3
"""Internal T2 verification suite (not the official checker; run.py is).

Covers the full judging lifecycle on two throwaway draft events
(t2-probe-tmp, t2-probe-hist): rubrics, weights, locking, roster, balanced
assignment, rolling/batch, removal, scoring isolation, deadlines, the
connectivity gate, calculation, reproducibility, historical priors, CSV.

Like check_t1.py it leaves its draft probe events behind (invisible
publicly) rather than deleting data it cannot see. Prints PASS/FAIL.
"""
import http.cookiejar
import json
import os
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
# Fresh probe events per run: the flow needs unevaluated projects, and a
# previous run leaves everything submitted and calculated. Old probes stay
# behind as invisible drafts (same convention as check_t1's probe).
RUN = f"{int(time.time()) % 1000000:x}{os.getpid() % 4096:03x}"
O = "Cookie: session=org_7f2a_local_test_token"
A = "Cookie: session=adm_9c1b_local_test_token"
P = "Cookie: session=prt_2e88_local_test_token"
JA = "Cookie: session=jdg_judge_a_91bc_local_token"
JB = "Cookie: session=jdg_judge_b_91bc_local_token"


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


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))


def J(path, header, method="GET", body=None):
    s, b = req(path, header, method, body)
    try:
        return s, json.loads(b) if b else {}
    except Exception:
        return s, {"_raw": b[:200]}


# ---- setup: one draft event, track, team, four submitted projects ----
s, b = J("/events", O, "POST", {"name": "T2 Probe", "slug": f"t2-probe-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV = b["event"]["id"] if s == 200 else None
check("probe event created", EV is not None, f"got {s}")

s, b = J(f"/events/{EV}/tracks", O, "POST", {"name": "Probe Track"})
TRK = b["track"]["id"] if s == 200 else None

REG = {"fullName": "T2", "email": "t2@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "T2 U", "category": "Open Innovation"}


def _login(email):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = urllib.request.Request(
        BASE + "/auth/login",
        data=json.dumps({"email": email, "password": "ProbePass123"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        opener.open(r, timeout=30)
    except Exception:
        return None
    tok = [c.value for c in cj if c.name == "session"]
    return f"Cookie: session={tok[0]}" if tok else None


def mkuser(email, name):
    """Register + log in a throwaway user, returning its Cookie header.
    One submission per team (and one team per user per event) means the
    four ranked projects need four separate users. Registration is
    idempotent across runs: an existing account just logs in."""
    s, _ = J("/auth/register", None, "POST",
             {"email": email, "password": "ProbePass123", "display_name": name})
    if s != 200 and s != 409:
        return None
    return _login(email)


def join_team_project(header, email, ev, trk, team_name, title, summary="probe"):
    """Join event, create a team, draft one project. Returns project id."""
    reg = dict(REG, email=email, fullName=email.split("@")[0])
    req(f"/events/{ev}/join", header, "POST", reg)
    s, b = J(f"/events/{ev}/teams", header, "POST", {"name": team_name})
    team = b["team"]["id"] if s == 200 else None
    s, b = J("/submissions", header, "POST", {"team_id": team, "event_id": ev,
                                              "track_id": trk, "title": title,
                                              "summary": summary})
    return b["project"]["id"] if s == 200 else None


# One submission per team: four projects need four users (P + three probes).
MEMBERS = [(P, "participant@local.test")] + [
    (mkuser(f"t2probe{i}@local.test", f"T2 Probe {i}"), f"t2probe{i}@local.test")
    for i in (2, 3, 4)]
check("probe users ready", all(h for h, _ in MEMBERS), f"{MEMBERS}")
PROJS = []
OWNERS = []
for (header, email), i in zip(MEMBERS, range(1, 5)):
    PROJS.append(join_team_project(header, email, EV, TRK, f"T2 Team {i}", f"T2 P{i}"))
    OWNERS.append(header)
check("four draft projects created (one per team)", all(PROJS), f"{PROJS}")
_, mine_teams = J("/teams", P)
OWN_TEAM = next((t["id"] for t in mine_teams.get("teams", []) if t["event_id"] == EV), None)
s, b = J("/submissions", P, "POST", {"team_id": OWN_TEAM, "event_id": EV,
                                     "track_id": TRK, "title": "T2 P5",
                                     "summary": "probe"})
check("second project for the same team refused (409)", s == 409, f"got {s} {b}")

# ---- rubrics ----
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Craft", "description": "d"})
C1 = b["criterion"]["id"] if s == 200 else None
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Scope"})
C2 = b["criterion"]["id"] if s == 200 else None
check("criteria created without weights", C1 and C2, f"got {s}")
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Zero", "weight": 0})
check("zero weight rejected (422)", s == 422, f"got {s}")
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Huge", "weight": 101})
check("weight >100 rejected (422)", s == 422, f"got {s}")
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Craft", "weight": 10})
check("duplicate criterion name rejected (409)", s == 409, f"got {s}")
s, b = J(f"/rubric/{C1}", O, "PATCH", {"name": "Craft", "weight": 60, "display_order": 0})
check("criterion edited (weight set)", s == 200, f"got {s} {b}")
s, b = J(f"/rubric/{C2}", O, "PATCH", {"name": "Scope", "weight": 40, "display_order": 1})
check("second weight set (60/40 explicit)", s == 200, f"got {s}")
s, b = J(f"/events/{EV}/rubric", P, "POST", {"name": "Sneaky", "weight": 10})
check("participant cannot touch rubric (403)", s == 403, f"got {s}")

# ---- roster ----
_, me_a = J("/auth/me", JA)
_, me_b = J("/auth/me", JB)
UA, UB = me_a["user"]["id"], me_b["user"]["id"]
s, _ = J(f"/events/{EV}/judges", O, "POST", {"email": me_a["user"]["email"]})
check("judge A rostered", s == 200, f"got {s}")
s, _ = J(f"/events/{EV}/judges", O, "POST", {"email": me_b["user"]["email"]})
check("judge B rostered", s == 200, f"got {s}")
s, _ = J(f"/events/{EV}/judges", O, "POST", {"email": "participant@local.test"})
check("non-judge roster refused (422)", s == 422, f"got {s}")
s, b = J(f"/events/{EV}/judging", O, "PATCH",
         {"judges_per_project": 1, "rolling_judging": False})
check("batch mode configured (per_project=1, rolling off)", s == 200, f"got {s} {b}")

# ---- rolling OFF: submits create nothing ----
for pid, owner in zip(PROJS, OWNERS):
    req(f"/submissions/{pid}/submit", owner, "POST", {})
s, b = J(f"/events/{EV}/judges", O)
loads = {j["user_id"]: j["active_load"] for j in b["judges"]}
check("no rolling assignment while off", sum(loads.values()) == 0, f"{loads}")

# ---- batch: balanced, idempotent ----
s, b = J(f"/events/{EV}/assignments/batch", O, "POST", {})
check("batch fills all four", s == 200 and b["assignments_created"] == 4, f"got {s} {b}")
s, b = J(f"/events/{EV}/assignments/batch", O, "POST", {})
check("batch rerun creates nothing", s == 200 and b["assignments_created"] == 0, f"got {s} {b}")
s, b = J(f"/events/{EV}/judges", O)
loads = {j["user_id"]: j["active_load"] for j in b["judges"]}
check("batch balanced 2/2", sorted(loads.values()) == [2, 2], f"{loads}")

# ---- isolation: A cannot open B's assignment ----
_, ab = J("/judge/assignments", JB)
B_ASG = ab["assignments"][0]["id"]
s, _ = J(f"/judge/assignments/{B_ASG}", JA)
check("judge cannot open peer assignment (403)", s == 403, f"got {s}")

# ---- scoring: unanimous design P1=8 P2=6 P3=4 P4=2, scored by title ----
# (60/40 weights of equal marks reproduce the mark, proving normalization).
WANT = {"T2 P1": 8, "T2 P2": 6, "T2 P3": 4, "T2 P4": 2}


def _score_all(tok):
    ok = True
    _, mine = J("/judge/assignments", tok)
    mine = [a for a in mine["assignments"] if a["event_id"] == EV]
    for a in mine:
        if a["status"] == "COMPLETED":
            continue
        det = J(f"/judge/assignments/{a['id']}", tok)[1]["assignment"]
        crits = {c["name"]: c["id"] for c in det["rubric"]}
        val = WANT[det["project"]["title"]]
        s, _ = J(f"/judge/assignments/{a['id']}/scores", tok, "POST",
                 {"scores": {crits["Craft"]: val, crits["Scope"]: val}})
        ok = ok and s == 200
        s, b = J(f"/judge/assignments/{a['id']}/submit", tok, "POST", {})
        ok = ok and s == 200 and abs(b["weighted_score"] - val) < 1e-9
    return ok


ok = _score_all(JA) and _score_all(JB)
check("both judges scored and submitted (weighted == mark, 60/40 normalized)", ok)
_, aa = J("/judge/assignments", JA)
s, b = J(f"/judge/assignments/{aa['assignments'][0]['id']}/scores", JA, "POST",
         {"scores": {C1: 1, C2: 1}})
check("submitted evaluation immutable (409)", s == 409, f"got {s}")

# ---- connectivity gate: two disjoint pairs must refuse ----
s, b = J(f"/events/{EV}/judging", O, "PATCH", {"judging_close": "2020-01-01T00:00:00Z"})
s, b = J(f"/events/{EV}/results/calculate", O, "POST", {})
check("disconnected graph refused (422, names stranded)", s == 422 and "disconnected" in b.get("detail", {}).get("message", ""), f"got {s} {b}")
s, _ = J(f"/events/{EV}/results/runs", O)
check("refused calculation leaves no FAILED run", all(r["status"] != "FAILED" for r in b.get("runs", [])), f"{b}")

# ---- link the components: per_project=2, reopen, batch, submit rest ----
J(f"/events/{EV}/judging", O, "PATCH",
  {"judging_close": None, "judges_per_project": 2})
s, b = J(f"/events/{EV}/assignments/batch", O, "POST", {})
check("cross-link batch fills the other judge", s == 200 and b["assignments_created"] == 4, f"got {s} {b}")
# New assignments: A gets B's two projects and vice versa; same by-title
# scoring completes the unanimous design.
ok = _score_all(JA) and _score_all(JB)
check("cross-linked evaluations submitted (unanimous design)", ok)

# ---- deadline blocks scoring ----
J(f"/events/{EV}/judging", O, "PATCH", {"judging_close": "2020-01-01T00:00:00Z"})
_, mine = J("/judge/assignments", JA)
aid = mine["assignments"][0]["id"]
s, _ = J(f"/judge/assignments/{aid}/scores", JA, "POST", {"scores": {C1: 5, C2: 5}})
check("scoring after deadline refused (403)", s == 403, f"got {s}")

# ---- calculate: full ranking ----
s, b = J(f"/events/{EV}/results/calculate", O, "POST", {})
check("calculate succeeds (4 projects, 2 judges)", s == 200 and b["projects"] == 4 and b["judges"] == 2, f"got {s} {b}")
s, b = J(f"/events/{EV}/results", O)
order = [r["title"] for r in b.get("ranking", [])]
thetas = [r["theta"] for r in b.get("ranking", [])]
check("unanimous ranking P1>P2>P3>P4", order == ["T2 P1", "T2 P2", "T2 P3", "T2 P4"], f"{order}")
check("thetas strictly decreasing", all(a > c for a, c in zip(thetas, thetas[1:])), f"{thetas}")
check("reliabilities positive", all(j["reliability"] > 0 for j in b.get("judges", [])), f"{b}")
RUN1 = b["run"]["id"]

# ---- reproducibility: recalculate, same numbers ----
s, b = J(f"/events/{EV}/results/calculate", O, "POST", {})
RUN2 = b.get("run_id")
s, b = J(f"/events/{EV}/results", O)
thetas2 = [r["theta"] for r in b.get("ranking", [])]
check("recalculation replays identically", RUN2 != RUN1 and all(abs(a - c) < 1e-9 for a, c in zip(thetas, thetas2)), f"{thetas} vs {thetas2}")
s, b = J(f"/events/{EV}/results/runs", O)
check("version history keeps both runs", len(b.get("runs", [])) == 2, f"{b}")

# ---- CSV: one row per evaluation, full judging detail ----
s, b = req("/export.csv?event_id=" + EV, O)
rows = b.splitlines()
first = rows[0] if rows else ""
check("CSV exports 8 evaluation rows with full detail",
      s == 200 and first.startswith("project,team,team_leader")
      and "weighted_total" in first and "Craft [score]" in first
      and len(rows) == 9 and all("T2 P" in r for r in rows[1:]),
      f"got {s} {first} ({len(rows)} lines)")

# ---- historical prior on a second event ----
s, b = J("/events", O, "POST", {"name": "T2 Hist", "slug": f"t2-hist-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV2 = b["event"]["id"] if s == 200 else None
s, b = J(f"/events/{EV2}/tracks", O, "POST", {"name": "T"})
TRK2 = b["track"]["id"] if s == 200 else None
J(f"/events/{EV2}/judging", O, "PATCH", {"judges_per_project": 1, "rolling_judging": False})
# Two criteria, deliberately NO weights: the equal-weight fallback path.
J(f"/events/{EV2}/rubric", O, "POST", {"name": "Craft"})
J(f"/events/{EV2}/rubric", O, "POST", {"name": "Scope"})
C3 = {c["name"]: c["id"] for c in J(f"/events/{EV2}/rubric", O)[1]["criteria"]}
J(f"/events/{EV2}/judges", O, "POST", {"email": me_a["user"]["email"]})
# One submission per team here too: H1 and H2 live on separate teams.
H1U, H2U = MEMBERS[0], MEMBERS[1]
PIDS = []
for (header, email), title in zip((H1U, H2U), ("H1", "H2")):
    pid = join_team_project(header, email, EV2, TRK2, f"T2 Hist Team {title}", title, summary="h")
    PIDS.append(pid)
    if pid:
        req(f"/submissions/{pid}/submit", header, "POST", {})
J(f"/events/{EV2}/assignments/batch", O, "POST", {})
_, mine = J("/judge/assignments", JA)
mine = [a for a in mine["assignments"] if a["event_id"] == EV2]
got_ws = {}
for a, marks in zip(sorted(mine, key=lambda x: x["project_title"]), ((9, 3), (3, 3))):
    s, _ = J(f"/judge/assignments/{a['id']}/scores", JA, "POST",
             {"scores": {C3["Craft"]: marks[0], C3["Scope"]: marks[1]}})
    s, b = J(f"/judge/assignments/{a['id']}/submit", JA, "POST", {})
    got_ws[a["project_title"]] = b.get("weighted_score") if s == 200 else None
check("equal-weight fallback (9,3)->6.0 and (3,3)->3.0",
      got_ws == {"H1": 6.0, "H2": 3.0}, f"{got_ws}")
J(f"/events/{EV2}/judging", O, "PATCH", {"judging_close": "2020-01-01T00:00:00Z"})
s, b = J(f"/events/{EV2}/results/calculate", O, "POST", {})
s, b = J(f"/events/{EV2}/results", O)
order2 = [r["title"] for r in b.get("ranking", [])] if s == 200 else []
src = list(b.get("run", {}).get("config", {}).get("priors", {}).values())[0]["source"] if s == 200 else None
check("unweighted ranking H1 first", order2 == ["H1", "H2"], f"{order2}")
check("second event inherits HISTORICAL prior", src == "HISTORICAL", f"got {src}")

print("INTERNAL T2 verification")
ok_all = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok_all = ok_all and c
print("ALL PASS" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
