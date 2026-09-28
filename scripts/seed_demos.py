#!/usr/bin/env python3
"""Seed dedicated manual-test events (idempotent, rerun-safe).

Creates three stable events with full metadata — tracks, prizes, rubric,
judging/voting config — for testing specific flows by hand in the UI:

  demo-bt    "BT Model Demo"       Crowd-BT ranking: weighted rubric
               (Craft 60 / Scope 40), 2 judges, batch assignment.
  demo-vote  "Community Vote Demo" T3 voting: open mode, public comments.
  demo-bayes "Bayes Score Demo"    Hier-Bayes edge case: unweighted rubric
               (equal-weight fallback), 1 judge per project.

Leaves evt_01 (Sample Hack 2026) and fixtures.json data untouched: every
lookup is scoped to the demo slugs, and nothing here deletes anything.
Usage:  python scripts/seed_demos.py
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
O = "Cookie: session=org_7f2a_local_test_token"

FUTURE = "2030-06-01T00:00:00Z"
JUDGE_A = "tomas.varga@example.org"
JUDGE_B = "wei.lindqvist@example.org"


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


def ensure_event(slug, name, description):
    s, b = J("/events", O, "POST", {"name": name, "slug": slug,
                                    "description": description,
                                    "submissions_close": FUTURE})
    if s == 200:
        return b["event"]["id"], True
    if s == 409:  # already there — reuse
        s, b = J(f"/events/{slug}", O)
        if s == 200:
            return b["event"]["id"], False
    return None, False


def ensure_tracks(ev, names):
    _, b = J(f"/events/{ev}/tracks", O)
    have = {t["name"]: t["id"] for t in b.get("tracks", [])}
    for n in names:
        if n not in have:
            s, d = J(f"/events/{ev}/tracks", O, "POST", {"name": n})
            if s == 200:
                have[n] = d["track"]["id"]
    return have


def ensure_prizes(ev, specs, tracks):
    """specs: [(name, description, value_desc, track_name_or_None)]."""
    _, b = J(f"/events/{ev}/prizes", O)
    have = {p["name"] for p in b.get("prizes", [])}
    for name, desc, val, track_name in specs:
        if name in have:
            continue
        body = {"name": name, "description": desc, "value_desc": val}
        if track_name:
            body["track_id"] = tracks.get(track_name)
        J(f"/events/{ev}/prizes", O, "POST", body)


def ensure_rubric(ev, specs):
    """specs: [(name, weight_or_None)]. Sets exact weights via PATCH."""
    _, b = J(f"/events/{ev}/rubric", O)
    have = {c["name"]: c for c in b.get("criteria", [])}
    for i, (name, weight) in enumerate(specs):
        if name not in have:
            s, d = J(f"/events/{ev}/rubric", O, "POST",
                     {"name": name, "description": name})
            if s != 200:
                continue
            have[name] = d["criterion"]
        c = have[name]
        if c.get("weight") != weight:
            body = {"name": name, "display_order": i}
            if weight is not None:
                body["weight"] = weight
            J(f"/rubric/{c['id']}", O, "PATCH", body)


def ensure_judges(ev, emails):
    for em in emails:
        J(f"/events/{ev}/judges", O, "POST", {"email": em})


DEMOS = [
    {"slug": "demo-bt", "name": "BT Model Demo",
     "description": "Stable fixture for hand-testing Crowd-BT ranking: "
                    "weighted rubric, two judges, batch assignment. "
                    "Add teams + projects in the UI, then score and calculate.",
     "tracks": ["Machine Learning", "Web Platform"],
     "prizes": [("Best Overall", "Top of the BT ranking", "$500 cash", None),
                ("Best ML Hack", "Best project on the ML track", "$250 cash",
                 "Machine Learning")],
     "rubric": [("Craft", 60), ("Scope", 40)],
     "judging": {"judges_per_project": 2, "rolling_judging": False},
     "judges": [JUDGE_A, JUDGE_B],
     "voting": None},
    {"slug": "demo-vote", "name": "Community Vote Demo",
     "description": "Stable fixture for hand-testing T3 community voting: "
                    "open ballot, public comments. Add teams + projects, "
                    "then vote from an incognito window.",
     "tracks": ["Open Innovation", "Design"],
     "prizes": [("Crowd Favorite", "Most community influence", "Glory", None)],
     "rubric": [],
     "judging": None,
     "judges": [],
     "voting": {"voting_enabled": True, "voting_mode": "open",
                "voting_close": FUTURE, "comments_visibility": "public"}},
    {"slug": "demo-bayes", "name": "Bayes Score Demo",
     "description": "Stable fixture for the single-judge-per-project edge "
                    "case: unweighted rubric (equal-weight fallback), one "
                    "judge per project.",
     "tracks": ["Prototypes"],
     "prizes": [("Most Promising", "Highest posterior mean", "$100 cash", None)],
     "rubric": [("Craft", None), ("Scope", None)],
     "judging": {"judges_per_project": 1, "rolling_judging": False},
     "judges": [JUDGE_A],
     "voting": None},
]

for d in DEMOS:
    ev, created = ensure_event(d["slug"], d["name"], d["description"])
    check(f"{d['slug']}: event present", ev is not None)
    if not ev:
        continue
    # Refresh metadata every run so the demos never drift stale.
    J(f"/events/{ev}", O, "PATCH",
      {"name": d["name"], "description": d["description"],
       "submissions_close": FUTURE})
    tracks = ensure_tracks(ev, d["tracks"])
    check(f"{d['slug']}: tracks filled ({len(d['tracks'])})",
          all(n in tracks for n in d["tracks"]), f"{sorted(tracks)}")
    ensure_prizes(ev, d["prizes"], tracks)
    _, pb = J(f"/events/{ev}/prizes", O)
    check(f"{d['slug']}: prizes filled ({len(d['prizes'])})",
          len(pb.get("prizes", [])) >= len(d["prizes"]),
          f"{[p['name'] for p in pb.get('prizes', [])]}")
    if d["rubric"]:
        ensure_rubric(ev, d["rubric"])
    if d["judging"]:
        J(f"/events/{ev}/judging", O, "PATCH", d["judging"])
    if d["judges"]:
        ensure_judges(ev, d["judges"])
    if d["voting"]:
        J(f"/events/{ev}/voting", O, "PATCH", d["voting"])
    s, _ = J(f"/events/{ev}/publish", O, "POST", {})
    check(f"{d['slug']}: published", s in (200, 409), f"got {s}")

print("DEMO SEED")
ok = True
for n, c, det in results:
    print(f"{'PASS' if c else 'FAIL'}  {n}" + ("" if c else f" -- {det}"))
    ok = ok and c
print("ALL PASS" if ok else "FAILURES PRESENT")
raise SystemExit(0 if ok else 1)
