"""Community voting math (T3), pure functions — no DB, no time.

Rule, in plain words: every voter gets 10 votes to distribute across any
number of projects, total allocations never above 10. Influence follows a
square-root curve — casting n votes on one project carries √n influence —
so a loud minority piling everything onto one project gains less than
broad support spread around: √9 + √1 beats √10 every time
(3 + 1 = 4 > 3.16…).

Tally sums influence per project. Ordering is deterministic: influence
desc, project id asc. Ranks are competition "1224" (ties share, next
skips), same convention as judging.
"""
from __future__ import annotations

import math

VOTE_CAP = 10  # total votes one voter may distribute, all projects combined
MAX_VOTES_PER_PROJECT = 10  # unreachable under the cap, kept as a backstop


def influence(votes: int) -> float:
    """Voice a block of votes carries."""
    return math.sqrt(votes)


def check_budget(allocations: dict[str, int], budget: int = VOTE_CAP) -> dict:
    """Validate one voter's full allocation. Returns used/remaining, or
    raises ValueError naming the problem (routes translate to 422)."""
    clean: dict[str, int] = {}
    for pid, v in (allocations or {}).items():
        if isinstance(v, bool):
            raise ValueError(f"votes for {pid} must be a whole number")
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"votes for {pid} must be a whole number")
        if isinstance(v, float) and not v.is_integer():
            raise ValueError(f"votes for {pid} must be a whole number")
        if n < 0:
            raise ValueError(f"votes for {pid} cannot be negative")
        if n > MAX_VOTES_PER_PROJECT:
            raise ValueError(
                f"at most {MAX_VOTES_PER_PROJECT} votes per project")
        if n:
            clean[pid] = n
    used = sum(clean.values())
    if used > budget:
        raise ValueError(
            f"that is {used} votes but you only have {budget} — "
            f"take {used - budget} back from somewhere")
    return {"allocations": clean, "spent": used, "remaining": budget - used}


def tally(ballots: list[dict]) -> list[dict]:
    """Rank projects by summed influence. Input rows: {project_id, votes}.
    Output: [{project_id, votes, influence, rank}].

    The sqrt applies PER BALLOT ROW (each voter's block), then sums per
    project — never sqrt-of-total. Collapsing first would let one voter's
    9 votes masquerade as broad √9 support instead of a single voice;
    per-row sqrt keeps every voice distinct, which is the entire point."""
    raw: dict[str, int] = {}
    inf: dict[str, float] = {}
    for b in ballots:
        v = int(b["votes"])
        if v <= 0:
            continue
        pid = b["project_id"]
        raw[pid] = raw.get(pid, 0) + v
        inf[pid] = inf.get(pid, 0.0) + influence(v)
    ordered = sorted(inf.items(), key=lambda kv: (-kv[1], kv[0]))
    out, prev_inf, rank = [], None, 0
    for i, (pid, total_inf) in enumerate(ordered):
        if prev_inf is None or not math.isclose(total_inf, prev_inf, abs_tol=1e-9):
            rank = i + 1
            prev_inf = total_inf
        out.append({"project_id": pid, "votes": raw[pid],
                    "influence": round(total_inf, 4), "rank": rank})
    return out
