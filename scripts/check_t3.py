#!/usr/bin/env python3
"""Internal T3 verification suite (not the official checker; run.py is).

Covers community voting end to end on a fresh-per-run draft probe event:
settings matrix, all three ballot modes, quadratic budgets, own-team block,
hidden-until-close results, tally order, comments visibility + moderation,
rate limits, duplicate signals, organizer audit. Prints PASS/FAIL.

Rerun-safe via per-run slugs. Leaves its probe event + two probe users
behind (invisible drafts, same convention as check_t1/check_t2 probes).
"""
import http.cookiejar
import json
import os
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
RUN = f"{int(time.time()) % 1000000:x}{os.getpid() % 4096:03x}"
O = "Cookie: session=org_7f2a_local_test_token"
P = "Cookie: session=prt_2e88_local_test_token"


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


def mkuser(email):
    s, _ = J("/auth/register", None, "POST",
             {"email": email, "password": "ProbePass123", "display_name": email})
    if s != 200 and s != 409:
        return None
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


REG = {"fullName": "T3", "email": "t3@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "T3 U", "category": "Open Innovation"}

# ---- setup: draft event, track, team, submitted project ----
s, b = J("/events", O, "POST", {"name": "T3 Probe", "slug": f"t3-probe-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV = b["event"]["id"] if s == 200 else None
check("probe event created", EV is not None, f"got {s}")
s, b = J(f"/events/{EV}/tracks", O, "POST", {"name": "T"})
TRK = b["track"]["id"] if s == 200 else None
# Drafts are staff-only across voting: anon box on a draft is a 404.
s, b = J(f"/public/events/{EV}/ballot", None)
check("draft ballot hidden from anon (404)", s == 404, f"got {s}")
s, b = J(f"/events/{EV}/publish", O, "POST", {})
check("probe event published", s == 200, f"got {s}")
U2 = mkuser(f"t3u2-{RUN}@local.test")
check("second user ready", bool(U2))
J(f"/events/{EV}/join", P, "POST", dict(REG, email="participant@local.test"))
s, b = J(f"/events/{EV}/teams", P, "POST", {"name": f"T3 Team {RUN}"})
TM = b["team"]["id"] if s == 200 else None
J(f"/events/{EV}/join", U2, "POST", dict(REG, email=f"t3u2-{RUN}@local.test"))
s, b = J(f"/events/{EV}/teams", U2, "POST", {"name": f"T3 Team2 {RUN}"})
TM2 = b["team"]["id"] if s == 200 else None
s, b = J("/submissions", P, "POST", {"team_id": TM, "event_id": EV,
                                     "track_id": TRK, "title": "T3 P1",
                                     "summary": "s"})
PID = b["project"]["id"] if s == 200 else None
s, b = J("/submissions", U2, "POST", {"team_id": TM2, "event_id": EV,
                                      "track_id": TRK, "title": "T3 P2",
                                      "summary": "s"})
PID2 = b["project"]["id"] if s == 200 else None
check("two submitted projects on two teams",
      all([PID, PID2]) and J(f"/submissions/{PID}/submit", P, "POST", {})[0] == 200
      and J(f"/submissions/{PID2}/submit", U2, "POST", {})[0] == 200, f"{PID} {PID2}")

# ---- settings matrix ----
s, b = J(f"/events/{EV}/voting", O)
check("voting off by default", s == 200 and b["config"]["voting_enabled"] is False, f"got {s}")
s, b = J(f"/public/events/{EV}/ballot", None)
check("box closed when disabled", s == 200 and b["open"] is False, f"got {s}")
s, b = J(f"/events/{EV}/voting", O, "PATCH", {"voting_mode": "smoke-signals"})
check("bad mode rejected (422)", s == 422, f"got {s}")
s, b = J(f"/events/{EV}/voting", P, "PATCH", {"voting_enabled": True})
check("settings organizer-only (403)", s == 403, f"got {s}")
s, b = J(f"/events/{EV}/voting", O, "PATCH", {"voting_enabled": True, "voting_mode": "email",
                                              "voting_close": "2030-06-01T00:00:00Z",
                                              "comments_visibility": "team"})
check("settings saved", s == 200 and b["config"]["voting_mode"] == "email", f"got {s} {b}")

# ---- results hidden before close ----
s, b = J(f"/public/events/{EV}/votes/results", None)
check("results hidden before close (403)", s == 403, f"got {s} {b}")

# ---- email mode voting + quadratic budget ----
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 3})
check("email required in email mode (422)", s == 422, f"got {s}")
s, b = J(f"/public/events/{EV}/ballot", P, "POST",
         {"project_id": PID, "votes": 3, "email": "voter@local.test"})
check("own team cannot vote own project (403)", s == 403, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 3, "email": "voter@local.test"})
check("3 of 10 votes used", s == 200 and b["spent"] == 3 and b["remaining"] == 7,
      f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 10, "email": "voter@local.test"})
