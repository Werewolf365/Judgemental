"""Unit tests for the Crowd-BT MAP fitter (v2: analytic gradient, Laplace, sum-to-zero).

The headline test replays the six-project reference subset end to end
(fixtures → weighted scores → pairs → fit) and asserts agreement with the
architecture's documented MAP outputs. Everything else pins the model's
contract: positivity, priors, reference constraint, determinism, uncertainty.

Sum-to-zero normalization: v2 subtracts the mean of all thetas post-fit, so
the pinned absolute values shift but the orderings and pairwise differences
are preserved. Tests now assert ORDER and DIFFERENCES, not raw magnitudes.
"""
import math

import pytest

from app.modules.judging import crowd_bt
from app.modules.judging.pairwise import connected_components, generate_pairs
from app.modules.judging.tests.test_pairwise import POC_PROJECTS, POC_WEIGHTS, _poc_rows

# Documented ORDERINGS (crowd doc §15/§16). The full project order and the
# full judge-reliability order both match exactly — this is invariant under
# sum-to-zero normalization.
EXPECTED_THETA_ORDER = ["prj_07", "prj_02", "prj_12", "prj_03", "prj_04", "prj_06"]
EXPECTED_R_ORDER = ["jdg_26", "jdg_21", "jdg_22", "jdg_24", "jdg_12", "jdg_19"]

# Pinned pairwise DIFFERENCES from the corrected model optimum. Under sum-to-
# zero the absolute values shift, but differences are invariant. Verified via
# multi-start and L-BFGS-B showing unique optimum.
# (values derived from v1 pinned: prj_07=0.91199, prj_12=0.0 → diff=0.91199)
PINNED_DIFFS = {
    ("prj_07", "prj_02"): 0.91199 - 0.641323,   # ≈ 0.2707
    ("prj_02", "prj_03"): 0.641323 - (-0.448659),  # ≈ 1.0900
    ("prj_03", "prj_04"): -0.448659 - (-1.052488),  # ≈ 0.6038
    ("prj_04", "prj_06"): -1.052488 - (-1.696218),  # ≈ 0.6437
}
PINNED_R = {
    "jdg_12": 1.044724, "jdg_19": 0.759891, "jdg_21": 1.142919,
    "jdg_22": 1.104834, "jdg_24": 1.094499, "jdg_26": 1.485692,
}
TOL = 0.01   # slightly wider than v1 due to analytic gradient path


def _fit_reference():
    pairs = generate_pairs(_poc_rows())
    judges = sorted({p["judge_user_id"] for p in pairs})
    priors = {j: (0.0, 0.60) for j in judges}
    return crowd_bt.fit(pairs, POC_PROJECTS, judges,
                        reference_project="prj_12", priors=priors)


def test_reference_ranking_order_matches_documented():
    out = _fit_reference()
    assert out["model_version"] == "crowd-bt-map-v3"
    ranking = crowd_bt.rank(out["thetas"], out.get("theta_stds"))
    order = [r["project_id"] for r in ranking]
    assert order == EXPECTED_THETA_ORDER


def test_reference_reliability_order_matches_documented():
    out = _fit_reference()
    order = sorted(out["reliabilities"], key=lambda j: out["reliabilities"][j], reverse=True)
    assert order == EXPECTED_R_ORDER


def test_pinned_pairwise_differences():
    """Pairwise theta differences are invariant under sum-to-zero shift."""
    out = _fit_reference()
    thetas = out["thetas"]
    for (pa, pb), want in PINNED_DIFFS.items():
        got = thetas[pa] - thetas[pb]
        assert got == pytest.approx(want, abs=TOL), f"{pa}-{pb}: got {got:.4f}, want {want:.4f}"


def test_pinned_reliabilities():
    out = _fit_reference()
    for j, want in PINNED_R.items():
        assert out["reliabilities"][j] == pytest.approx(want, abs=TOL), j


def test_sum_to_zero():
    """Post-fit thetas must sum to approximately zero (mean-centering)."""
    out = _fit_reference()
    theta_mean = sum(out["thetas"].values()) / len(out["thetas"])
    assert abs(theta_mean) < 1e-6, f"theta mean not near zero: {theta_mean}"


def test_theta_stds_returned_and_positive():
    """Laplace stds must be present and non-trivial for every project,
    reference included: after the centering shift the reference moves with
    the mean, so a zero there would understate its pairwise probabilities."""
    out = _fit_reference()
    assert "theta_stds" in out
    stds = out["theta_stds"]
    assert set(stds) == set(out["thetas"]), "stds must cover every project"
    assert all(v > 0 for v in stds.values()), \
        f"Some theta_stds are non-positive: {stds}"
    assert all(v == v and abs(v) != float("inf") for v in stds.values()), \
        "stds must be finite"


