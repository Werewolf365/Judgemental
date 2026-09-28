#!/usr/bin/env python3
"""Internal T4 verification suite: certificates + bulk transfer.

Covers template upload matrix, certificate gating (registration +
declared results), winner/participation kinds, mine listing, export ZIP
(all 14 datasets, subset, errors, authZ), and create-only CSV import with
role rules — on throwaway draft probes left behind per repo convention.
Prints PASS/FAIL.
"""
import http.cookiejar
import io
import json
import os
import time
import urllib.request
import urllib.error
import zipfile

BASE = "http://localhost:8000"
RUN = f"{int(time.time()) % 1000000:x}{os.getpid() % 4096:03x}"
O = "Cookie: session=org_7f2a_local_test_token"
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


def J(path, header, method="GET", body=None):
    s, b = req(path, header, method, body)
    try:
        return s, json.loads(b) if b else {}
    except Exception:
        return s, {"_raw": b[:200]}


results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f" -- {detail}"))


def _login(email):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = urllib.request.Request(BASE + "/auth/login",
        data=json.dumps({"email": email, "password": "ProbePass123"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        opener.open(r, timeout=30)
    except Exception:
        return None
    tok = [c.value for c in cj if c.name == "session"]
    return f"Cookie: session={tok[0]}" if tok else None


def mkuser(email):
    s, _ = J("/auth/register", None, "POST",
             {"email": email, "password": "ProbePass123", "display_name": email})
    if s not in (200, 409):
        return None
    return _login(email)


def post_multipart(path, header, fields, filename, content):
    boundary = "----probe1234"
    lines = []
    for k, v in fields.items():
        lines += [f"--{boundary}", f'Content-Disposition: form-data; name="{k}"', "", v]
    lines += [f"--{boundary}",
              f'Content-Disposition: form-data; name="file"; filename="{filename}"',
              "Content-Type: text/csv", "",
              content if isinstance(content, str) else content.decode()]
    body = ("\r\n".join(lines) + f"\r\n--{boundary}--\r\n").encode()
    n, _, v = header.partition(":")
    r = urllib.request.Request(BASE + path, method="POST", data=body,
        headers={n.strip(): v.strip(), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_err": str(e)}


REG = {"fullName": "T4", "email": "t4@local.test", "phone": "9999999999",
       "age": 20, "degree": "B.Tech", "yearOfStudy": "3rd Year",
       "institution": "T4 U", "category": "Open Innovation"}

# ---- setup ----
s, b = J("/events", O, "POST", {"name": "T4 Probe", "slug": f"t4-probe-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV = b["event"]["id"]
check("probe event created", EV is not None, f"got {s}")

# ---- template matrix (before any upload) ----
s, b = J(f"/events/{EV}/certificate-template", O)
check("template missing -> 404", s == 404, f"got {s}")
s, _ = J(f"/events/{EV}/certificate-template", O, "PUT", {"image": "http://x/y.png"})
check("non-image template refused (422)", s == 422, f"got {s}")
s, _ = J(f"/events/{EV}/certificate-template", P, "PUT", {"image": "data:image/png;base64,AAA"})
check("template organizer-only (403)", s == 403, f"got {s}")
s, _ = J(f"/events/{EV}/certificate-template", O, "PUT", {"image": "data:image/png;base64,AAA"})
check("template uploaded", s == 200, f"got {s}")
s, b = J(f"/events/{EV}/certificate-template", O)
check("template read back", s == 200 and b.get("image", "").startswith("data:image/"), f"got {s}")

# ---- import: tracks first (projects need one) ----
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "tracks"},
                      "tracks.csv", "name\nT4 Track\nT4 Extra\n")
TRK_OK = s == 200 and b.get("created") == 2
check("tracks imported (2 created)", TRK_OK, f"got {s} {b}")
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "tracks"},
                      "tracks.csv", "name\nT4 Track\nT4 Extra\n")
check("tracks re-import skips duplicates", s == 200 and b.get("created") == 0 and b.get("skipped") == 2, f"got {s} {b}")
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "tracks"},
                      "bad.csv", "title\nNope\n")
check("tracks bad header refused", s == 200 and b.get("created") == 0 and b.get("errors"), f"got {s} {b}")
s, b = post_multipart(f"/events/{EV}/import", P, {"dataset": "tracks"},
                      "tracks.csv", "name\nSneaky\n")
check("import organizer-only (403)", s == 403, f"got {s}")
s, b = J(f"/events/{EV}/tracks", O)
TRK = next((t["id"] for t in b.get("tracks", []) if t["name"] == "T4 Track"), None)

# ---- import: prizes / judges / organizers ----
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "prizes"},
                      "prizes.csv", "name,description,value,track\nBest,T4 desc,Glory,T4 Track\nOrphan,X,Y,Nope\n")
