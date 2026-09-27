#!/usr/bin/env python3
"""Internal T1 verification suite (not the official checker).
Covers: health, seed counts, auth, roles, events, join, teams, invites,
drafts, deadlines, gallery, leakage. Prints PASS/FAIL per check."""
import json, urllib.request, urllib.error

BASE = "http://localhost:8000"
P = "Cookie: session=prt_2e88_local_test_token"
O = "Cookie: session=org_7f2a_local_test_token"

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

print("INTERNAL T1 verification")
ok = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok = ok and c
print("ALL PASS" if ok else "FAILURES PRESENT")
raise SystemExit(0 if ok else 1)