check("10 votes use the whole budget", s == 200 and b["spent"] == 10, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID2, "votes": 1, "email": "voter@local.test"})
check("over-budget second cell refused (422)", s == 422, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 0, "email": "voter@local.test"})
check("retract frees budget", s == 200 and b["remaining"] == 10, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID2, "votes": 1, "email": "voter@local.test"})
check("1 vote fits after retract (cost 1)", s == 200 and b["spent"] == 1, f"got {s} {b}")

# ---- auth mode: login required, box personalizes ----
s, b = J(f"/events/{EV}/voting", O, "PATCH", {"voting_mode": "auth"})
check("mode switched to auth", s == 200, f"got {s}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 2, "email": "voter@local.test"})
check("auth mode refuses anonymous (401)", s == 401, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot", U2, "POST",
         {"project_id": PID, "votes": 2})
check("logged-in user votes without email", s == 200 and b["spent"] == 2, f"got {s} {b}")

# ---- open mode: uuid voter id, garbage refused ----
s, b = J(f"/events/{EV}/voting", O, "PATCH", {"voting_mode": "open"})
VID = "12345678-1234-4234-8234-123456789012"
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 1, "voter_id": "not-a-uuid"})
check("garbage voter id refused (422)", s == 422, f"got {s}")
s, b = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 1, "voter_id": VID})
check("uuid voter id accepted", s == 200, f"got {s} {b}")
s, b = J(f"/public/events/{EV}/ballot?voter_id={VID}", None)
check("box echoes my allocation", s == 200 and b["my_votes"].get(PID) == 1, f"got {s} {b}")

# ---- comments: team-only visibility + moderation ----
s, b = J(f"/public/projects/{PID}/comments", None)
check("team comments hidden from anon (403)", s == 403, f"got {s}")
s, b = J(f"/public/projects/{PID}/comments", P, "POST", {"body": "Great build!"})
check("member comments (200)", s == 200, f"got {s} {b}")
CID = b["comment"]["id"] if s == 200 else None
s, b = J(f"/public/projects/{PID}/comments", U2)
check("non-member refused thread (403)", s == 403, f"got {s}")
s, b = J(f"/comments/{CID}", P, "PATCH", {"is_hidden": True})
check("member cannot moderate (403)", s == 403, f"got {s}")
s, b = J(f"/comments/{CID}", O, "PATCH", {"is_hidden": True})
check("organizer hides comment", s == 200, f"got {s}")
s, b = J(f"/public/projects/{PID}/comments", P)
check("hidden comment gone for member", s == 200 and b["comments"] == [], f"got {s} {b}")

# ---- rate limits trip ----
codes = {}
for i in range(45):
    s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
             {"project_id": "prj_nope", "votes": 0, "email": f"rl{i}@local.test",
              "voter_id": "12345678-1234-4234-8234-123456789012"})
    codes[s] = codes.get(s, 0) + 1
check("flood trips 429", codes.get(429, 0) > 0, f"{codes}")

# ---- organizer audit readable, refusals recorded ----
s, b = J(f"/events/{EV}/audit", O)
acts = {e["action"] for e in b.get("entries", [])}
check("organizer reads event audit", s == 200 and "vote.cast" in acts, f"got {s}")
s, b = J(f"/events/{EV}/audit", P)
check("audit organizer-only (403)", s == 403, f"got {s}")

# ---- close -> public tally ----
s, b = J(f"/events/{EV}/voting", O, "PATCH", {"voting_close": "2020-01-01T00:00:00Z"})
check("window closed", s == 200, f"got {s}")
s, b = J(f"/public/events/{EV}/votes/results", None)
rnk = [(r["title"] if "title" in r else r["project_id"], r["votes"],
        round(r["influence"], 4), r["rank"]) for r in b.get("ranking", [])]
check("public tally after close", s == 200 and len(rnk) == 2, f"got {s} {rnk}")
check("tally exact: P1 ~2.414 first, P2 1.0 second",
      [r[0] for r in rnk] == ["T3 P1", "T3 P2"]
      and abs(rnk[0][2] - (2 ** 0.5 + 1)) < 1e-3 and rnk[0][3] == 1
      and abs(rnk[1][2] - 1.0) < 1e-9 and rnk[1][3] == 2, f"{rnk}")
print("INTERNAL T3 verification")
ok_all = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok_all = ok_all and c
print("ALL PASS" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
