"""Hierarchical Bayesian Crowd-Bradley–Terry, MAP estimation (prompt_T2 §10).

Pure functions: comparisons in, thetas and reliabilities out. No database,
no framework — unit-testable anywhere with numpy/scipy.

Model (crowd_bt_architecture_poc_corrected.md):
    P_j(A > B) = sigmoid(r_j * (theta_A - theta_B)),  r_j = exp(log_r_j)
    log r_j ~ Normal(mu_j, sigma_j^2)   (mu_j, sigma_j from reliability priors)
    theta_i ~ Normal(0, THETA_SIGMA^2),  one reference project fixed at 0.

Fitted by BFGS from the all-zeros start: fully deterministic for a given
input, which is what makes "final ranking is reproducible from stored
observations" (§19) literally true.
"""
import math

THETA_SIGMA = 2.0
MODEL_VERSION = "crowd-bt-map-v1"


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def fit(comparisons: list, project_ids: list, judge_ids: list, *,
        reference_project: str, priors: dict,
        theta_sigma: float = THETA_SIGMA) -> dict:
    """MAP fit. comparisons: [{judge_user_id, winner_project_id,
    loser_project_id, weight}]. priors: {judge: (mu, sigma)}.

    Weight is accepted but every caller must pass 1.0 (the CHECK constraint
    and generate_pairs guarantee it); it enters the likelihood exactly as
    stored so a persisted run replays bit-identically.
    """
    if reference_project not in project_ids:
        raise ValueError("reference project must be one of the fitted projects")
    if not comparisons:
        raise ValueError("no pairwise comparisons to fit")
    missing = [j for j in judge_ids if j not in priors]
    if missing:
        raise ValueError(f"missing reliability priors for judges: {missing[:3]}")

    import numpy as np
    from scipy.optimize import minimize

    free = [p for p in project_ids if p != reference_project]
    judges = list(judge_ids)
    w = np.array([float(c.get("weight", 1.0)) for c in comparisons])
    jdx = np.array([judges.index(c["judge_user_id"]) for c in comparisons])
    wdx = np.array([free.index(c["winner_project_id"])
                    if c["winner_project_id"] != reference_project else -1
                    for c in comparisons])
    ldx = np.array([free.index(c["loser_project_id"])
                    if c["loser_project_id"] != reference_project else -1
                    for c in comparisons])
    mu = np.array([priors[j][0] for j in judges])
    sig = np.array([priors[j][1] for j in judges])
    n_free = len(free)

    def nlp(x):
        # Reference project theta is fixed at 0: winner/loser indexes of -1
        # (the reference) contribute 0.0 via the np.where below, so the
        # reference never appears in the free vector at all.
        theta = x[:n_free]
        log_r = x[n_free:]
        r = np.exp(log_r)
        tw = np.where(wdx == -1, 0.0, theta[wdx])
        tl = np.where(ldx == -1, 0.0, theta[ldx])
        z = np.clip(r[jdx] * (tw - tl), -50, 50)
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-12, 1.0 - 1e-12)
        out = float(-np.sum(w * np.log(p)))
        out += float(0.5 * np.sum((x[:n_free] / theta_sigma) ** 2))
        out += float(0.5 * np.sum(((log_r - mu) / sig) ** 2))
        return out

    x0 = np.zeros(n_free + len(judges))
    res = minimize(nlp, x0, method="BFGS")
    xv = res.x
    thetas = {reference_project: 0.0}
    for i, pid in enumerate(free):
        thetas[pid] = float(xv[i])
    log_rs = {j: float(xv[n_free + k]) for k, j in enumerate(judges)}
    return {
        "thetas": thetas,
        "log_reliabilities": log_rs,
        "reliabilities": {j: float(math.exp(v)) for j, v in log_rs.items()},
        "success": bool(res.success),
        "n_comparisons": len(comparisons),
        "reference_project": reference_project,
        "model_version": MODEL_VERSION,
    }


def rank(thetas: dict, reference_project: str) -> list:
    """Dense... no — competition ranking ("1224" style ranks, ties share a
    rank): sorted by theta desc, equal thetas share the same rank number.
    The reference project's theta=0 is an origin, not a quality score, so it
    ranks wherever 0 falls."""
    order = sorted(thetas.items(), key=lambda kv: kv[1], reverse=True)
    out, last_theta, last_rank = [], None, 0
    for i, (pid, theta) in enumerate(order, start=1):
        if last_theta is None or not math.isclose(theta, last_theta, rel_tol=0, abs_tol=1e-9):
            last_rank = i
        out.append({"project_id": pid, "theta": theta, "rank": last_rank})
        last_theta = theta
    return out
