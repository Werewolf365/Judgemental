"""Hierarchical Bayesian scoring model for the single-judge-per-project edge case.

The Bradley–Terry model (crowd_bt.py) is the primary ranking model and is NOT
touched by this module. It needs pairwise comparisons, which do not exist when
each project has only one assigned judge. This module covers exactly that case
by modelling absolute scores instead of pairwise orderings:

    R_i = theta_i + b_j + eps_i,   eps_i ~ Normal(0, sigma^2)

theta_i is latent project quality, b_j is judge severity/leniency, eps_i is
judging noise. Judge effects are partially pooled (b_j ~ Normal(0, tau^2),
theta_i ~ Normal(mu, s^2)) so a judge with few evaluations is automatically
shrunk toward the population instead of producing unstable corrections.

Pipeline:
    raw criterion scores
      -> per-criterion normalization to a common 0..1 scale
      -> organizer-weighted total (weights normalized to sum 1)
      -> x10 back to the familiar 0..10 display scale
      -> empirical-Bayes Gaussian fit (closed-form MAP + exact posterior
         covariance — the model is linear-Gaussian, so no optimizer is needed)
      -> posterior sampling (seeded, deterministic) for ranking uncertainty
      -> plain-language Top-K summary (no raw statistics in default fields).

Pure functions: no database, no framework — unit-testable anywhere with numpy.
Only numpy is required (no scipy).
"""

import hashlib
import math

MODEL_VERSION = "hier-bayes-score-v1"

# Score scale judges write against (judge.py SCORE_MIN/SCORE_MAX). Normalization
# divides by this range, so criteria on any future scale map to 0..1 first.
SCALE_MIN = 0.0
SCALE_MAX = 10.0

# Variance floor ((0.25 points)^2 on the 0..10 scale): below human
# discrimination. Prevents zero-variance collapse when every judge agrees or a
# judge has a single evaluation — posteriors stay honest instead of degenerate.
MIN_VAR = 0.0625

# Posterior draws for ranking probabilities. 4000 keeps Monte-Carlo SE under
# ~0.8pp at p=0.5 while staying milliseconds for competition-size problems.
N_SAMPLES = 4000

# "1224" competition-rank tie tolerance (same convention as crowd_bt.rank).
TIE_EPS = 1e-9

# Confidence bands on the probability that a project's displayed position is
# right. Conservative on purpose: a High means "safe to announce".
HIGH_P = 0.90
MED_P = 0.70


def normalize_criterion_score(value: float, lo: float = SCALE_MIN,
                              hi: float = SCALE_MAX) -> float:
    """One raw criterion score -> 0..1 on the common scale."""
    if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)):
        v = float(value)
    else:
        raise ValueError(f"score {value!r} is not a finite number")
    if hi <= lo:
        raise ValueError("criterion scale is empty")
    return min(1.0, max(0.0, (v - lo) / (hi - lo)))


def score_evaluation(raw_scores: dict, weights: dict,
                     lo: float = SCALE_MIN, hi: float = SCALE_MAX) -> float:
    """Normalized weighted total for one evaluation, back on the display scale.

    raw_scores: {criterion_id: number} as stored on the evaluation.
    weights: {criterion_id: normalized share} (sums to ~1, e.g. from
    service.resolve_weights). Only criteria present in BOTH maps count; their
    shares are renormalized so dynamic rubrics (any count, any weights,
    deactivated criteria) always produce a comparable total. Needs >= 1.
    """
    if not isinstance(raw_scores, dict) or not raw_scores:
        raise ValueError("evaluation has no criterion scores")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("no rubric weights to score against")
    present = [cid for cid in raw_scores if cid in weights]
    if not present:
        raise ValueError("evaluation scores match no active rubric criterion")
    wsum = sum(float(weights[c]) for c in present)
    if not math.isfinite(wsum) or wsum <= 0:
        raise ValueError("rubric weights are not positive")
    total = 0.0
    for cid in present:
        share = float(weights[cid]) / wsum
        total += share * normalize_criterion_score(raw_scores[cid], lo, hi)
    return lo + total * (hi - lo)


def _seed_from(value: str) -> int:
    return int(hashlib.sha256(str(value).encode()).hexdigest()[:16], 16) % (2 ** 31)


