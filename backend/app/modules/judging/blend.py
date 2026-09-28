"""Judge/crowd final-score blend.

Additional function only: nothing in crowd_bt, hier_score, pairwise, or the
voting tally is modified by this module. It consumes their outputs — judge
scores (BT thetas pre-rank, or bayes direct scores) and the crowd aggregate
(voting influence per project) — and combines them with the organizer's
weights:

    final(p) = w_judge * N(judge(p)) + w_voter * N(voter(p))

Each side is min-max normalized to [0, 1] over the ranked project set first,
because the raw scales are incomparable (BT thetas ~ [-3, 3], bayes scores
on 0..10, voter influence a sqrt-sum >= 0). Without normalization the side
with the wider numeric range would silently dominate no matter what weights
the organizer picked, making the weight UI a lie. Normalization preserves
each side's ordering exactly; only relative spacing within a side changes.

Missing-side policy (documented, tested):
- A ranked project with no crowd votes gets voter raw 0 (no support shown
  means no support counted), normalized with the rest.
- A voted project the judges never scored cannot be ranked at all and is
  excluded — the blend never invents a judge score.
- If a side is constant across projects it carries no information and maps
  to 0.5 for every project (neutral), instead of dividing by zero.

Ranks use competition "1224" (ties share a rank), matching crowd_bt.rank.
"""

from __future__ import annotations


def normalize(scores: dict[str, float]) -> dict[str, float]:
    """Min-max scale to [0, 1]. Constant input maps to 0.5 (neutral)."""
    if not scores:
        return {}
    lo = min(scores.values())
    hi = max(scores.values())
    if hi <= lo:
        return {pid: 0.5 for pid in scores}
    span = hi - lo
    return {pid: (v - lo) / span for pid, v in scores.items()}


def blend(judge_scores: dict[str, float], voter_scores: dict[str, float],
          crowd_weight_pct: float) -> dict[str, float]:
    """Weighted combination over the judge-scored project set.

    crowd_weight_pct in [0, 100]; w_voter = pct/100, w_judge = 1 - w_voter.
    voter_scores defaults missing projects to raw 0 before normalization.
    """
    w_v = min(100.0, max(0.0, float(crowd_weight_pct))) / 100.0
    w_j = 1.0 - w_v
    nj = normalize(judge_scores)
    nv = normalize({pid: float(voter_scores.get(pid, 0.0)) for pid in judge_scores})
    return {pid: w_j * nj[pid] + w_v * nv[pid] for pid in judge_scores}


def rank_scores(blended: dict[str, float]) -> list[dict]:
    """Competition-rank ("1224") the blended scores, best first."""
    ordered = sorted(blended.items(), key=lambda kv: (-kv[1], kv[0]))
    out: list[dict] = []
    last_score: float | None = None
    rank = 0
    for pos, (pid, score) in enumerate(ordered, start=1):
        if last_score is None or score != last_score:
            rank = pos
            last_score = score
        out.append({"project_id": pid, "blended_score": score,
                    "blended_rank": rank})
    return out


async def maybe_blend(db, event) -> dict | None:
    """Event-level gate + data fetch. Returns None when the blend must not
    run (voting off, blend off, zero crowd weight, or no crowd ballots);
    otherwise the blended ranking inputs. Read-only: never writes.

    The caller persists blended_score/blended_rank on its own result rows.
    """
    if not getattr(event, "voting_enabled", False):
        return None
    if not getattr(event, "crowd_blend_enabled", False):
        return None
    try:
        pct = float(getattr(event, "crowd_weight", 0) or 0)
    except (TypeError, ValueError):
        return None
    if pct <= 0:
        return None
    from app.modules.voting.routes import _rank_event
    ranking, turnout = await _rank_event(db, event)
    voter = {r["project_id"]: float(r["influence"]) for r in ranking}
    if not voter:
        return None
    return {"crowd_weight_pct": pct, "voter": voter,
            "n_voters": turnout.get("voters", 0),
            "n_ballots": turnout.get("ballots", 0)}
