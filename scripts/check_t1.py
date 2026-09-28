#!/usr/bin/env python3
"""Internal T1 verification suite (not the official checker).
Covers: health, seed counts, auth, roles, events, join, teams, invites,
drafts, deadlines, gallery, leakage. Prints PASS/FAIL per check."""
import json, os, time, urllib.request, urllib.error

BASE = "http://localhost:8000"
P = "Cookie: session=prt_2e88_local_test_token"
O = "Cookie: session=org_7f2a_local_test_token"
A = "Cookie: session=adm_9c1b_local_test_token"

def req(path, header=None, method="GET", body=None):
    r = urllib.request.Request(BASE + path, method=method)
    if header:
        n, _, v = header.partition(":")
        r.add_header(n.strip(), v.strip())
    if body is not None:
        r.data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))

s, b = req("/health")
check("health", s == 200, f"got {s}")
s, b = req("/public/events")
check("public events", s == 200 and "Sample Hack" in b, f"got {s}")
s, b = req("/public/events/sample-hack-2026/projects?q=Glass+Signal")
check("gallery search title", s == 200 and "Glass Signal" in b, f"got {s}")
s, b = req("/public/events/sample-hack-2026/projects?track=trk_04&page=1&page_size=5")
d = json.loads(b) if s == 200 else {}
check("gallery track filter", s == 200 and all(p["track_id"] == "trk_04" for p in d.get("projects", [])), f"got {s}")
s, b = req("/public/events/sample-hack-2026/projects?page_size=200")
d = json.loads(b) if s == 200 else {}
# Bounded = server either clamps to <=50 or rejects the oversized page.
bounded = (s == 200 and d.get("page_size", 999) <= 50) or s == 422
check("page_size bounded", bounded, f"got {s} {d.get('page_size')}")
check("no leakage in gallery", "password" not in b.lower() and "token_hash" not in b.lower(), "")
s, b = req("/submissions", header=P, method="POST", body={"title": "x", "summary": "y"})
check("closed event refuses submissions (4xx)", 400 <= s < 500, f"got {s}")
s, b = req("/events", header=P, method="POST", body={"name": "Nope", "submissions_close": "2030-01-01T00:00:00Z"})
check("participant cannot create event (403)", s == 403, f"got {s}")
s, b = req("/auth/me", header=P)
check("session works", s == 200 and "participant@local.test" in b, f"got {s}")
s, b = req("/auth/me", header="Cookie: session=bogus")
check("bad session rejected (401)", s == 401, f"got {s}")
s, b = req("/events/evt_01/membership", header=P)
check("membership endpoint", s == 200 and "joined" in b, f"got {s}")
s, b = req("/events/evt_01/participants", header=P)
check("participants list is organizer-only (403)", s == 403, f"got {s}")
s, b = req("/events/evt_01/participants", header=O)
check("organizer sees participants", s == 200 and "team_name" in b, f"got {s}")
s, b = req("/events/evt_01/submissions", header=O)
check("organizer sees submissions", s == 200 and "is_visible" in b, f"got {s}")

# ---- event-scoped organizer access ----
# One reusable draft event, so re-running this check does not pile up events.
PROBE_SLUG = "scope-probe-tmp"
s, b = req("/events", method="POST", header=O, body={"name": "Scope Probe", "slug": PROBE_SLUG})
if s == 409:
    s, b = req(f"/events/{PROBE_SLUG}", header=O)