def fit(observations: list, *, seed: int = 0, n_samples: int = N_SAMPLES,
        top_k: int = 10) -> dict:
    """Fit R_i = theta_i + b_j + eps and derive ranking uncertainty.

    observations: [{project_id, judge_id, score}] with score on the display
    scale (see score_evaluation). Returns posterior means/SDs, exact posterior
    covariance diagonals via the closed form, seeded posterior draws, Top-K
    probabilities, neighbour pairwise probabilities, and confidence labels.
    Fully deterministic for a given (observations, seed).
    """
    if not observations:
        raise ValueError("no evaluations to model")
    import numpy as np

    for o in observations:
        if not math.isfinite(float(o["score"])):
            raise ValueError("evaluation score is not a finite number")

    projects = sorted({o["project_id"] for o in observations})
    judges = sorted({o["judge_id"] for o in observations})
    P, J, n = len(projects), len(judges), len(observations)
    if P < 1:
        raise ValueError("no projects to rank")

    pdx = {p: i for i, p in enumerate(projects)}
    jdx = {j: i for i, j in enumerate(judges)}
    y = np.array([float(o["score"]) for o in observations])
    pj = np.array([pdx[o["project_id"]] for o in observations])
    jj = np.array([jdx[o["judge_id"]] for o in observations])

    mu = float(np.mean(y))

    # --- Empirical-Bayes variance components (method of moments). ---
    # sigma^2 from pooled within-judge variance. This OVERestimates pure noise
    # (it also contains project differences within a judge), i.e. posteriors
    # are conservative — wider, never narrower, than the data strictly implies.
    judge_means = np.array([y[jj == j].mean() for j in range(J)])
    judge_ns = np.array([(jj == j).sum() for j in range(J)])
    ss_within = sum(float(np.sum((y[jj == j] - judge_means[j]) ** 2)) for j in range(J))
    dof = max(1, n - J)
    sigma2 = max(ss_within / dof, MIN_VAR)
    avg_n = n / J
    if J > 1:
        # Replication adjustment: a judge seen once provides no replication to
        # separate their severity from project quality (exactly confounded),
        # so severity variance scales with (nbar-1)/nbar — full shrinkage to
        # the prior at nbar=1, the plain method-of-moments estimate as
        # replication grows. Without this, single-evaluation judges would
        # absorb project-quality spread into huge spurious severity effects.
        rep = max(0.0, (avg_n - 1.0) / avg_n)
        tau2 = max((float(np.var(judge_means, ddof=1)) - sigma2 / avg_n) * rep,
                   MIN_VAR)
    else:
        # One judge total: no severity variation is estimable, b -> 0, and the
        # ranking reduces to (shrunk) score order. Honest, not degenerate.
        tau2 = MIN_VAR
    vtot = float(np.var(y, ddof=1)) if n > 1 else MIN_VAR
    s2 = max(vtot - tau2 - sigma2, MIN_VAR)

    # --- Closed-form Gaussian posterior. beta = [theta(P), b(J)]. ---
    # Q beta = c with Q = A'A/sigma^2 + diag(1/s^2, 1/tau^2); Cov = Q^-1.
    # Linear-Gaussian => exact, no optimizer, no convergence failure mode.
    dim = P + J
    XtX = np.zeros((dim, dim))
    Xty = np.zeros(dim)
    np.add.at(XtX, (pj, pj), 1.0)
    np.add.at(XtX, (P + jj, P + jj), 1.0)
    np.add.at(XtX, (pj, P + jj), 1.0)
    np.add.at(XtX, (P + jj, pj), 1.0)
    np.add.at(Xty, pj, y)
    np.add.at(Xty, P + jj, y)
    Q = XtX / sigma2
    Q[np.arange(P), np.arange(P)] += 1.0 / s2
    Q[np.arange(P, dim), np.arange(P, dim)] += 1.0 / tau2
    c = Xty / sigma2
    c[:P] += mu / s2
    try:
        beta = np.linalg.solve(Q, c)
        cov = np.linalg.inv(Q)
    except Exception:
        # Numerically singular (e.g. duplicate columns): tiny jitter on the
        # diagonal, still symmetric positive definite. Documented fallback.
        Q = Q + np.eye(dim) * 1e-6
        beta = np.linalg.solve(Q, c)
        cov = np.linalg.inv(Q)
    se = np.sqrt(np.maximum(np.diag(cov), 1e-12))

    theta_mean = beta[:P]
    theta_sd = se[:P]
    b_mean = beta[P:]
    b_sd = se[P:]

    # --- Posterior ranking probabilities (seeded draws). ---
    rng = np.random.default_rng(int(seed) % (2 ** 31))
    draws = rng.multivariate_normal(beta, cov, size=int(n_samples))
    th_draws = draws[:, :P]
    # rank 1 = best in each draw
    order = np.argsort(-th_draws, axis=1)
    ranks = np.empty_like(order)
    for s in range(int(n_samples)):
        r = np.empty(P, dtype=int)
        r[order[s]] = np.arange(1, P + 1)
        ranks[s] = r
    K = min(int(top_k), P)
    p_top = (ranks <= K).mean(axis=0)
    lo = np.percentile(th_draws, 5, axis=0)
    hi = np.percentile(th_draws, 95, axis=0)

    # Display order = posterior-mean order; competition "1224" ranks.
    mean_order = sorted(range(P), key=lambda i: theta_mean[i], reverse=True)
    rank_of = {}
    last_v, last_r = None, 0
    for pos, i in enumerate(mean_order, start=1):
        if last_v is None or abs(theta_mean[i] - last_v) > TIE_EPS:
            last_r = pos
        rank_of[projects[i]] = last_r
        last_v = theta_mean[i]

    # Neighbour pairwise probabilities P(upper above lower).
    pair_p = {}
    for a_pos in range(len(mean_order) - 1):
        a, b = mean_order[a_pos], mean_order[a_pos + 1]
        pair_p[(projects[a], projects[b])] = float(np.mean(th_draws[:, a] > th_draws[:, b]))

    def p_above(pid_a, pid_b):
        ia, ib = pdx[pid_a], pdx[pid_b]
        return float(np.mean(th_draws[:, ia] > th_draws[:, ib]))

    top_ids = [projects[i] for i in mean_order[:K]]
    top_set = set(top_ids)

    def confidence(pid):
        i = pdx[pid]
        stay = float(p_top[i]) if pid in top_set else float(1.0 - p_top[i])
        # Nearest-neighbour certainty: the weakest adjacent ordering involving
        # this project. Missing neighbours (ends / single project) don't count.
        neigh = []
        pos = mean_order.index(i)
        if pos > 0:
            up = projects[mean_order[pos - 1]]
            neigh.append(p_above(up, pid))
        if pos < len(mean_order) - 1:
            dn = projects[mean_order[pos + 1]]
            neigh.append(p_above(pid, dn))
        cert = min([stay] + neigh) if neigh else stay
        if cert >= HIGH_P:
            return "High", cert
        if cert >= MED_P:
            return "Medium", cert
        return "Low", cert

    summary = []
    for i in mean_order:
        pid = projects[i]
        label, cert = confidence(pid)
        # Close competitors: uncertain neighbours only (P < 0.95 either way).
        close = []
        pos = mean_order.index(i)
        for other_pos in (pos - 1, pos + 1):
            if 0 <= other_pos < len(mean_order):
                other = projects[mean_order[other_pos]]
                p = p_above(pid, other)
                if min(p, 1 - p) > 0.05:
                    close.append({"project_id": other, "p_above": round(p, 4)})
        close.sort(key=lambda d: -min(d["p_above"], 1 - d["p_above"]))
        summary.append({
            "project_id": pid,
            "rank": rank_of[pid],
            "score": round(float(theta_mean[i]), 4),
            "score_sd": round(float(theta_sd[i]), 4),
            "likely_range": [round(float(lo[i]), 2), round(float(hi[i]), 2)],
            "p_top": round(float(p_top[i]), 4),
            "confidence": label,
            "close_competitors": close[:2],
        })

    return {
        "model_version": MODEL_VERSION,
        "projects": projects,
        "judges": judges,
        "n_observations": n,
        "top_k": K,
        "hypers": {"mu": round(mu, 4), "sigma2": round(float(sigma2), 4),
                   "tau2": round(float(tau2), 4), "s2": round(float(s2), 4)},
        "theta_mean": {p: float(theta_mean[pdx[p]]) for p in projects},
        "theta_sd": {p: float(theta_sd[pdx[p]]) for p in projects},
        "judge_effects": {j: {"b_mean": float(b_mean[jdx[j]]),
                              "b_sd": float(b_sd[jdx[j]]),
                              "n": int(judge_ns[jdx[j]])} for j in judges},
        "ranking": summary,
        "seed": int(seed) % (2 ** 31),
        "n_samples": int(n_samples),
    }


