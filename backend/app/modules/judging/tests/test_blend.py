"""DB-free tests for the judge/crowd final-score blend. Run inside the api image:
    docker compose exec -T api python -m pytest app/modules/judging/tests/test_blend.py -q

Covers the new module only: normalize, blend, rank_scores, and the
maybe_blend gate off-paths (stub event, no DB touched). Live blend-on paths
are verified by probe, not here.
"""
import asyncio

import pytest

from app.modules.judging import blend
from app.modules.judging.schemas import JudgingConfigIn


def test_normalize_scales_to_unit():
    assert blend.normalize({"a": 10.0, "b": 20.0, "c": 30.0}) == {
        "a": 0.0, "b": 0.5, "c": 1.0}


def test_normalize_constant_maps_neutral():
    assert blend.normalize({"a": 5.0, "b": 5.0}) == {"a": 0.5, "b": 0.5}


def test_normalize_empty():
    assert blend.normalize({}) == {}


def test_blend_zero_crowd_is_judge_order():
    j = {"a": 2.0, "b": 1.0, "c": 0.0}
    v = {"c": 99.0, "b": 50.0, "a": 0.0}  # opposite order, must not matter
    out = blend.blend(j, v, 0)
    assert out["a"] > out["b"] > out["c"]


def test_blend_full_crowd_is_voter_order():
    j = {"a": 2.0, "b": 1.0, "c": 0.0}
    v = {"a": 0.0, "b": 5.0, "c": 9.0}
    out = blend.blend(j, v, 100)
    assert out["c"] > out["b"] > out["a"]


def test_blend_fifty_fifty_exact_values():
    # judge 10..30 -> 0, .5, 1; voter 0..100 -> 0, .5, 1 on same keys
    out = blend.blend({"a": 10.0, "b": 20.0, "c": 30.0},
                      {"a": 0.0, "b": 50.0, "c": 100.0}, 50)
    assert out == {"a": 0.0, "b": 0.5, "c": 1.0}


def test_blend_missing_voter_defaults_to_zero_raw():
    # b has no crowd support: raw 0 -> normalized 0, so at 50% it trails.
    out = blend.blend({"a": 0.0, "b": 10.0}, {"a": 100.0}, 50)
    assert out["a"] == pytest.approx(0.5)   # 0.5*0 + 0.5*1
    assert out["b"] == pytest.approx(0.5)   # 0.5*1 + 0.5*0
    # With three projects the missing-vote project provably trails:
    out3 = blend.blend({"a": 0.0, "b": 5.0, "c": 10.0}, {"a": 100.0, "c": 0.0}, 50)
    assert out3["b"] == pytest.approx(0.25)  # 0.5*0.5 + 0.5*0
    assert out3["a"] == out3["c"] > out3["b"]


def test_blend_clamps_weight():
    j = {"a": 1.0, "b": 0.0}
    assert blend.blend(j, {"a": 0.0, "b": 1.0}, 250) == blend.blend(j, {"a": 0.0, "b": 1.0}, 100)
    assert blend.blend(j, {"a": 0.0, "b": 1.0}, -40) == blend.blend(j, {"a": 0.0, "b": 1.0}, 0)


def test_rank_scores_competition_ties():
    ranks = {r["project_id"]: r["blended_rank"]
             for r in blend.rank_scores({"a": 0.9, "b": 0.9, "c": 0.1})}
    assert ranks == {"a": 1, "b": 1, "c": 3}  # 1224, not 1223


def test_config_schema_caps_weight():
    assert JudgingConfigIn(crowd_weight=30).crowd_weight == 30
    with pytest.raises(Exception):
        JudgingConfigIn(crowd_weight=101)
    with pytest.raises(Exception):
        JudgingConfigIn(crowd_weight=-1)


def _event(**kw):
    class E:
        voting_enabled = False
        crowd_blend_enabled = False
        crowd_weight = 30
    for k, v in kw.items():
        setattr(E, k, v)
    return E()


def test_gate_voting_off_returns_none():
    assert asyncio.run(blend.maybe_blend(None, _event())) is None


def test_gate_blend_off_returns_none():
    assert asyncio.run(blend.maybe_blend(None, _event(voting_enabled=True))) is None


def test_gate_zero_weight_returns_none():
    assert asyncio.run(blend.maybe_blend(
        None, _event(voting_enabled=True, crowd_blend_enabled=True, crowd_weight=0))) is None