def test_rank_annotates_close_calls():
    """rank() with theta_stds must annotate p_beats_next and close_call_with_next."""
    out = _fit_reference()
    ranking = crowd_bt.rank(out["thetas"], out.get("theta_stds"))
    for r in ranking[:-1]:   # all but the last have a 'next'
        assert "p_beats_next" in r
        assert "close_call_with_next" in r
        assert "confidence" in r
        assert isinstance(r["p_beats_next"], float)
        assert 0.5 <= r["p_beats_next"] <= 1.0, \
            f"p_beats_next out of range for rank {r['rank']}: {r['p_beats_next']}"


def test_rank_last_project_has_no_next():
    out = _fit_reference()
    ranking = crowd_bt.rank(out["thetas"], out.get("theta_stds"))
    last = ranking[-1]
    assert last["p_beats_next"] is None
    assert last["close_call_with_next"] is False


def test_reliabilities_positive_and_reference_in_thetas():
    out = _fit_reference()
    assert all(v > 0 for v in out["reliabilities"].values())
    # Under sum-to-zero, prj_12 is no longer 0 — but it's still in the dict
    assert "prj_12" in out["thetas"]


def test_new_judge_neutral_prior_old_judge_historical_prior():
    pairs = generate_pairs(_poc_rows())
    judges = sorted({p["judge_user_id"] for p in pairs})
    priors = {j: (0.0, 0.60) for j in judges}
    priors["jdg_26"] = (0.5, 0.60)  # experienced judge: posterior became prior
    out = crowd_bt.fit(pairs, POC_PROJECTS, judges,
                       reference_project="prj_12", priors=priors)
    assert out["success"]
    assert all(v > 0 for v in out["reliabilities"].values())
    # A stronger prior mean pulls the posterior up vs the neutral run.
    neutral = _fit_reference()["reliabilities"]["jdg_26"]
    assert out["reliabilities"]["jdg_26"] > neutral


def test_fit_is_deterministic():
    assert _fit_reference()["thetas"] == _fit_reference()["thetas"]


def test_optimizer_diagnostics_present():
    out = _fit_reference()
    diag = out.get("optimizer_diagnostics", {})
    assert "nit" in diag
    assert "njev" in diag
    assert "message" in diag


def test_empty_comparisons_refused():
    with pytest.raises(ValueError):
        crowd_bt.fit([], POC_PROJECTS, [], reference_project="prj_12", priors={})


def test_held_out_pairs_predicted_above_chance():
    """3-fold cross-validation on synthetic data with known truth: fit on
    two folds, predict the third from fitted thetas. Passes only if the
    ranking generalizes — a regression net for predictive power, not just
    plumbing. Deterministic (fixed seed); needs no fixtures or database."""
    import itertools
    import random
    rnd = random.Random(7)
    true = {"p0": -2.0, "p1": -1.0, "p2": 0.0, "p3": 1.0, "p4": 2.0}
    judges = ["j0", "j1", "j2"]
    pairs = []
    for j in judges:
        for a, b in itertools.combinations(sorted(true), 2):
            d = (true[a] - true[b]) + rnd.gauss(0, 0.5)
            if abs(d) < 1e-9:
                continue
            w, l = (a, b) if d > 0 else (b, a)
            pairs.append({"judge_user_id": j, "winner_project_id": w,
                          "loser_project_id": l, "weight": 1.0,
                          "source_evaluation_ids": []})
    assert len(pairs) >= 30
    folds = [[], [], []]
    for i, p in enumerate(pairs):
        folds[i % 3].append(p)
    accs = []
    for k in range(3):
        train = [p for i, f in enumerate(folds) if i != k for p in f]
        held = folds[k]
        pids = sorted({p["winner_project_id"] for p in train} |
                      {p["loser_project_id"] for p in train})
        out = crowd_bt.fit(train, pids, judges, reference_project=pids[0],
                           priors={j: (0.0, 0.60) for j in judges})
        th = out["thetas"]
        correct = total = 0
        for c in held:
            w, l = c["winner_project_id"], c["loser_project_id"]
            if w not in th or l not in th:
                continue
            p = 1.0 / (1.0 + math.exp(-(th[w] - th[l])))
            total += 1
            if p > 0.5:
                correct += 1
        assert total > 0
        accs.append(correct / total)
    mean_acc = sum(accs) / len(accs)
    assert mean_acc > 0.65, f"held-out accuracy {mean_acc:.3f} {accs} — ranking does not generalize"


def test_missing_prior_refused():
    pairs = generate_pairs(_poc_rows())
    with pytest.raises(ValueError):
        crowd_bt.fit(pairs, POC_PROJECTS, ["jdg_26"],
                     reference_project="prj_12", priors={})