check("prizes import (1 created, unknown track skipped)",
      s == 200 and b.get("created") == 1 and b.get("skipped") == 1 and b.get("errors"), f"got {s} {b}")
_, me_b = J("/auth/me", JB)
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "judges"},
                      "judges.csv", f"email\n{me_b['user']['email']}\nparticipant@local.test\nnobody@local.test\n")
check("judges import (1 created, non-judge + missing reported)",
      s == 200 and b.get("created") == 1 and b.get("skipped") == 2 and len(b.get("errors", [])) == 2, f"got {s} {b}")
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "organizers"},
                      "orgs.csv", "email\norganizer@local.test\nparticipant@local.test\n")
check("organizers import (dup skipped, non-organizer reported)",
      s == 200 and b.get("created") == 0 and b.get("skipped") == 2 and len(b.get("errors", [])) == 1, f"got {s} {b}")
s, b = post_multipart(f"/events/{EV}/import", O, {"dataset": "ballots"},
                      "b.csv", "x\n1\n")
check("non-importable dataset refused (422)", s == 422, f"got {s}")

# ---- rubric import matrix on a second probe (empty rubric) ----
s, b = J("/events", O, "POST", {"name": "T4 Probe 2", "slug": f"t4-probe2-{RUN}",
                                "submissions_close": "2030-01-01T00:00:00Z"})
EV2 = b["event"]["id"]
s, b = post_multipart(f"/events/{EV2}/import", O, {"dataset": "rubric"},
                      "rubric.csv", "name,weight\nR1,60\nR2,40\nR3,50\nR4,zzz\n")
check("rubric import (2 created, over-cap + bad weight skipped)",
      s == 200 and b.get("created") == 2 and b.get("skipped") == 2 and len(b.get("errors", [])) == 2, f"got {s} {b}")

# ---- projects + judging on EV ----
U1 = mkuser(f"t4u1-{RUN}@local.test")
U2 = mkuser(f"t4u2-{RUN}@local.test")
PIDS = []
for h, em, i in ((U1, f"t4u1-{RUN}@local.test", 1), (U2, f"t4u2-{RUN}@local.test", 2)):
    req(f"/events/{EV}/join", h, "POST", dict(REG, email=em, fullName=f"T4-{i}"))
    _, t = J(f"/events/{EV}/teams", h, "POST", {"name": f"T4 Team {i} {RUN}"})
    _, p = J("/submissions", h, "POST", {"team_id": t["team"]["id"], "event_id": EV,
                                         "track_id": TRK, "title": f"T4 P{i}", "summary": "s"})
    PIDS.append(p["project"]["id"])
    req(f"/submissions/{p['project']['id']}/submit", h, "POST", {})
check("two submitted projects", len(PIDS) == 2, f"{PIDS}")
s, b = J(f"/events/{EV}/rubric", O, "POST", {"name": "Q", "weight": 100})
s, b = J(f"/events/{EV}/certificate", U1)
check("certificate before results -> 404", s == 404, f"got {s} {b}")
_, me_a = J("/auth/me", JA)
J(f"/events/{EV}/judges", O, "POST", {"email": me_a["user"]["email"]})
J(f"/events/{EV}/judging", O, "PATCH", {"judges_per_project": 2, "rolling_judging": False})
J(f"/events/{EV}/assignments/batch", O, "POST", {})
WANT = {"T4 P1": 8, "T4 P2": 6}
_, mine = J("/judge/assignments", JA)
mine = [a for a in mine["assignments"] if a["event_id"] == EV]
ok = len(mine) == 2
for a in mine:
    det = J(f"/judge/assignments/{a['id']}", JA)[1]["assignment"]
    crits = {c["name"]: c["id"] for c in det["rubric"]}
    s, _ = J(f"/judge/assignments/{a['id']}/scores", JA, "POST",
             {"scores": {crits["Q"]: WANT[det["project"]["title"]]}})
    ok = ok and s == 200
    s, _ = J(f"/judge/assignments/{a['id']}/submit", JA, "POST", {})
    ok = ok and s == 200