def recommend_extra_judging(fit_out: dict, *, max_pairs: int = 5) -> list:
    """Prioritized extra-judging recommendations from a fit.

    Scores candidate adjacent pairs: boundary pairs (one side in the Top-K,
    one out) count double, then by closeness to a coin flip. Returns at most
    max_pairs pair-level items with plain-language reasons — the route layer
    turns these into per-project assignments with a suggested judge.
    """
    ranking = fit_out.get("ranking", [])
    K = fit_out.get("top_k", 10)
    in_top = {r["project_id"] for r in ranking if r["rank"] <= K}
    order = sorted(ranking, key=lambda r: (r["rank"], -r["score"]))
    cands = []
    for a_pos in range(len(order) - 1):
        a, b = order[a_pos], order[a_pos + 1]
        pab = None
        for cc in a.get("close_competitors", []):
            if cc["project_id"] == b["project_id"]:
                pab = cc["p_above"]
                break
        if pab is None:
            continue  # certain ordering — extra judging buys nothing here
        boundary = (a["project_id"] in in_top) != (b["project_id"] in in_top)
        value = (2.0 if boundary else 1.0) * (1.0 - abs(pab - 0.5) * 2.0)
        cands.append({
            "project_a": a["project_id"], "project_b": b["project_id"],
            "p_a_above_b": pab, "boundary": boundary, "_v": value,
        })
    cands.sort(key=lambda d: -d["_v"])
    out = []
    for d in cands[:max(1, int(max_pairs))]:
        a, b, pab = d["project_a"], d["project_b"], d["p_a_above_b"]
        pct = round(pab * 100)
        if d["boundary"]:
            reason = (f"Top-{K} boundary is uncertain: one of these two projects "
                      f"is in and the other is out, but they are close "
                      f"({pct}% likely the higher-ranked one stays above). "
                      f"One more judgment on either project settles it.")
        else:
            reason = (f"Neighbouring ranks are uncertain "
                      f"({pct}% likely the higher-ranked one stays above). "
                      f"Extra judging separates them.")
        out.append({"project_a": a, "project_b": b, "p_a_above_b": pab,
                    "boundary": d["boundary"], "reason": reason})
    return out


