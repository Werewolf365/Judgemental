#!/usr/bin/env python3
"""Delete throwaway test-probe data, keep real data.

Removes events created by scripts/check_t1.py, check_t2.py and check_t3.py
(per-run slugs like t2-probe-*, t3-probe-*, scope-probe-tmp, plus the stray
'noj' draft) and the throwaway users those runs registered
(t2probe*@local.test, t3u2-*@local.test, t2repj*@local.test, ...).

NEVER touches:
  - evt_01 / sample-hack-2026 and anything from fixtures.json
  - demo-bt, demo-vote, demo-bayes (scripts/seed_demos.py)
  - admin/organizer/participant/judge @local.test demo accounts

Needs the db container running. Usage:
  python scripts/clean_probes.py            # delete
  python scripts/clean_probes.py --dry-run  # list only
"""
import subprocess
import sys

EVENT_PATTERNS = ("scope-probe-tmp", "t2-probe-%", "t2-hist-%",
                  "t2-repair-%", "t3-probe-%", "noj")
USER_PATTERNS = ("t2probe%@local.test", "t3u2-%@local.test",
                 "t2repj%@local.test", "t2@local.test", "t3@local.test",
                 "probe@local.test", "sybil%@local.test")

PROTECTED_SLUGS = ("sample-hack-2026", "demo-bt", "demo-vote", "demo-bayes")

DRY = "--dry-run" in sys.argv


def psql(sql):
    p = subprocess.run(
        ["docker", "compose", "exec", "-T", "db",
         "psql", "-U", "dogfood", "-d", "dogfood",
         "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", "-c", sql],
        capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr.strip() or "psql failed")
        raise SystemExit(1)
    return [l for l in p.stdout.splitlines() if l.strip()]


def like_list(col, patterns):
    return " OR ".join(f"{col} LIKE '{p}'" for p in patterns)


print("probe events:")
evs = psql(
    "SELECT slug FROM events WHERE "
    + like_list("slug", EVENT_PATTERNS) + " ORDER BY slug;")
bad = [s for s in evs if s in PROTECTED_SLUGS]
if bad:
    print(f"REFUSING: protected slug matched: {bad}")
    raise SystemExit(1)
for s in evs:
    print(f"  {s}")
print("probe users:")
us = psql(
    "SELECT email_norm FROM users WHERE "
    + like_list("email_norm", USER_PATTERNS) + " ORDER BY email_norm;")
for u in us:
    print(f"  {u}")
if not evs and not us:
    print("nothing to clean")
    raise SystemExit(0)
if DRY:
    print("dry run — nothing deleted")
    raise SystemExit(0)

# Events first: children (teams, projects, ballots, comments, judging
# rows, organizer links) cascade off the event id.
n_ev = psql(
    "WITH del AS (DELETE FROM events WHERE "
    + like_list("slug", EVENT_PATTERNS) + " RETURNING id) "
    "SELECT count(*) FROM del;")
# Then users whose teams vanished with those events.
n_u = psql(
    "WITH del AS (DELETE FROM users WHERE "
    + like_list("email_norm", USER_PATTERNS) + " RETURNING id) "
    "SELECT count(*) FROM del;")
print(f"deleted {n_ev[0] if n_ev else 0} events, "
      f"{n_u[0] if n_u else 0} users")
