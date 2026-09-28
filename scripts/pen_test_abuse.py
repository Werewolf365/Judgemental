#!/usr/bin/env python3
"""Adversarial pen test for the T3 anti-abuse layer (stdlib only).

Attacks a throwaway probe event (slug t3-probe-pentest-<RUN>, swept by
scripts/clean_probes.py afterwards) as an outsider would: budget overruns,
bad identities, cross-event/draft/hidden targets, own-team votes, floods
with and without spoofed X-Forwarded-For, comment abuse, pre-close tally
pulls, a concurrent budget double-spend race, identical-repost spam, and
register/login floods — then verifies every refusal lands in the
organizer's (or admin's) audit view.

Note: the register flood saturates the hourly throttle, so rerunning
within the hour trips the setup itself — that cooldown IS the defense.
Minute-bucket phases self-sync; just wait it out on reruns.

Usage:  python scripts/pen_test_abuse.py
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
PW = "Pentest123!"


def req(path, header=None, method="GET", body=None, extra_headers=None):
    r = urllib.request.Request(BASE + path, method=method)
    if header:
        n, _, v = header.partition(":")
        r.add_header(n.strip(), v.strip())
    for k, v in (extra_headers or {}).items():
        r.add_header(k, v)
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


def J(path, header, method="GET", body=None, extra_headers=None):
    s, b = req(path, header, method, body, extra_headers)
    try:
        return s, json.loads(b) if b else {}
    except Exception:
        return s, {"_raw": b[:200]}


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))


def login(email):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = urllib.request.Request(
        BASE + "/auth/login",
        data=json.dumps({"email": email, "password": PW}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    opener.open(r, timeout=30)
    tok = [c.value for c in cj if c.name == "session"]
    return f"Cookie: session={tok[0]}"


# ---- setup: open-mode probe event, 2 submitted projects, member + outsider
s, b = J("/events", O, "POST", {"name": "Pentest Probe", "slug": f"t3-probe-pentest-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV = b["event"]["id"] if s == 200 else None
check("probe event created", EV is not None, f"got {s}")
s, b = J(f"/events/{EV}/tracks", O, "POST", {"name": "T"})
TRK = b["track"]["id"] if s == 200 else None
J("/auth/register", None, "POST",
  {"email": f"t3u2-pentest-{RUN}@local.test", "password": PW, "display_name": "pentest"})
MEM = login(f"t3u2-pentest-{RUN}@local.test")
J("/auth/register", None, "POST",
  {"email": f"t3u2b-pentest-{RUN}@local.test", "password": PW, "display_name": "pentestbee"})
MEM2 = login(f"t3u2b-pentest-{RUN}@local.test")
REG = {"fullName": "Pen", "email": "pen@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "Pen U", "category": "Open Innovation"}
PIDS = []
# One team AND one submission per user per event: two projects need two users.
for header, email, team_name, title in (
        (MEM, f"t3u2-pentest-{RUN}@local.test", "Pen Team 1", "Pen P1"),
        (MEM2, f"t3u2b-pentest-{RUN}@local.test", "Pen Team 2", "Pen P2")):
    J(f"/events/{EV}/join", header, "POST", dict(REG, email=email))
    _, t = J(f"/events/{EV}/teams", header, "POST", {"name": team_name})
    _, p = J("/submissions", header, "POST",
             {"team_id": t["team"]["id"], "event_id": EV, "track_id": TRK,
              "title": title, "summary": "pen"})
    if p.get("project"):
        PIDS.append(p["project"]["id"])
        J(f"/submissions/{p['project']['id']}/submit", header, "POST", {})
J(f"/events/{EV}/publish", O, "POST", {})
J(f"/events/{EV}/voting", O, "PATCH",
  {"voting_enabled": True, "voting_mode": "open",
   "voting_close": "2030-06-01T00:00:00Z", "comments_visibility": "public"})
check("two submitted projects", len(PIDS) == 2, f"{PIDS}")
PID = PIDS[0] if PIDS else "prj_nope"
VID = "12345678-1234-4234-8234-123456789012"

# Rate-limit self-sync: a previous run from this same host may have filled
# the per-minute bucket. A harmless retract tells us; on 429 we wait the
# window out (twice max) so attack results reflect the product, not our
# own past traffic.
for _ in range(3):
    s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
             {"project_id": PID, "votes": 0, "voter_id": VID})
    if s != 429:
        break
    time.sleep(65)

# ---- budget / identity attacks
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 10, "voter_id": VID})
check("10 votes fits budget", s == 200, f"got {s}")
# Two more humans behind the same IP/UA: the organizer should see one
# fingerprint shared by three voters.
for v in ("52345678-1234-4234-8234-123456789012",
          "62345678-1234-4234-8234-123456789012"):
    J(f"/public/events/{EV}/ballot", None, "POST",
      {"project_id": PID, "votes": 1, "voter_id": v})
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PIDS[1] if len(PIDS) > 1 else PID, "votes": 1, "voter_id": VID})
check("11th vote over budget refused (422)", s == 422, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": -1, "voter_id": VID})
check("negative votes refused (422)", s == 422, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 11, "voter_id": VID})
check("11 on one project refused (422)", s == 422, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 1, "voter_id": "garbage"})
check("garbage voter id refused (422)", s == 422, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": PID, "votes": 1})
check("missing voter id refused (422)", s == 422, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": "prj_nope", "votes": 1, "voter_id": VID})
check("unknown project refused (404)", s == 404, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": "prj_01", "votes": 1, "voter_id": VID})
check("other event's project refused (404)", s == 404, f"got {s}")

# ---- auth-mode gates on a second event (member's own team exists there)
s, b = J("/events", O, "POST", {"name": "Pentest Auth", "slug": f"t3-probe-pentest-auth-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV2 = b["event"]["id"] if s == 200 else None
J(f"/events/{EV2}/publish", O, "POST", {})
J(f"/events/{EV2}/voting", O, "PATCH",
  {"voting_enabled": True, "voting_mode": "auth",
   "voting_close": "2030-06-01T00:00:00Z"})
s, _ = J(f"/public/events/{EV2}/ballot", None, "POST",
         {"project_id": PID, "votes": 1})
check("auth mode refuses anonymous (401)", s == 401, f"got {s}")
# Draft target: ballot on an unpublished event is invisible, not forbidden.
s, b = J("/events", O, "POST", {"name": "Pentest Draft", "slug": f"t3-probe-pentest-draft-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EVD = b["event"]["id"] if s == 200 else None
s, _ = J(f"/public/events/{EVD}/ballot", None)
check("draft ballot hidden from anon (404, no leak)", s == 404, f"got {s}")

# ---- own-team block (auth mode, member votes own project)
s, b = J(f"/events/{EV2}/tracks", O, "POST", {"name": "T"})
TRK2 = b["track"]["id"] if s == 200 else None
J(f"/events/{EV2}/join", MEM, "POST",
  dict(REG, email=f"t3u2-pentest-{RUN}@local.test"))
_, t = J(f"/events/{EV2}/teams", MEM, "POST", {"name": "Pen Own Team"})
_, p = J("/submissions", MEM, "POST",
         {"team_id": t["team"]["id"], "event_id": EV2, "track_id": TRK2,
          "title": "Own P", "summary": "own"})
OWNP = p.get("project", {}).get("id", "prj_nope")
J(f"/submissions/{OWNP}/submit", MEM, "POST", {})
s, _ = J(f"/public/events/{EV2}/ballot", MEM, "POST",
         {"project_id": OWNP, "votes": 1})
check("own-team vote blocked (403)", s == 403, f"got {s}")

# ---- pre-close tally pull
s, _ = J(f"/public/events/{EV}/votes/results", None)
check("results hidden before close (403)", s == 403, f"got {s}")

# ---- comment abuse
s, _ = J(f"/public/projects/{PID}/comments", None, "POST", {"body": "anon"})
check("anonymous comment refused (401)", s == 401, f"got {s}")
s, _ = J(f"/public/projects/{PID}/comments", MEM, "POST", {"body": "  "})
check("blank comment refused (422)", s == 422, f"got {s}")
# Hidden project: organizer hides P2 via visibility, outsider must get 404.
_, subs = J(f"/events/{EV}/submissions", O)
HID = next((x["id"] for x in subs.get("submissions", []) if x["id"] != PID), PID)
J(f"/submissions/{HID}/visibility", O, "POST", {"visible": False})
s, _ = J(f"/public/projects/{HID}/comments", MEM, "POST", {"body": "sneaky"})
check("comment on hidden project refused (404)", s == 404, f"got {s}")
s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
         {"project_id": HID, "votes": 1,
          "voter_id": "22345678-1234-4234-8234-123456789012"})
check("ballot on hidden project refused (404)", s == 404, f"got {s}")
J(f"/submissions/{HID}/visibility", O, "POST", {"visible": True})

# ---- identical repost refused
DUP = f"same words {RUN}"
s, _ = J(f"/public/projects/{PID}/comments", MEM, "POST", {"body": DUP})
check("first posting accepted", s == 200, f"got {s}")
s, _ = J(f"/public/projects/{PID}/comments", MEM, "POST", {"body": DUP})
check("identical repost refused (429)", s == 429, f"got {s}")

# ---- budget double-spend race: two concurrent 10-vote casts, one voter.
# Runs BEFORE the floods below saturate this IP's vote bucket.
import threading
RACE = "72345678-1234-4234-8234-123456789012"
race_codes = []
race_threads = [threading.Thread(
    target=lambda p=pid: race_codes.append(req(
        f"/public/events/{EV}/ballot", None, "POST",
        {"project_id": p, "votes": 10, "voter_id": RACE})[0]))
    for pid in PIDS[:2]]
for t in race_threads:
    t.start()
for t in race_threads:
    t.join()
s, b = J(f"/public/events/{EV}/ballot?voter_id={RACE}", None)
spent = sum((b.get("my_votes") or {}).values())
check("concurrent double-spend capped at budget",
      sorted(race_codes) == [200, 422] and spent == 10,
      f"codes={race_codes} spent={spent}")

# ---- floods (this IP's vote bucket is now partly spent, which is fine:
# 45 requests still overflow the 30/min budget deterministically)
codes = {}
for i in range(45):
    s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
             {"project_id": "prj_nope", "votes": 0,
              "voter_id": "32345678-1234-4234-8234-123456789012"})
    codes[s] = codes.get(s, 0) + 1
check("ballot flood trips 429", codes.get(429, 0) > 0, f"{codes}")
codes = {}
for i in range(45):
    s, _ = J(f"/public/events/{EV}/ballot", None, "POST",
             {"project_id": "prj_nope", "votes": 0,
              "voter_id": "42345678-1234-4234-8234-123456789012"},
             extra_headers={"X-Forwarded-For": "9.9.9.9"})
    codes[s] = codes.get(s, 0) + 1
check("flood with spoofed XFF still trips 429", codes.get(429, 0) > 0, f"{codes}")
codes = {}
for i in range(30):
    s, _ = J(f"/public/projects/{PID}/comments", MEM, "POST",
             {"body": f"spam {i}"})
    codes[s] = codes.get(s, 0) + 1
check("comment flood trips 429", codes.get(429, 0) > 0, f"{codes}")

# ---- organizer reads everything without a db client
s, b = J(f"/events/{EV}/audit", O)
acts = {e["action"] for e in b.get("entries", [])}
check("organizer reads event audit", s == 200 and "vote.cast" in acts, f"got {s}")
check("audit shows ballot refusals", "vote.rate_limited" in acts, f"{sorted(acts)}")
check("audit shows comment refusals", "comment.rate_limited" in acts, f"{sorted(acts)}")
check("audit shows duplicate refusals", "comment.duplicate" in acts, f"{sorted(acts)}")
s, _ = J(f"/events/{EV}/audit", P)
check("audit organizer-only (403)", s == 403, f"got {s}")
s, b = J(f"/events/{EV}/audit?action=vote.cast", O)
check("audit action filter works",
      s == 200 and all(e["action"] == "vote.cast" for e in b.get("entries", [])), f"got {s}")
s, b = J(f"/events/{EV}/voting", O)
check("turnout flags shared-device voters",
      s == 200 and len(b.get("turnout", {}).get("fp_collisions", [])) > 0, f"{b.get('turnout')}")

# ---- auth-surface floods (hour/minute buckets are per-route, so these run
# last; rerunning this script within the hour trips the register setup —
# that cooldown is the throttle working as designed)
codes = {}
for i in range(103):
    s, _ = J("/auth/register", None, "POST",
             {"email": f"sybil{i}-{RUN}@local.test", "password": PW,
              "display_name": "sybil"})
    codes[s] = codes.get(s, 0) + 1
check("mass registration throttled (429)", codes.get(429, 0) > 0, f"{codes}")
codes = {}
for i in range(35):
    s, _ = J("/auth/login", None, "POST",
             {"email": "nobody@nowhere.test", "password": "wrongpass1"})
    codes[s] = codes.get(s, 0) + 1
check("login flood throttled (429)", codes.get(429, 0) > 0, f"{codes}")
s, b = J("/admin/audit?limit=500", "Cookie: session=adm_9c1b_local_test_token")
admin_acts = {e["action"] for e in b.get("entries", [])} if s == 200 else set()
check("throttle refusals reach admin audit",
      "auth.register_rate_limited" in admin_acts and "auth.login_rate_limited" in admin_acts,
      f"{sorted(admin_acts)[:10]}")

print("ABUSE PEN TEST")
ok = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok = ok and c
print("ALL PASS" if ok else "FAILURES PRESENT")
raise SystemExit(0 if ok else 1)