def apply_swap(order_ids: list, project_a: str, project_b: str) -> list:
    """Pure: interchange two projects in an ordered id list.

    Used for organizer manual rank resolution on uncertain close calls. Both
    ids must be present and distinct; anything else raises ValueError (the
    route layer turns this into a 4xx). Returns a NEW list, input untouched.
    """
    if project_a == project_b:
        raise ValueError("cannot swap a project with itself")
    if project_a not in order_ids or project_b not in order_ids:
        raise ValueError("both projects must be in this ranking")
    out = list(order_ids)
    ia, ib = out.index(project_a), out.index(project_b)
    out[ia], out[ib] = out[ib], out[ia]
    return out


def plain_summary_row(row: dict, top_k: int, n_total: int | None = None) -> str:
    """One plain-language sentence for a Top-K table row."""
    pct = round(row["p_top"] * 100)
    if n_total is not None and top_k >= n_total:
        # Small event: everything is Top-K, so the Top-K probability carries
        # no information — phrase confidence purely as positional certainty.
        if row["confidence"] == "High":
            base = f"Likely to hold around #{row['rank']}."
        elif row["confidence"] == "Medium":
            base = (f"Probably around #{row['rank']}, but this could move "
                    f"with more judging.")
        else:
            base = (f"Uncertain at #{row['rank']} — this position may change "
                    f"with more judging.")
    elif row["confidence"] == "High":
        base = f"Likely to stay around #{row['rank']} ({pct}% likely to stay in the Top {top_k})."
    elif row["confidence"] == "Medium":
        base = (f"Probably around #{row['rank']} ({pct}% likely to stay in the "
                f"Top {top_k}), but this could move with more judging.")
    else:
        base = (f"Uncertain at #{row['rank']} (only {pct}% likely to stay in the "
                f"Top {top_k}) — this position may change with more judging.")
    if row["close_competitors"]:
        cc = row["close_competitors"][0]
        base += f" Closest call: {round(cc['p_above'] * 100)}% likely to rank above its neighbour."
    return base
