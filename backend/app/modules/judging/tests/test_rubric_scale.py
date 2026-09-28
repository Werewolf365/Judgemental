"""DB-free tests for per-criterion scoring scales. Run inside the api image:
    docker compose exec -T api python -m pytest app/modules/judging/tests/test_rubric_scale.py -q
"""
import math
from types import SimpleNamespace

import pytest

from app.modules.judging import hier_score
from app.modules.judging.judge import _validate_scores
from app.modules.judging.schemas import CriterionIn


def _crit(cid, lo=0.0, hi=10.0, active=True):
    return SimpleNamespace(id=cid, is_active=active, score_lo=lo, score_hi=hi)


def test_schema_accepts_valid_scales():
    c = CriterionIn(name="Q", weight=50, score_lo=2, score_hi=5)
    assert (c.score_lo, c.score_hi) == (2, 5)
    c = CriterionIn(name="Q")
    assert c.score_lo is None and c.score_hi is None  # omitted resets to default


def test_schema_rejects_bad_scales():
    with pytest.raises(Exception):
        CriterionIn(name="Q", score_lo=5, score_hi=5)   # empty range
    with pytest.raises(Exception):
        CriterionIn(name="Q", score_lo=10, score_hi=2)  # inverted
    with pytest.raises(Exception):
        CriterionIn(name="Q", score_lo=float("nan"), score_hi=5)
    with pytest.raises(Exception):
        CriterionIn(name="Q", score_lo=0, score_hi=float("inf"))


def test_custom_scale_matches_rescaled_default():
    # 3.5 on a 2–5 scale == 5.0 on the 0–10 scale: same normalized position.
    w = {"a": 1.0}
    assert hier_score.score_evaluation(
        {"a": 3.5}, w, {"a": (2.0, 5.0)}) == pytest.approx(5.0)
    assert hier_score.score_evaluation({"a": 5.0}, w) == pytest.approx(5.0)
    # Mixed scales weight normalized positions, not raw magnitudes.
    got = hier_score.score_evaluation(
        {"a": 5.0, "b": 10.0}, {"a": 0.5, "b": 0.5}, {"a": (2.0, 5.0)})
    assert got == pytest.approx(0.5 * 10.0 + 0.5 * 10.0)


def test_judge_validation_uses_criterion_scale():
    crits = [_crit("a", 2.0, 5.0), _crit("b")]
    assert _validate_scores(crits, {"a": 2.0, "b": 10.0}) == {"a": 2.0, "b": 10.0}
    with pytest.raises(Exception):
        _validate_scores(crits, {"a": 1.9, "b": 5.0})   # below criterion scale
    with pytest.raises(Exception):
        _validate_scores(crits, {"a": 5.1, "b": 5.0})   # above criterion scale
    with pytest.raises(Exception):
        _validate_scores(crits, {"a": 3.0, "b": 10.1})  # default scale still enforced


def test_snapshot_formula_matches_old_on_defaults():
    # The normalize-first snapshot must reduce exactly to Σ w·score when
    # every criterion is 0–10: replicate the submit-time computation.
    clean = {"a": 9.0, "b": 8.0, "c": 10.0}
    weights = {"a": 0.4, "b": 0.35, "c": 0.25}
    scales = {"a": (0.0, 10.0), "b": (0.0, 10.0), "c": (0.0, 10.0)}
    total = sum(weights[c] * (clean[c] - scales[c][0]) / (scales[c][1] - scales[c][0])
                for c in weights) * 10.0
    assert total == pytest.approx(sum(clean[c] * weights[c] for c in weights))
    assert total == pytest.approx(hier_score.score_evaluation(clean, weights, scales))


def test_normalize_clamps_and_rejects():
    assert hier_score.normalize_criterion_score(99, 0, 10) == 1.0
    assert hier_score.normalize_criterion_score(-5, 0, 10) == 0.0
    assert math.isfinite(hier_score.normalize_criterion_score(3, 2, 5))
