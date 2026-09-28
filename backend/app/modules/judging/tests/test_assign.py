"""Pure unit tests for assignment selection and connectivity. No database.

Run inside the api image (code is baked in there):
    docker compose exec -T api python -m pytest app/modules/judging/tests/ -q
"""
from app.modules.judging.assign import (
    _fill_project_slots, _rank_candidates, _slot_ranking, components_of,
    min_bridge, shared_judge_count, single_shared_pairs)


def test_lowest_load_wins():
    ranked = _rank_candidates(
        {"a": 3, "b": 1, "c": 2}, {"a": set(), "b": set(), "c": set()},
        {"a", "b", "c"}, set())
    assert ranked == ["b", "c", "a"]


def test_overlap_breaks_load_ties():
    # b and c tie on load; b already serves two projects, so the newcomer
    # links into the graph through b rather than stranding with c.
    ranked = _rank_candidates(
        {"a": 5, "b": 1, "c": 1},
        {"a": {"p1"}, "b": {"p1", "p2"}, "c": set()},
        {"a", "b", "c"}, set())
    assert ranked == ["b", "c", "a"]


def test_user_id_breaks_remaining_ties_deterministically():
    loads = {"u2": 0, "u1": 0}
    live = {"u2": set(), "u1": set()}
    assert _rank_candidates(loads, live, {"u1", "u2"}, set()) == ["u1", "u2"]
    # Same inputs, same outputs — concurrent runs choose identically.
    assert _rank_candidates(loads, live, {"u1", "u2"}, set()) == ["u1", "u2"]


def test_excluded_judges_never_picked():
    ranked = _rank_candidates(
        {"a": 0, "b": 0}, {"a": set(), "b": set()}, {"a", "b"}, {"a"})
    assert ranked == ["b"]


def _state(loads, live, eligible):
    coverage = {}
    for j, ps in live.items():
        for p in ps:
            coverage.setdefault(p, set()).add(j)
    return {"loads": dict(loads), "live": {j: set(ps) for j, ps in live.items()},
            "eligible_ids": set(eligible), "coverage": coverage}


def test_first_slot_matches_plain_ranking():
    # With one slot the bridge key collapses: identical order, so
    # single-slot fills behave exactly as before.
    loads = {"a": 1, "b": 1, "c": 0}
    live = {"a": {"p1"}, "b": set(), "c": set()}
    st = _state(loads, live, {"a", "b", "c"})
    assert _slot_ranking(st, "px", []) == _rank_candidates(loads, live, {"a", "b", "c"}, set())


def test_later_slot_bridges_unrepresented_components():
    # pX already picked a (island {p1}); b serves another island, c serves
    # the same one. b wins despite tying c on load: it stitches islands.
    st = _state({"a": 1, "b": 1, "c": 1},
                {"a": {"p1"}, "b": {"p2"}, "c": {"p1"}},
                {"a", "b", "c"})
    assert _slot_ranking(st, "px", ["a"])[0] == "b"


def test_load_still_outranks_bridge():
    # b would bridge, but c is a full unit less loaded: balance first.
    st = _state({"a": 2, "b": 2, "c": 1},
                {"a": {"p1"}, "b": {"p2"}, "c": set()},
                {"a", "b", "c"})
    assert _slot_ranking(st, "px", ["a"])[0] == "c"


def test_redundancy_beats_attach_among_ties():
    # px has picked a. t serves q, which shares exactly judge a with
    # px-so-far (adding t completes a redundant bridge); c serves three
    # projects but completes nothing. One component throughout, all loads
    # tie, so neither balance nor bridging discriminates — redundancy picks
    # t despite c serving more projects overall.
    live = {"a": {"px", "q"}, "t": {"q", "w"}, "c": {"w", "x", "y"}}
    st = {"loads": {"a": 1, "t": 1, "c": 1},
          "live": {j: set(ps) for j, ps in live.items()},
          "eligible_ids": {"a", "t", "c"},
          "coverage": {"px": {"a"}, "q": {"a", "t"}, "w": {"t", "c"},
                       "x": {"c"}, "y": {"c"}}}
    ranked = _slot_ranking(st, "px", ["a"])
    assert ranked[0] == "t"


def test_components_single():
    live = {"j1": {"p1", "p2"}, "j2": {"p2", "p3"}}
    comps = components_of(live)
    assert comps == [{"p1", "p2", "p3"}]


def test_components_split_is_deterministic():
    # Coverage-1 islands: no shared judges, two components, stable order.
    live = {"j1": {"p1"}, "j2": {"p2"}}
    assert components_of(live) == [{"p1"}, {"p2"}]


def test_components_empty_and_singleton():
    assert components_of({}) == []
    assert components_of({"j1": {"p1"}}) == [{"p1"}]


def test_components_ignores_idle_judges():
    live = {"j1": {"p1", "p2"}, "j2": set()}
    assert components_of(live) == [{"p1", "p2"}]


def test_shared_judge_count():
    cov = {"p1": {"a", "b"}, "p2": {"b", "c"}, "p3": {"d"}}
    assert shared_judge_count(cov, "p1", "p2") == 1
    assert shared_judge_count(cov, "p1", "p3") == 0
    assert shared_judge_count(cov, "p1", "p9") == 0


def test_single_shared_pairs_finds_thin_bridges():
    cov = {"p1": {"a", "b"}, "p2": {"b", "c"}, "p3": {"b", "c"}, "p4": {"d"}}
    # (p1,p2): {b}; (p1,p3): {b}; (p2,p3): {b,c} -> not thin; p4 isolated.
    assert single_shared_pairs(cov) == [("p1", "p2"), ("p1", "p3")]


def test_min_bridge():
    assert min_bridge({}) is None
    assert min_bridge({"p1": {"a"}}) is None  # no linked pairs at all
    assert min_bridge({"p1": {"a", "b"}, "p2": {"b", "c"}}) == 1
    assert min_bridge({"p1": {"a", "b"}, "p2": {"a", "b"}}) == 2
