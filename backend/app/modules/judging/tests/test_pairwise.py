"""Pure unit tests for pairwise generation. No database, no server.

Run inside the api image (code is baked in there):
    docker compose exec -T api python -m pytest app/modules/judging/tests/ -q
"""
import json
from pathlib import Path

from app.modules.judging.pairwise import connected_components, generate_pairs

# The corrected architecture's documented evidence table (§14): the fitter
# input our pipeline must reproduce exactly from fixture scores.
EXPECTED_PAIRS = [
    ("jdg_21", "prj_02", "prj_03"), ("jdg_21", "prj_02", "prj_07"),
    ("jdg_21", "prj_07", "prj_03"), ("jdg_12", "prj_07", "prj_02"),
    ("jdg_26", "prj_02", "prj_03"), ("jdg_26", "prj_02", "prj_06"),
    ("jdg_26", "prj_07", "prj_02"), ("jdg_26", "prj_03", "prj_06"),
    ("jdg_26", "prj_07", "prj_03"), ("jdg_26", "prj_07", "prj_06"),
    ("jdg_19", "prj_03", "prj_07"), ("jdg_22", "prj_12", "prj_04"),
    ("jdg_24", "prj_12", "prj_06"),
]

POC_WEIGHTS = {"functionality": 0.40, "quality": 0.35, "innovation": 0.25}
POC_PROJECTS = ["prj_02", "prj_03", "prj_04", "prj_06", "prj_07", "prj_12"]


def _fixture_path() -> Path:
    """Locate fixtures.json in any layout: FIXTURE_PATH (the seed's
    convention, /fixtures/fixtures.json inside the api image), a checkout
    root above this file, or the cwd."""
    import os
    cands = [Path(os.getenv("FIXTURE_PATH", "/fixtures/fixtures.json"))]
    here = Path(__file__).resolve()
    cands += [p / "fixtures.json" for p in [here, *here.parents]]
    cands.append(Path.cwd() / "fixtures.json")
    for c in cands:
        if c.is_file():
            return c
    raise FileNotFoundError("fixtures.json not found (tried FIXTURE_PATH, parents, cwd)")


def _poc_rows():
    """Fixture scores for the six-project reference subset, adapted from the
    real fixture keys (judge/project/criteria) to the pipeline's rows."""
    fx = json.loads(_fixture_path().read_text())
    rows = []
    for s in fx["scores"]:
        if s["project"] not in POC_PROJECTS:
            continue
        w = sum(POC_WEIGHTS[k] * float(v) for k, v in s["criteria"].items())
        rows.append({"judge_user_id": s["judge"], "project_id": s["project"],
                     "weighted_score": w, "evaluation_id": f"{s['judge']}:{s['project']}"})
    return rows


def test_reference_evidence_reproduced_exactly():
    pairs = generate_pairs(_poc_rows())
    got = sorted((p["judge_user_id"], p["winner_project_id"], p["loser_project_id"])
                 for p in pairs)
    assert got == sorted(EXPECTED_PAIRS), (
        f"pipeline evidence differs from the architecture's documented table: "
        f"missing={sorted(set(EXPECTED_PAIRS) - set(got))} extra={sorted(set(got) - set(EXPECTED_PAIRS))}")
    assert all(p["weight"] == 1.0 for p in pairs)


def test_ties_produce_no_observation():
    rows = [
        {"judge_user_id": "j", "project_id": "a", "weighted_score": 6.5, "evaluation_id": "e1"},
        {"judge_user_id": "j", "project_id": "b", "weighted_score": 6.5, "evaluation_id": "e2"},
        {"judge_user_id": "j", "project_id": "c", "weighted_score": 7.0, "evaluation_id": "e3"},
    ]
    pairs = generate_pairs(rows)
    # a/b tied (no row); a/c and b/c both lose to c.
    assert sorted((p["winner_project_id"], p["loser_project_id"]) for p in pairs) == [("c", "a"), ("c", "b")]


def test_float_dust_is_a_tie_not_a_win():
    # 0.1 + 0.2 != 0.3 in binary FP: mathematically tied vectors must not
    # crown a winner on representation dust.
    rows = [
        {"judge_user_id": "j", "project_id": "a", "weighted_score": 0.1 + 0.2, "evaluation_id": "e1"},
        {"judge_user_id": "j", "project_id": "b", "weighted_score": 0.3, "evaluation_id": "e2"},
    ]
    assert generate_pairs(rows) == []


def test_scale_invariance_same_ordering_same_direction():
    # Strict judge (1-5) and lenient judge (0-100) with the same ordering
    # produce the same directional preference; the margin never leaks in.
    strict = [
        {"judge_user_id": "strict", "project_id": "a", "weighted_score": 5, "evaluation_id": "e1"},
        {"judge_user_id": "strict", "project_id": "b", "weighted_score": 3, "evaluation_id": "e2"},
    ]
    lenient = [
        {"judge_user_id": "lenient", "project_id": "a", "weighted_score": 85, "evaluation_id": "e1"},
        {"judge_user_id": "lenient", "project_id": "b", "weighted_score": 70, "evaluation_id": "e2"},
    ]
    ps = generate_pairs(strict)
    pl = generate_pairs(lenient)
    assert [(p["winner_project_id"], p["loser_project_id"]) for p in ps] == [("a", "b")]
    assert [(p["winner_project_id"], p["loser_project_id"]) for p in pl] == [("a", "b")]
    assert ps[0]["weight"] == pl[0]["weight"] == 1.0


def test_single_project_judge_yields_nothing():
    rows = [{"judge_user_id": "j", "project_id": "a", "weighted_score": 9, "evaluation_id": "e1"}]
    assert generate_pairs(rows) == []


def test_connected_graph_single_component():
    pairs = generate_pairs(_poc_rows())
    assert connected_components(pairs, POC_PROJECTS) == [set(POC_PROJECTS)]


def test_disconnected_graph_detected():
    pairs = [
        {"judge_user_id": "j1", "winner_project_id": "a", "loser_project_id": "b",
         "weight": 1.0, "source_evaluation_ids": []},
        {"judge_user_id": "j2", "winner_project_id": "c", "loser_project_id": "d",
         "weight": 1.0, "source_evaluation_ids": []},
    ]
    comps = connected_components(pairs, ["a", "b", "c", "d"])
    assert sorted(map(sorted, comps)) == [["a", "b"], ["c", "d"]]
