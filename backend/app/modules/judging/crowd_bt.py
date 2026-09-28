"""Hierarchical Bayesian Crowd-Bradley–Terry, MAP estimation (prompt_T2 §10).

Pure functions: comparisons in, thetas and reliabilities out. No database,
no framework — unit-testable anywhere with numpy/scipy.

Model (crowd_bt_architecture_poc_corrected.md):
    P_j(A > B) = sigmoid(r_j * (theta_A - theta_B)),  r_j = exp(log_r_j)
    log r_j ~ Normal(mu_j, sigma_j^2)   (mu_j, sigma_j from reliability priors)
    theta_i ~ Normal(0, THETA_SIGMA^2),  one reference project fixed at 0.

Fitted by BFGS with analytic gradient from the all-zeros start.
Sum-to-zero normalization is applied post-fit so reported thetas are
symmetric and comparable across recalculations.
Laplace uncertainty uses the FULL inverse-Hessian covariance (theta block),
propagated through the centering shift — including the reference project,
which is no longer special after normalization. Callers get honest marginal
stds for every project, usable for confidence intervals and close calls.
"""
import math

THETA_SIGMA = 2.0
MODEL_VERSION = "crowd-bt-map-v3"
CLOSE_CALL_THRESHOLD = 0.90   # P(A>B) below this → "close call", not a verdict


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def fit(comparisons: list, project_ids: list, judge_ids: list, *,
        reference_project: str, priors: dict,
        theta_sigma: float = THETA_SIGMA) -> dict:
    """MAP fit with analytic gradient, Laplace uncertainty, and sum-to-zero
    normalization.

    comparisons: [{judge_user_id, winner_project_id, loser_project_id, weight}].
    priors: {judge: (mu, sigma)}.

    Returns:
        thetas          — {project_id: float}, sum-to-zero normalized
        theta_stds      — {project_id: float}, Laplace marginal stds: the full
                          theta-block covariance propagated through the
                          centering shift, so the reference project gets a
                          real std like everyone else
        log_reliabilities — {judge_id: float}
        reliabilities   — {judge_id: float}
        success         — bool (optimizer convergence flag)
        converged       — bool (same as success, kept for clarity)
        optimizer_diagnostics — {nit, njev, message, grad_norm}
        close_calls     — [{project_a, project_b, p_a_beats_b}] adjacent-rank
                          pairs where P < CLOSE_CALL_THRESHOLD
        n_comparisons   — int
        reference_project — str (fit-time pin; after normalization all
                            thetas are shifted, reference is no longer 0)
        model_version   — str
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
    n_judges = len(judges)
    ts2 = theta_sigma ** 2

    # ------------------------------------------------------------------ #
    # Negative log-posterior and analytic gradient                        #
    # ------------------------------------------------------------------ #
    def _nlp_and_grad(x):
        theta = x[:n_free]
        log_r = x[n_free:]
        r = np.exp(log_r)

        tw = np.where(wdx == -1, 0.0, theta[wdx])
        tl = np.where(ldx == -1, 0.0, theta[ldx])
        delta = tw - tl                          # theta_winner - theta_loser

        z = np.clip(r[jdx] * delta, -50, 50)
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-12, 1.0 - 1e-12)

        # --- NLP ---
        nlp = float(-np.sum(w * np.log(p)))
        nlp += float(0.5 * np.sum((theta / theta_sigma) ** 2))
        nlp += float(0.5 * np.sum(((log_r - mu) / sig) ** 2))

        # --- Gradient ---
        # ∂NLP/∂z_k = w_k * (p_k - 1)
        resid = w * (p - 1.0)                    # shape (n_comparisons,)
        r_per_obs = r[jdx]

        # ∂NLP/∂theta_i: winner gets +resid*r, loser gets -resid*r
        g_theta = np.zeros(n_free)
        mask_w = wdx != -1
        mask_l = ldx != -1
        np.add.at(g_theta, wdx[mask_w], (resid * r_per_obs)[mask_w])
        np.add.at(g_theta, ldx[mask_l], -(resid * r_per_obs)[mask_l])
        g_theta += theta / ts2                   # prior gradient

        # ∂NLP/∂log_r_j: ∂z_k/∂log_r_j = z_k (chain through exp)
        g_logr = np.zeros(n_judges)
        np.add.at(g_logr, jdx, resid * z)
        g_logr += (log_r - mu) / (sig ** 2)     # prior gradient

        return nlp, np.concatenate([g_theta, g_logr])

    def nlp_only(x):
        return _nlp_and_grad(x)[0]

    def grad_only(x):
        return _nlp_and_grad(x)[1]

    x0 = np.zeros(n_free + n_judges)
    res = minimize(nlp_only, x0, jac=grad_only, method="BFGS")

    xv = res.x
    theta_arr = xv[:n_free]
    log_r_arr = xv[n_free:]

    # --- Laplace uncertainty: full covariance propagated through centering ---
    # BFGS stores the approximate inverse Hessian H over [theta, log_r].
    # Reported thetas are theta'_i = theta_i - m with m = mean(all thetas,
    # reference 0 included), so marginal variances must propagate through m:
    #   Var(theta'_i) = S_ii + Var(m) - 2*Cov(theta_i, m),
    #   Var(m) = sum(S)/P^2,  Cov(theta_i, m) = row_sum_i/P,
    # with S the theta block of H and P = n_free + 1. The reference project
    # (a constant 0 pre-shift) gets Var(m): it moves with the shift exactly
    # like everything else, so a zero there would understate every pairwise
    # probability involving it. Diagonal-only propagation would miss the
    # Cov(theta_i, m) terms for all projects, not just the reference.
    n_dim = n_free + n_judges
    hess_inv = np.asarray(res.hess_inv, dtype=float) if hasattr(res, "hess_inv") else None
    if (hess_inv is not None and hess_inv.shape == (n_dim, n_dim)
            and np.all(np.isfinite(hess_inv))):
        H = 0.5 * (hess_inv + hess_inv.T)   # enforce symmetry against drift
        S = H[:n_free, :n_free]
        P = n_free + 1
        row_sums = S.sum(axis=1)
        var_m = float(S.sum() / (P ** 2))   # >= 0 when S is PSD
        var_shifted = np.diag(S) + var_m - 2.0 * row_sums / P
        var_shifted = np.maximum(var_shifted, 0.0)   # clamp float dust
        ref_var = max(var_m, 0.0)
    else:
        # No usable Hessian (should not happen with BFGS): fall back to
        # zeros rather than fabricating uncertainty. rank() then treats
        # gaps heuristically, documented there.
        var_shifted = np.zeros(n_free)
        ref_var = 0.0
    theta_std_arr = np.sqrt(var_shifted)
    ref_std = math.sqrt(ref_var)

    # --- Sum-to-zero normalization ---
    # BT likelihood only depends on differences; subtracting the mean
    # makes reported thetas symmetric and stable across recalculations.
    # The reference project theta (fixed at 0) participates in the mean.
    ref_theta = 0.0
    all_theta_vals = np.append(theta_arr, ref_theta)
    mean_theta = float(np.mean(all_theta_vals))
    theta_arr_norm = theta_arr - mean_theta
    ref_theta_norm = ref_theta - mean_theta
    # NOTE: variances are NOT shift-invariant here — the shift m is itself a
    # function of the fitted params, so its variance propagates (done above).
    # Only a fixed constant shift would leave variances unchanged.

    # Build output dicts
    thetas: dict = {reference_project: ref_theta_norm}
    theta_stds: dict = {reference_project: float(ref_std)}
    for i, pid in enumerate(free):
        thetas[pid] = float(theta_arr_norm[i])
        theta_stds[pid] = float(theta_std_arr[i])

    log_rs = {j: float(log_r_arr[k]) for k, j in enumerate(judges)}

    # Optimizer diagnostics
    try:
        gn = float(np.linalg.norm(res.jac)) if res.jac is not None else None
    except Exception:
        gn = None
    diag = {
        "nit": int(res.nit),
        "njev": int(res.njev),
        "message": str(res.message),
        "grad_norm": gn,
    }

    return {
        "thetas": thetas,
        "theta_stds": theta_stds,
        "log_reliabilities": log_rs,
        "reliabilities": {j: float(math.exp(v)) for j, v in log_rs.items()},
        "success": bool(res.success),
        "converged": bool(res.success),
        "optimizer_diagnostics": diag,
        "n_comparisons": len(comparisons),
        "reference_project": reference_project,
        "model_version": MODEL_VERSION,
    }


def rank(thetas: dict, theta_stds: dict | None = None) -> list:
    """Competition ranking (1224 style): sorted by theta desc, equal thetas
    share a rank. Adjacent-rank close calls are flagged when theta_stds is
    supplied: P(A>B) = sigmoid((θ_A-θ_B)/sqrt(σ²_A+σ²_B)).

    Returns list of dicts with: project_id, theta, theta_std, rank,
    confidence ('High'|'Low'), and for adjacent pairs where P<threshold:
    a 'close_call_with_next' flag and 'p_beats_next' probability.
    """
    order = sorted(thetas.items(), key=lambda kv: kv[1], reverse=True)
    stds = theta_stds or {}
    out, last_theta, last_rank = [], None, 0
    for i, (pid, theta) in enumerate(order, start=1):
        if last_theta is None or not math.isclose(theta, last_theta, rel_tol=0, abs_tol=1e-9):
            last_rank = i
        std = stds.get(pid, 0.0)
        out.append({
            "project_id": pid,
            "theta": theta,
            "theta_std": std,
            "rank": last_rank,
        })
        last_theta = theta

    # Annotate close calls between adjacent ranked projects.
    # Assumption, stated plainly: the two thetas are treated as INDEPENDENT
    # Gaussians, so Var(θ_A − θ_B) = σ²_A + σ²_B. The Laplace posterior does
    # not factor this way — strengths share the reference pin and the
    # sum-to-zero shift, so off-diagonal covariance exists and is dropped
    # here. Effect: probabilities ignore correlation and can err either way;
    # they remain useful as a flagging heuristic, not as calibrated odds.
    # Do not build betting-grade claims on p_beats_next without a correlated
    # treatment (multivariate draw or full-covariance contrast variance).
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        sa, sb = a["theta_std"], b["theta_std"]
        combined_std = math.sqrt(sa ** 2 + sb ** 2) if (sa > 0 or sb > 0) else 0.0
        if combined_std > 0:
            p_a_beats_b = _sigmoid((a["theta"] - b["theta"]) / combined_std)
        else:
            # No uncertainty info — assume decisive if gap is large, unknown if tiny
            gap = abs(a["theta"] - b["theta"])
            p_a_beats_b = _sigmoid(gap * 2)   # heuristic; gap*2 ~ moderate sharpness
        a["p_beats_next"] = float(p_a_beats_b)
        a["close_call_with_next"] = p_a_beats_b < CLOSE_CALL_THRESHOLD
        # Confidence on this project's rank: low if it's in a close-call pair
        a["confidence"] = "Low" if p_a_beats_b < CLOSE_CALL_THRESHOLD else "High"

    # Last project: no "next", but flag confidence based on p_beaten_by_prev
    if out:
        last = out[-1]
        if len(out) > 1:
            prev = out[-2]
            last["confidence"] = "Low" if prev.get("close_call_with_next") else "High"
        else:
            last["confidence"] = "High"
        last.setdefault("p_beats_next", None)
        last.setdefault("close_call_with_next", False)

    return out
