"""Within-judge pairwise preference generation (prompt_T2 §9).

Pure functions: no database, no framework. The database rows that feed these
are SUBMITTED evaluations with their snapshotted weighted_score, so history
can never be reinterpreted under later rubric edits.

The central invariant: every non-tied comparison carries weight 1. Raw score
margins NEVER become evidence weights (that would hand louder judges more
influence purely for using a wider scale). The DB enforces this too with a
CHECK constraint; here it is simply never anything but 1.0.

Ties: two weighted scores within 1e-9 are a tie and produce NO observation —
never a forced winner. The epsilon exists because weights like 0.35/0.40 are
not binary-exact: two mathematically tied score vectors can differ by float
dust (~1e-16), and crowning a winner on dust would be fabrication.
"""
import itertools
import math

TIE_EPSILON = 1e-9


def generate_pairs(rows: list) -> list[dict]:
    """rows: dicts with judge_user_id, project_id, weighted_score,
    evaluation_id. Returns [{judge_user_id, winner_project_id,
    loser_project_id, weight=1.0, source_evaluation_ids:[a,b]}]."""
    by_judge: dict = {}
    for r in rows:
        by_judge.setdefault(r["judge_user_id"], []).append(r)
    out = []
    for judge, recs in by_judge.items():
        for a, b in itertools.combinations(recs, 2):
            sa, sb = a["weighted_score"], b["weighted_score"]
            if math.isclose(sa, sb, rel_tol=0, abs_tol=TIE_EPSILON):
                continue
            winner, loser = (a, b) if sa > sb else (b, a)
            out.append({
                "judge_user_id": judge,
                "winner_project_id": winner["project_id"],
                "loser_project_id": loser["project_id"],
                "weight": 1.0,
                "source_evaluation_ids": [winner["evaluation_id"], loser["evaluation_id"]],
            })
    return out


def connected_components(pairs: list[dict], project_ids: list) -> list[set]:
    """Undirected connectivity over projects linked by any comparison.

    More than one component means the losers/winners of separate groups
    cannot be placed on one common latent scale — the caller must refuse
    to fit rather than silently rank incomparable projects.
    """
    parent = {p: p for p in project_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for c in pairs:
        union(c["winner_project_id"], c["loser_project_id"])
    groups: dict = {}
    for p in project_ids:
        groups.setdefault(find(p), set()).add(p)
    return list(groups.values())
