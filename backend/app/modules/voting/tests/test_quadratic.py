"""Unit tests for the voting math: 10-vote cap, validation, sqrt tally."""
import math

import pytest

from app.modules.voting.quadratic import VOTE_CAP, check_budget, influence, tally


def test_ten_votes_distributed_freely():
    out = check_budget({"a": 3, "b": 7})
    assert out == {"allocations": {"a": 3, "b": 7}, "spent": 10, "remaining": 0}


def test_all_ten_on_one_project_allowed():
    out = check_budget({"a": 10})
    assert out["spent"] == 10 and out["remaining"] == 0


def test_eleven_total_refused_with_numbers():
    with pytest.raises(ValueError, match="11.*10|take 1 back"):
        check_budget({"a": 10, "b": 1})


def test_zeros_and_empties_dropped():
    assert check_budget({"a": 0, "b": 3}) == {
        "allocations": {"b": 3}, "spent": 3, "remaining": VOTE_CAP - 3}
    assert check_budget({})["spent"] == 0


def test_negative_and_fractional_refused():
    with pytest.raises(ValueError, match="[Nn]egative"):
        check_budget({"a": -1})
    with pytest.raises(ValueError, match="whole number"):
        check_budget({"a": 2.5})
    with pytest.raises(ValueError, match="whole number"):
        check_budget({"a": "lots"})


def test_per_project_cap():
    with pytest.raises(ValueError, match="at most 10"):
        check_budget({"a": 11})


def test_spread_beats_pile():
    # The whole point of the square root: 9+1 outranks a straight 10.
    assert influence(9) + influence(1) > influence(10)
    assert influence(9) + influence(1) == pytest.approx(4.0)


def test_tally_sums_influence_and_orders():
    rows = [{"project_id": "b", "votes": 3}, {"project_id": "a", "votes": 9},
            {"project_id": "b", "votes": 1}, {"project_id": "c", "votes": 0}]
    got = tally(rows)
    assert [(r["project_id"], r["votes"], r["rank"]) for r in got] == [
        ("a", 9, 1), ("b", 4, 2)]
    assert got[0]["influence"] == pytest.approx(3.0)
    # Per-row sqrt summed: √3 + √1 ≈ 2.7321. sqrt-of-total would say 2.0 —
    # this assertion pins the distinction (one voice ≠ broad support).
    assert got[1]["influence"] == pytest.approx(2.7321, abs=1e-3)


def test_tally_ties_share_1224_ranks():
    rows = [{"project_id": "b", "votes": 4}, {"project_id": "a", "votes": 4},
            {"project_id": "c", "votes": 1}]
    got = tally(rows)
    assert [(r["project_id"], r["rank"]) for r in got] == [("a", 1), ("b", 1), ("c", 3)]


def test_tally_empty():
    assert tally([]) == []