check("judge scored both (P1=8 P2=6)", ok)
J(f"/events/{EV}/publish", O, "POST", {})
J(f"/events/{EV}/voting", O, "PATCH", {"voting_enabled": True, "voting_mode": "email",
                                       "voting_close": "2030-06-01T00:00:00Z"})
J(f"/public/events/{EV}/ballot", None, "POST",
  {"project_id": PIDS[1], "votes": 2, "email": f"t4v-{RUN}@local.test"})
J(f"/events/{EV}/judging", O, "PATCH", {"judging_close": "2020-01-01T00:00:00Z"})
s, b = J(f"/events/{EV}/results/calculate", O, "POST", {})
check("calculated (results declared)", s == 200, f"got {s} {b}")

# ---- certificates ----
s, b = J(f"/events/{EV}/certificate", U1)
check("winner certificate issued", s == 200 and b.get("kind") == "WINNER"
      and b.get("rank") == 1 and b.get("code") and b.get("template_image", "").startswith("data:image/"), f"got {s} {b}")
s, b = J(f"/events/{EV}/certificate", U2)
check("participation certificate issued", s == 200 and b.get("kind") == "PARTICIPATION"
      and b.get("code"), f"got {s} {b}")
s, b = J(f"/events/{EV}/certificate", U1)
check("certificate idempotent on re-view", s == 200 and b.get("kind") == "WINNER", f"got {s}")
s, b = J("/certificates/mine", U1)
mine1 = [c for c in b.get("certificates", []) if c["event_id"] == EV]
check("mine lists declared kind", s == 200 and len(mine1) == 1 and mine1[0]["kind"] == "WINNER"
      and mine1[0]["declared"] is True, f"got {s} {b}")
s, _ = J(f"/events/{EV}/certificate", P)
check("outsider gets no certificate (404)", s == 404, f"got {s}")

# ---- export ----
def get_zip(header, qs):
    r = urllib.request.Request(BASE + f"/events/{EV}/export{qs}", method="GET")
    if header:
        n, _, v = header.partition(":")
        r.add_header(n.strip(), v.strip())
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

s, body = get_zip(O, "")
zf = zipfile.ZipFile(io.BytesIO(body)) if s == 200 else None
names = sorted(zf.namelist()) if zf else []
want = sorted(["participants.csv", "organizers.csv", "judges.csv", "tracks.csv",
               "prizes.csv", "rubric.csv", "teams.csv", "projects.csv",
               "evaluations.csv", "assignments.csv", "ballots.csv", "comments.csv",
               "results.csv", "audit.csv"])
check("export all = 14 CSVs", s == 200 and names == want, f"got {s} {names}")
ok = True
if zf:
    for n in names:
        text = zf.read(n).decode()
        lines = [l for l in text.splitlines() if l.strip()]
        ok = ok and len(lines) >= 1  # header at minimum
    parts = zf.read("participants.csv").decode()
    ok = ok and f"t4u1-{RUN}@local.test" in parts
    bal = zf.read("ballots.csv").decode()
    ok = ok and f"t4v-{RUN}@local.test" in bal
    res = zf.read("results.csv").decode()
    ok = ok and "T4 P1" in res
check("CSVs carry real rows (participants, ballot, results)", ok)
s, body = get_zip(O, "?datasets=tracks,rubric")
zf = zipfile.ZipFile(io.BytesIO(body)) if s == 200 else None
check("export subset (2 files)", s == 200 and sorted(zf.namelist()) == ["rubric.csv", "tracks.csv"], f"got {s}")
s, _ = get_zip(O, "?datasets=bogus")
check("export bad dataset (422)", s == 422, f"got {s}")
s, _ = get_zip(P, "")
check("export organizer-only (403)", s == 403, f"got {s}")
s, _ = get_zip(None, "")
check("export needs login (401)", s == 401, f"got {s}")

print("FAILURES PRESENT" if any(not c for _, c, _ in results) else "ALL PASS")