probe = json.loads(b)["event"]["id"] if s == 200 else None
check("organizer reaches own draft event", probe is not None, f"got {s} {b[:80]}")
s, b = req(f"/events/{probe}/organizers", header=O)
check("creator listed on own event", s == 200 and any(o["is_owner"] for o in json.loads(b).get("organizers", [])), f"got {s}")
s, b = req(f"/events/{probe}/tracks", header=O, method="POST", body={"name": "Probe Track"})
probe_track = json.loads(b)["track"]["id"] if s == 200 else None
s, b = req(f"/events/{probe}/stats", header=P)
check("participant cannot read other event stats (403)", s == 403, f"got {s}")
s, b = req(f"/events/{probe}", header=P)
check("participant cannot read draft event (404, no leak)", s == 404, f"got {s}")
s, b = req(f"/events/{probe}/tracks", header=P, method="POST", body={"name": "Sneaky"})
check("participant cannot add track to draft (403)", s == 403, f"got {s}")
s, b = req(f"/events/{probe}/publish", header=P, method="POST", body="{}")
check("participant cannot publish (403)", s == 403, f"got {s}")
s, b = req(f"/events/{probe}/organizers", header=P)
check("participant cannot list organizers (403)", s == 403, f"got {s}")
# Assign a second organizer, then confirm scoping follows the assignment.
s, b = req(f"/events/{probe}/organizers", header=O, method="POST", body={"email": "admin@local.test"})
check("add organizer by email", s == 200, f"got {s} {b[:120]}")
s, b = req(f"/events/{probe}/organizers", header=O, method="POST", body={"email": "participant@local.test"})
check("cannot assign a non-organizer", s in (403, 422), f"got {s}")
s, b = req(f"/events/{probe}/organizers", header=O, method="POST", body={"email": "nobody@nowhere.test"})
check("unknown email is 404 (no directory leak)", s == 404, f"got {s}")
# Unique per process, not per second: two runs inside the same second would
# otherwise reuse a track name and collide on the event's unique (event, name).
RUN = f"{int(time.time()) % 1000000:x}{os.getpid() % 4096:03x}"
s, b = req(f"/events/{probe}/tracks", header=A, method="POST", body={"name": f"Admin Track {RUN}"})
check("assigned organizer can write to event", s == 200, f"got {s} {b[:120]}")
s, b = req(f"/events/{probe}/organizers", header=A)
orgs_list = json.loads(b).get("organizers", []) if s == 200 else []
owner_id = next((o["user_id"] for o in orgs_list if o["is_owner"]), "x")
guest_id = next((o["user_id"] for o in orgs_list if not o["is_owner"]), "x")
s, b = req(f"/events/{probe}/organizers/{owner_id}", header=A, method="DELETE")
check("owner cannot be removed", s == 409, f"got {s}")
s, b = req(f"/events/{probe}/organizers/{guest_id}", header=A, method="DELETE")
check("co-organizer can be removed", s == 200, f"got {s}")
s, b = req(f"/events/{probe}/organizers", header=O)
check("removal is reflected in the roster", guest_id not in [o["user_id"] for o in json.loads(b).get("organizers", [])], f"got {s}")
s, b = req(f"/events/{probe}/tracks", header=A, method="POST", body={"name": f"After Removal {RUN}"})
check("admin keeps platform-wide access (documented bypass)", s == 200, f"got {s}")
if probe_track:
    s, b = req(f"/tracks/{probe_track}", header=P, method="PATCH", body={"name": "Hijacked"})
    check("child id alone cannot edit another event's track", s in (403, 404), f"got {s}")
s, b = req(f"/events/{probe}/unpublish", header=A, method="POST", body="{}")
check("assigned organizer can unpublish", s == 200, f"got {s}")
# Publish it once so the audit-trail check below has a real row to find,
# rather than depending on whatever a previous run happened to leave behind.
# Publishing needs a name and a deadline.
s, b = req(f"/events/{probe}", header=O, method="PATCH",
           body={"name": "Scope Probe", "submissions_close": "2030-01-01T00:00:00Z"})
check("probe event has the fields publish needs", s == 200, f"got {s} {b[:120]}")
s, b = req(f"/events/{probe}/publish", header=O, method="POST", body="{}")
check("organizer can publish the probe event", s == 200 and '"PUBLISHED"' in b, f"got {s} {b[:120]}")
s, b = req(f"/events/{probe}/unpublish", header=O, method="POST", body="{}")
check("probe event returned to draft", s == 200, f"got {s}")
# The probe event stays a draft owned by the demo organizer.
s, b = req("/events", header=O)
mine = [e["id"] for e in json.loads(b).get("events", [])]
check("organizer event list is scoped to owned events", probe in mine, f"got {s} {mine}")

