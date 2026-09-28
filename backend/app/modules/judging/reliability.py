"""Historical judge reliability (prompt_T2 §11).

The Bayesian chain: historical posterior → current prior → current posterior.
After every SUCCEEDED model run the calculate flow appends one
judge_reliability_history row per judge; the latest row for a judge (from any
earlier event) becomes that judge's prior mean in the next competition.
A judge with no history gets the neutral prior (mu=0, sigma=0.60, i.e. r
centered at 1 — the POC's values).

Honest limitation, stated in code so nobody "fixes" it silently: MAP
estimation yields point estimates, never a posterior variance, so
posterior_sigma is stored NULL and the propagated prior always reuses the
neutral sigma. Only the MEAN carries across runs. Full posterior sampling
would be needed to propagate real uncertainty (crowd doc §20 lists exactly
this as future work).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import JudgeReliabilityHistory

NEUTRAL_MU = 0.0
NEUTRAL_SIGMA = 0.60


async def prior_for_judge(db: AsyncSession, judge_user_id: str,
                          event_id: str) -> dict:
    """(mu, sigma, source) for one judge in one event.

    Latest history row from any event wins. Rows from the SAME event are
    excluded so a recalculation cannot feed on its own output.
    """
    res = await db.execute(
        select(JudgeReliabilityHistory).where(
            JudgeReliabilityHistory.judge_user_id == judge_user_id,
            JudgeReliabilityHistory.event_id != event_id,
        ).order_by(JudgeReliabilityHistory.created_at.desc()).limit(1))
    row = res.scalar_one_or_none()
    if row is None:
        return {"mu": NEUTRAL_MU, "sigma": NEUTRAL_SIGMA, "source": "NEUTRAL"}
    return {"mu": row.posterior_mu, "sigma": NEUTRAL_SIGMA, "source": "HISTORICAL",
            "from_event_id": row.event_id, "from_run_id": row.model_run_id}
