from pathlib import Path

import pytest

from engine.schema import Case
from evals.retrieval import (
    QUERIES,
    Expect,
    LabelledQuery,
    Outcome,
    load_queries,
    p95,
    run,
    summarize,
)

CASES_DIR = Path(__file__).resolve().parents[3] / "cases"
CASES = {
    c.id: c for c in (Case.model_validate_json(p.read_text()) for p in CASES_DIR.glob("*.json"))
}


def outcome(
    relevant: str,
    ranked: tuple[str, ...],
    expect: Expect = "found",
    leaks: int = 0,
    ms: float = 1.0,
) -> Outcome:
    q = LabelledQuery("manor", "q", relevant, (), ())
    return Outcome(q, expect, ranked, leaks, (ms,), (ms / 2,))


def test_recall_and_mrr_match_hand_computed_values() -> None:
    ranked = tuple(f"d{i}" for i in range(1, 12))
    metrics = summarize(
        [
            outcome("d1", ranked),
            outcome("d3", ranked),
            outcome("d11", ranked),
            outcome("zz", ranked),
        ]
    )
    assert metrics.recall_at_10 == pytest.approx(2 / 4)
    assert metrics.mrr == pytest.approx((1 + 1 / 3) / 4)


def test_withheld_and_leaks_are_scored_apart_from_found() -> None:
    metrics = summarize(
        [
            outcome("a", ("a", "b")),
            outcome("x", ("b", "c"), expect="withheld"),
            outcome("y", ("y", "c"), expect="withheld", leaks=1),
        ]
    )
    assert (metrics.recall_at_10, metrics.mrr) == (1.0, 1.0)
    assert metrics.withheld_ok == 0.5
    assert metrics.acl_leaks == 1


def test_p95_is_nearest_rank() -> None:
    assert p95([float(i) for i in range(1, 21)]) == 19.0
    assert p95([5.0]) == 5.0


def test_shipped_queries_cover_the_plan() -> None:
    loaded = load_queries(QUERIES, CASES)
    for case_id, case in CASES.items():
        mine = [(q, e) for q, e in loaded if q.case_id == case_id]
        assert sum(e == "found" for _, e in mine) >= 8
        assert sum(e == "withheld" for _, e in mine) >= 2
        key_clues = [c for c in case.clues if c.id in case.solution_chain and c.doc_id]
        assert all(any(q.query == c.description for q, _ in mine) for c in key_clues)
    assert sum(e == "withheld" for _, e in loaded) >= 6


def test_manor_pair_is_withheld_then_found() -> None:
    pair = [(q, e) for q, e in load_queries(QUERIES, CASES) if q.relevant == "solicitor_letter"]
    assert pair[0][0].query == pair[1][0].query
    assert sorted(e for _, e in pair) == ["found", "withheld"]


def test_loader_rejects_unknown_ids_and_too_few_locked_queries(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- {case: manor, query: q, relevant: nope}\n")
    with pytest.raises(ValueError, match=r"bad.yaml\[0\]: unknown relevant document 'nope'"):
        load_queries(bad, CASES)
    few = tmp_path / "few.yaml"
    few.write_text("- {case: manor, query: q, relevant: dinner_menu}\n")
    with pytest.raises(ValueError, match="withheld queries"):
        load_queries(few, {"manor": CASES["manor"]})


def test_replayed_eval_has_no_leaks_and_withholds_every_locked_target(tmp_path: Path) -> None:
    results = run(QUERIES, CASES_DIR, tmp_path)
    assert results["overall"].acl_leaks == 0
    assert results["overall"].withheld_ok == 1.0
    assert results["overall"].recall_at_10 == 1.0
    assert {"gallery", "lighthouse", "manor", "overall"} == set(results)
    assert (tmp_path / "retrieval.md").read_text().count("| 0 |") == 4
