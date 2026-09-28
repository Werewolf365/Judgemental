"""Unit tests for the hierarchical Bayesian scoring edge-case model.

Pure math only: no database, no server. Run inside the api image:
    docker compose exec -T api python -m pytest app/modules/judging/tests/test_hier_score.py -q
"""
import math

import pytest

from app.modules.judging import hier_score


def test_normalize_and_weighted_total():
    assert hier_score.normalize_criterion_score(5, 0, 10) == pytest.approx(0.5)
    assert hier_score.normalize_criterion_score(10, 0, 10) == pytest.approx(1.0)
    assert hier_score.normalize_criterion_score(0, 0, 10) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        hier_score.normalize_criterion_score(float("nan"))
    # 40/35/25 weights, scores (9, 8, 10) -> 8.9 on the display scale.
    w = {"a": 0.40, "b": 0.35, "c": 0.25}
    assert hier_score.score_evaluation({"a": 9, "b": 8, "c": 10}, w) == pytest.approx(8.9)


def test_dynamic_rubrics():
    # Any count, any weights: 2 criteria 70/30 and 5 equal criteria.
    assert hier_score.score_evaluation({"a": 10, "b": 0}, {"a": 0.7, "b": 0.3}) == pytest.approx(7.0)
    w5 = {f"c{i}": 0.2 for i in range(5)}
    assert hier_score.score_evaluation({f"c{i}": 6 for i in range(5)}, w5) == pytest.approx(6.0)
    # Evaluation scored under a subset (deactivated criterion): renormalize
    # over what is present instead of refusing.
    assert hier_score.score_evaluation({"a": 8}, {"a": 0.4, "b": 0.6}) == pytest.approx(8.0)
    with pytest.raises(ValueError):
        hier_score.score_evaluation({"zzz": 5}, {"a": 1.0})
    with pytest.raises(ValueError):
        hier_score.score_evaluation({}, {"a": 1.0})


def _synth(seed=0, n_projects=8, judges=("J0", "J1", "J2", "J3"), per_judge=8):
    """Projects with known quality spread, judges with known severity."""
    import random
    rnd = random.Random(seed)
    true_theta = {f"p{i}": v for i, v in
                  enumerate([-3, -2, -1, -0.5, 0.5, 1, 2, 3][:n_projects])}
    true_b = {"J0": -1.0, "J1": -0.3, "J2": 0.3, "J3": 1.0}
    obs = []
    projs = sorted(true_theta, key=lambda p: -true_theta[p])
    for k, j in enumerate(judges):
        assigned = (projs[k % len(projs):] + projs[:k % len(projs)])[:per_judge]
        for p in assigned:
            obs.append({"project_id": p, "judge_id": j,
                        "score": true_theta[p] + true_b[j] + rnd.gauss(0, 0.3) + 5.0})
    return obs, true_theta, true_b


def test_recovers_quality_order_despite_judge_severity():
    obs, true_theta, _ = _synth()
    out = hier_score.fit(obs, seed=7)
    got = [r["project_id"] for r in out["ranking"]]
    want = sorted(true_theta, key=lambda p: -true_theta[p])
    assert got == want
    # Harsh judge corrected upward, lenient judge downward.
    assert out["judge_effects"]["J0"]["b_mean"] < out["judge_effects"]["J3"]["b_mean"]
    assert out["judge_effects"]["J0"]["b_mean"] < 0 < out["judge_effects"]["J3"]["b_mean"]


def test_single_judge_per_project_edge_case():
    # Exactly the edge case: 6 projects, 6 judges, one evaluation each.
    obs = [{"project_id": f"p{i}", "judge_id": f"J{i}",
            "score": v} for i, v in
           enumerate([9.5, 8.0, 6.5, 5.0, 3.5, 1.5])]
    out = hier_score.fit(obs, seed=1)
    got = [r["project_id"] for r in out["ranking"]]
    assert got == ["p0", "p1", "p2", "p3", "p4", "p5"]
    # One observation per judge -> effects shrunk near zero, uncertainty honest.
    for j, e in out["judge_effects"].items():
        assert abs(e["b_mean"]) < 0.5
    for r in out["ranking"]:
        assert r["likely_range"][0] <= r["score"] <= r["likely_range"][1]
        assert 0.0 <= r["p_top"] <= 1.0
        assert r["confidence"] in ("High", "Medium", "Low")


