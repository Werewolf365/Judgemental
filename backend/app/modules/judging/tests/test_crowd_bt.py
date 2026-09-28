"""Unit tests for the Crowd-BT MAP fitter.

The headline test replays the six-project reference subset end to end
(fixtures → weighted scores → pairs → fit) and asserts agreement with the
architecture's documented MAP outputs. Everything else pins the model's
contract: positivity, priors, reference constraint, determinism.
"""
import math

import pytest

from app.modules.judging import crowd_bt
from app.modules.judging.pairwise import connected_components, generate_pairs
from app.modules.judging.tests.test_pairwise import POC_PROJECTS, POC_WEIGHTS, _poc_rows

# Documented ORDERINGS (crowd doc §15/§16, reference = Open Beacon). The full
# project order and the full judge-reliability order both match exactly.
EXPECTED_THETA_ORDER = ["prj_07", "prj_02", "prj_12", "prj_03", "prj_04", "prj_06"]
EXPECTED_R_ORDER = ["jdg_26", "jdg_21", "jdg_22", "jdg_24", "jdg_12", "jdg_19"]

# Pinned unit-weight MAP optimum from THIS implementation (scipy 1.18.1,
# BFGS from zeros; verified the unique optimum via multi-start + L-BFGS-B).
# NOTE on the doc's magnitudes: the §15/§16 numbers (e.g. prj_07 +1.042,
# jdg_26 1.716) reproduce bit-near-exactly only under the REMOVED
# w = 1 + |margin| weighting — i.e. they encode the scale dependence §6
# deletes — so they cannot serve as reference values for the corrected
# model. These pinned values are the corrected model's optimum; the tight
# tolerance exists to catch any future change in the likelihood.
PINNED_THETAS = {
    "prj_02": 0.641323, "prj_03": -0.448659, "prj_04": -1.052488,
    "prj_06": -1.696218, "prj_07": 0.91199, "prj_12": 0.0,
}
PINNED_R = {
    "jdg_12": 1.044724, "jdg_19": 0.759891, "jdg_21": 1.142919,
    "jdg_22": 1.104834, "jdg_24": 1.094499, "jdg_26": 1.485692,
}
TOL = 0.005


def _fit_reference():
    pairs = generate_pairs(_poc_rows())
    judges = sorted({p["judge_user_id"] for p in pairs})
    priors = {j: (0.0, 0.60) for j in judges}
    return crowd_bt.fit(pairs, POC_PROJECTS, judges,
                        reference_project="prj_12", priors=priors)


def test_reference_ranking_order_matches_documented():
    out = _fit_reference()
    assert out["success"] and out["model_version"] == "crowd-bt-map-v1"
    order = [r["project_id"] for r in crowd_bt.rank(out["thetas"], "prj_12")]
    assert order == EXPECTED_THETA_ORDER


def test_reference_reliability_order_matches_documented():
    out = _fit_reference()
    order = sorted(out["reliabilities"], key=lambda j: out["reliabilities"][j], reverse=True)
    assert order == EXPECTED_R_ORDER


def test_pinned_unit_weight_optimum():
    """Regression pin on the corrected model's optimum (see note above on
    why the doc's magnitudes are not the reference)."""
    out = _fit_reference()
    for pid, want in PINNED_THETAS.items():
        assert out["thetas"][pid] == pytest.approx(want, abs=TOL), pid
    for j, want in PINNED_R.items():
        assert out["reliabilities"][j] == pytest.approx(want, abs=TOL), j


def test_reliabilities_positive_and_reference_fixed():
    out = _fit_reference()
    assert all(v > 0 for v in out["reliabilities"].values())
    assert out["thetas"]["prj_12"] == 0.0


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


def test_empty_comparisons_refused():
    with pytest.raises(ValueError):
        crowd_bt.fit([], POC_PROJECTS, [], reference_project="prj_12", priors={})


def test_missing_prior_refused():
    pairs = generate_pairs(_poc_rows())
    with pytest.raises(ValueError):
        crowd_bt.fit(pairs, POC_PROJECTS, ["jdg_26"],
                     reference_project="prj_12", priors={})