# ---- admin role console ----
# Only ADMIN may change roles or read the audit trail.
s, b = req("/admin/audit", header=O)
check("audit log is admin-only (403 for organizer)", s == 403, f"got {s}")
s, b = req("/admin/audit", header=P)
check("audit log is admin-only (403 for participant)", s == 403, f"got {s}")
s, b = req("/admin/audit")
check("audit log needs auth (401 anonymous)", s == 401, f"got {s}")
s, b = req("/admin/audit", header=A)
check("admin reads audit log", s == 200 and "entries" in b, f"got {s}")
s, b = req("/admin/users", header=O)
check("user directory is admin-only (403 for organizer)", s == 403, f"got {s}")
s, b = req("/admin/users/role", header=O, method="POST", body={"email": "participant@local.test", "role": "ADMIN"})
check("organizer cannot grant roles (403)", s == 403, f"got {s}")
s, b = req("/admin/users/role", header=P, method="POST", body={"email": "participant@local.test", "role": "ADMIN"})
check("participant cannot grant roles (403)", s == 403, f"got {s}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "admin@local.test", "role": "ORGANIZER"})
check("admin cannot change own role (409)", s == 409, f"got {s}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "nobody@nowhere.test", "role": "ORGANIZER"})
check("unknown account cannot be promoted (404)", s == 404, f"got {s}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "participant@local.test", "role": "SUPERUSER"})
check("unknown role value rejected (422)", s == 422, f"got {s}")
# ---- staff and judges cannot register for events ----
# Registration is the participant flow. A staff account or a judge running an
# event must never end up in its participant roster.
REG = {"fullName": "Probe", "email": "probe@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "Probe U", "category": "Open Innovation"}
s, b = req("/events/evt_01/join", header=A, method="POST", body=REG)
check("admin cannot register for an event (403)", s == 403, f"got {s}")
s, b = req("/events/evt_01/join", header=O, method="POST", body=REG)
check("organizer cannot register for an event (403)", s == 403, f"got {s}")
JB = "Cookie: session=jdg_judge_a_91bc_local_token"
s, b = req("/events/evt_01/join", header=JB, method="POST", body=REG)
check("judge cannot register for an event (403)", s == 403, f"got {s}")
s, b = req("/events/evt_01/join", header=P, method="POST", body=REG)
check("participant registration still works", s == 200, f"got {s} {b[:120]}")

# The probe registration above is real data; drop it so re-runs stay clean.
s, b = req("/events/evt_01/join", header=P, method="DELETE")
check("probe registration cleaned up", s == 200, f"got {s}")

# ---- admin can move any account to any role ----
# participant@local.test starts as PARTICIPANT and must end where it started.
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "participant@local.test", "role": "ORGANIZER"})
check("admin promotes a participant to organizer", s == 200 and '"ORGANIZER"' in b, f"got {s} {b[:120]}")
s, b = req("/auth/me", header=P)
check("promotion is live immediately", s == 200 and '"ORGANIZER"' in b, f"got {s} {b[:120]}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "participant@local.test", "role": "JUDGE"})
check("admin promotes a participant to judge", s == 200 and '"JUDGE"' in b, f"got {s} {b[:120]}")
s, b = req("/auth/me", header=P)
check("judge promotion is live immediately", s == 200 and '"JUDGE"' in b, f"got {s} {b[:120]}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "participant@local.test", "role": "PARTICIPANT"})
check("admin demotes a judge back to participant", s == 200 and '"PARTICIPANT"' in b, f"got {s} {b[:120]}")
s, b = req("/auth/me", header=P)
check("demotion is live immediately", s == 200 and '"PARTICIPANT"' in b, f"got {s} {b[:120]}")
# organizer <-> admin still works, and the demo accounts end where they started.
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "organizer@local.test", "role": "ADMIN"})
check("admin promotes an organizer to admin", s == 200 and '"ADMIN"' in b, f"got {s} {b[:120]}")
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "organizer@local.test", "role": "ORGANIZER"})
check("admin steps an admin back to organizer", s == 200 and '"ORGANIZER"' in b, f"got {s} {b[:120]}")
s, b = req("/auth/me", header=O)
check("organizer role restored", s == 200 and '"ORGANIZER"' in b, f"got {s} {b[:120]}")
# A no-op change is idempotent rather than an error.
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "organizer@local.test", "role": "ORGANIZER"})
check("setting the current role is a no-op", s == 200 and '"changed": false' in b.replace('"changed":false', '"changed": false'), f"got {s} {b[:120]}")
# The last admin cannot be stepped down: platform lockout protection stays.
s, b = req("/admin/users/role", header=A, method="POST", body={"email": "admin@local.test", "role": "JUDGE"})
check("admin cannot change own role, so the last admin is safe (409)", s == 409, f"got {s}")
# Audit trail must contain the security-relevant actions, and no secrets.
s, b = req("/admin/audit?limit=500", header=A)
d = json.loads(b) if s == 200 else {}
actions = {e["action"] for e in d.get("entries", [])}
for act in ("user.role_changed", "user.role_change_refused", "event.organizer_added", "event.published"):
    check(f"audit records {act}", act in actions, f"actions={sorted(actions)[:8]}")
check("audit records failed sign-ins", "auth.login_failed" in actions, f"actions={sorted(actions)[:8]}")
low = json.dumps(d).lower()
# Look for actual credential material, not the bare word "password" (the action
# name auth.password_changed legitimately contains it).
found = [m for m in ("argon2", "password_hash", "token_hash", '"password":', '"token":',
                     "local123!", "session=") if m in low]
check("audit stores no credentials", not found, f"found={found}")
s, b = req("/admin/audit?q=zzzz-no-such-actor", header=A)
check("audit search filter works", s == 200 and json.loads(b)["total"] == 0, f"got {s}")
s, b = req("/admin/audit?limit=99999", header=A)
check("audit page_size is bounded (422)", s == 422, f"got {s}")

print("INTERNAL T1 verification")
ok = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok = ok and c
print("ALL PASS" if ok else "FAILURES PRESENT")
raise SystemExit(0 if ok else 1)