def test_partial_pooling_shrinks_lonely_judges():
    # Same raw deviation, different evidence: busy judge keeps most of it,
    # lonely judge is shrunk toward zero.
    obs = []
    for i in range(6):
        obs.append({"project_id": f"q{i}", "judge_id": "BUSY", "score": 8.0})
    obs.append({"project_id": "solo", "judge_id": "LONELY", "score": 8.0})
    for i in range(6):
        obs.append({"project_id": f"r{i}", "judge_id": "OTHER", "score": 5.0})
    out = hier_score.fit(obs, seed=3)
    assert abs(out["judge_effects"]["LONELY"]["b_mean"]) < abs(
        out["judge_effects"]["BUSY"]["b_mean"]) + 1e-9


def test_deterministic_and_uncertainty_sane():
    obs, _, _ = _synth(seed=11)
    a = hier_score.fit(obs, seed=42)
    b = hier_score.fit(obs, seed=42)
    assert a["ranking"] == b["ranking"]
    c = hier_score.fit(obs, seed=43)
    # Different seed -> Monte-Carlo jitter only, means identical.
    assert a["theta_mean"] == c["theta_mean"]
    for r in a["ranking"]:
        lo, hi = r["likely_range"]
        assert lo < hi
    # Top-K probabilities: exactly K projects hold most of the mass.
    K = a["top_k"]
    assert sum(r["p_top"] for r in a["ranking"]) == pytest.approx(K, abs=0.15)


def test_recommendations_prioritize_boundary():
    # Top-2 boundary itself is a coin flip (8.9 vs 8.8); the 9.0/8.9 pair is
    # also close but safely inside. Boundary must come first.
    obs = [{"project_id": f"p{i}", "judge_id": f"J{i}", "score": v}
           for i, v in enumerate([9.0, 8.9, 8.8, 4.9, 1.0])]
    out = hier_score.fit(obs, seed=5, top_k=2)
    recs = hier_score.recommend_extra_judging(out)
    assert recs, "close pairs must produce recommendations"
    assert all("reason" in r and "project_a" in r and "project_b" in r for r in recs)
    first = recs[0]
    assert first["boundary"] is True
    assert {first["project_a"], first["project_b"]} == {"p1", "p2"}


def test_refuses_empty_and_nonfinite():
    with pytest.raises(ValueError):
        hier_score.fit([])
    with pytest.raises(ValueError):
        hier_score.fit([{"project_id": "p", "judge_id": "j", "score": float("nan")}])
    with pytest.raises(ValueError):
        hier_score.fit([{"project_id": "p", "judge_id": "j", "score": float("inf")}])


def test_version_is_distinct_from_crowd_bt():
    from app.modules.judging import crowd_bt
    assert hier_score.MODEL_VERSION != crowd_bt.MODEL_VERSION


def test_apply_swap_interchanges_two_ranks():
    assert hier_score.apply_swap(["a", "b", "c"], "a", "c") == ["c", "b", "a"]
    assert hier_score.apply_swap(["a", "b", "c"], "b", "c") == ["a", "c", "b"]
    # Input untouched, double swap restores.
    order = ["a", "b", "c"]
    once = hier_score.apply_swap(order, "a", "b")
    assert order == ["a", "b", "c"]
    assert hier_score.apply_swap(once, "a", "b") == ["a", "b", "c"]
    with pytest.raises(ValueError):
        hier_score.apply_swap(["a", "b"], "a", "a")
    with pytest.raises(ValueError):
        hier_score.apply_swap(["a", "b"], "a", "zzz")
