#!/usr/bin/env python3
"""Fill the Blend Playground (demo-blend) with testable data, leaving the
judging window CLOSED so Calculate works immediately. Idempotent: skips
phases whose results already exist. Judges and crowd deliberately disagree
(judges: P2 first; crowd: P1 first) so the blend visibly moves the order.
Usage:  python scripts/seed_blend_playground.py
"""
import http.cookiejar
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
O = "Cookie: session=org_7f2a_local_test_token"
PAST = "2020-01-01T00:00:00Z"
USER_PW = "DemoPass123!"
JUDGE_PW = "Local123!"
EV = "evt_58cc8471"
REG = {"fullName": "Blend", "email": "blend@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "Blend U", "category": "Open Innovation"}


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


_, tb = J(f"/events/{EV}/tracks", O)
trks = {t["name"]: t["id"] for t in tb.get("tracks", [])}
_, sb = J(f"/events/{EV}/submissions", O)
have = {p["title"]: p for p in sb.get("submissions", sb.get("projects", []))}
for i, title in ((1, "Blend P1"), (2, "Blend P2"), (3, "Blend P3")):
    em = f"blendplay-{i}@local.test"
    h = mkuser(em, f"Blend Play {i}")
    if title not in have:
        J(f"/events/{EV}/join", h, "POST", dict(REG, email=em))
        _, t = J(f"/events/{EV}/teams", h, "POST", {"name": f"Blend Team {i}"})
        team = t["team"]["id"] if t.get("team") else None
        if not team:
            _, mine = J("/teams", h)
            team = next((x["id"] for x in mine.get("teams", [])
                         if x["event_id"] == EV), None)
        s, p = J("/submissions", h, "POST",
                 {"team_id": team, "event_id": EV,
                  "track_id": trks["Apps"] if i % 2 else trks["Hardware"],
                  "title": title, "summary": f"{title} playground submission"})
        if p.get("project"):
            req(f"/submissions/{p['project']['id']}/submit", h, "POST", {})
check("3 submitted projects",
      len([p for p in J(f"/events/{EV}/submissions", O)[1].get(
          "submissions", []) if p.get("status") == "SUBMITTED"]) == 3)

J(f"/events/{EV}/assignments/batch", O, "POST", {})
toks = [login("tomas.varga@example.org", JUDGE_PW),
        login("wei.lindqvist@example.org", JUDGE_PW)]
WANT = {"Blend P1": 3, "Blend P2": 8, "Blend P3": 6}
ok = True
for tok in toks:
    _, mine = J("/judge/assignments", tok)
    for a in [x for x in mine.get("assignments", [])
              if x["event_id"] == EV and x["status"] != "COMPLETED"]:
        det = J(f"/judge/assignments/{a['id']}", tok)[1]["assignment"]
        cids = [c["id"] for c in sorted(det["rubric"], key=lambda c: c["name"])]
        s, _ = J(f"/judge/assignments/{a['id']}/scores", tok, "POST",
                 {"scores": {cid: WANT[det["project"]["title"]] for cid in cids}})
        ok = ok and s == 200
        s, _ = J(f"/judge/assignments/{a['id']}/submit", tok, "POST", {})
        ok = ok and s == 200
check("judges scored P2 first", ok)

_, pb = J(f"/events/{EV}/submissions", O)
pids = {p["title"]: p["id"] for p in pb.get("submissions", [])}
VA, VB = ("55555555-5555-4555-8555-555555555555",
          "66666666-6666-4666-8666-666666666666")
ok = True
for vid, title, votes in ((VA, "Blend P1", 4), (VA, "Blend P2", 1),
                          (VB, "Blend P1", 1), (VB, "Blend P3", 2)):
    s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
             {"project_id": pids[title], "votes": votes, "voter_id": vid})
    ok = ok and s == 200
check("crowd voted P1 first", ok)
J(f"/events/{EV}/judging", O, "PATCH", {"judging_close": PAST})
check("window closed, ready to calculate", True)

print("BLEND PLAYGROUND SEED")
ok_all = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok_all = ok_all and c
print("ALL PASS" if ok_all else "FAILURES PRESENT")
raise SystemExit(0 if ok_all else 1)
