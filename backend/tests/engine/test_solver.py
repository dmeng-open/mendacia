from pathlib import Path

import clingo
import pytest

from engine.cli import load_case, main
from engine.compiler import compile_case
from engine.mutate import Uncontradictable, add_contradiction, drop_clue
from engine.schema import Case, Fact
from engine.solver import (
    Ambiguous,
    Conflict,
    Consistent,
    Necessary,
    NecessitySkipped,
    NoCulprit,
    Redundant,
    Unique,
    check_case,
)

CASES = Path(__file__).resolve().parents[3] / "cases"
CASE_PATHS = sorted(CASES.glob("*.json"))


def load(name: str) -> Case:
    return load_case(CASES / f"{name}.json")


CHAIN_DROPS = [
    pytest.param(path.stem, clue_id, id=f"{path.stem}-{clue_id}")
    for path in CASE_PATHS
    for clue_id in load_case(path).solution_chain
]


@pytest.mark.parametrize("path", CASE_PATHS, ids=lambda p: p.stem)
def test_hand_written_case_passes_every_check(path: Path) -> None:
    case = load_case(path)
    report = check_case(case)

    assert report.consistency == Consistent()
    assert report.uniqueness == Unique(case.culprit)
    assert not isinstance(report.necessity, NecessitySkipped)
    assert [type(v) for v in report.necessity] == [Necessary] * len(case.solution_chain)
    assert all(lie.exposed and not lie.true_in_case for lie in report.lies)
    assert report.passed


@pytest.mark.parametrize(("name", "clue_id"), CHAIN_DROPS)
def test_dropping_a_chain_clue_lets_another_suspect_do_it(name: str, clue_id: str) -> None:
    case = load(name)
    dropped = case.clues[[c.id for c in case.clues].index(clue_id)]

    report = check_case(drop_clue(case, clue_id))

    assert isinstance(report.uniqueness, Ambiguous)
    cx = report.uniqueness.counterexample
    assert cx.culprit != case.culprit
    assert cx.culprit in {s.id for s in case.suspects}
    assert set(cx.breaks) == set(dropped.reveals)
    assert report.necessity == NecessitySkipped()
    assert not report.passed


def test_dropping_a_non_chain_clue_keeps_the_culprit_unique() -> None:
    case = load("manor")
    assert check_case(drop_clue(case, "debt_ledger")).uniqueness == Unique("clara")


def test_suspect_in_two_places_fails_consistency_naming_both_facts() -> None:
    case = add_contradiction(load("manor"), "pike_in_kitchen")

    report = check_case(case)

    assert report.consistency == Conflict(
        ("pike_in_kitchen", "pike_in_kitchen_contradiction"), with_culprit=False
    )
    assert not report.passed


def test_contradicting_a_saw_fact_moves_the_seen_person() -> None:
    report = check_case(add_contradiction(load("manor"), "pike_saw_hobbs"))

    assert isinstance(report.consistency, Conflict)
    assert set(report.consistency.fact_ids) == {
        "pike_in_kitchen",
        "pike_saw_hobbs",
        "pike_saw_hobbs_contradiction",
    }


def test_has_facts_cannot_be_contradicted() -> None:
    with pytest.raises(Uncontradictable):
        add_contradiction(load("manor"), "clara_has_opener")


PIKE_IN_BALLROOM = Fact(
    id="pike_in_ballroom", subject="mrs_pike", predicate="at", object="ballroom", time_slot=3
)


def test_extra_fact_is_pinned_like_a_revealed_fact() -> None:
    program = compile_case(load("manor"), extra_facts=[PIKE_IN_BALLROOM])
    control = clingo.Control(["--warn=none"])
    control.add("base", [], program)
    control.ground([("base", [])])
    assert control.solve().unsatisfiable


def test_a_redundant_chain_clue_fails_necessity() -> None:
    case = load("manor")
    padded = case.model_copy(update={"solution_chain": (*case.solution_chain, "debt_ledger")})

    report = check_case(padded)

    assert isinstance(report.necessity, tuple)
    assert report.necessity[-1] == Redundant("debt_ledger")
    assert not report.passed


def test_clues_that_contradict_each_other_leave_no_culprit() -> None:
    case = load("manor")
    clue = {
        "id": "ballroom_testimony",
        "kind": "testimony",
        "description": "Mrs. Pike was in the ballroom at 10pm.",
        "reveals": ["pike_in_ballroom"],
    }
    data = case.model_dump(mode="json")
    data["facts"].append(PIKE_IN_BALLROOM.model_dump(mode="json"))
    data["clues"].append(clue)

    report = check_case(Case.model_validate(data))

    assert report.uniqueness == NoCulprit()
    assert report.necessity == NecessitySkipped()


def test_an_unexposed_lie_warns_without_failing() -> None:
    case = drop_clue(load("gallery"), "cctv_east_hall")
    report = check_case(case)
    wren = next(lie for lie in report.lies if lie.lie_id == "wren_office_lie")
    assert not wren.exposed


def test_cli_prints_one_line_per_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(CASES / "manor.json")]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "consistency PASS",
        "uniqueness PASS culprit=clara",
        "necessity PASS 3/3 chain clues",
        "lies PASS 1/1 exposed",
    ]


def test_cli_prints_the_counterexample_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "gallery.json"
    broken.write_text(drop_clue(load("gallery"), "cctv_east_hall").model_dump_json())

    assert main(["check", str(broken)]) == 1

    out = capsys.readouterr().out.splitlines()
    assert out[1] == "uniqueness FAIL culprits=lady_wren,sam_okafor"
    assert out[2].startswith("  counterexample culprit=lady_wren breaks=wren_in_east_hall holds=")
