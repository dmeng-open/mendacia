import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from engine.cli import main
from engine.schema import Case

CASES = Path(__file__).resolve().parents[3] / "cases"
CASE_PATHS = sorted(CASES.glob("*.json"))

Mutation = Callable[[dict[str, Any]], None]


def manor() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((CASES / "manor.json").read_text())
    return data


def _set(path: list[str | int], value: object) -> Mutation:
    def mutate(data: dict[str, Any]) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def _rename_secret_owner(data: dict[str, Any]) -> None:
    data["secrets"]["ghost"] = data["secrets"].pop("dr_finch")


REFERENCE_CASES: list[tuple[str, Mutation, str]] = [
    ("known_by", _set(["facts", 0, "known_by", 0], "ghost"), "facts[0].known_by[0]"),
    ("secrets key", _rename_secret_owner, "secrets.ghost"),
    ("secrets value", _set(["secrets", "clara", 1], "ghost"), "secrets.clara[1]"),
    (
        "planned lie suspect",
        _set(["planned_lies", 0, "suspect"], "ghost"),
        "planned_lies[0].suspect",
    ),
    (
        "planned lie hides_fact",
        _set(["planned_lies", 0, "hides_fact"], "ghost"),
        "planned_lies[0].hides_fact",
    ),
    ("clue reveals", _set(["clues", 2, "reveals", 0], "ghost"), "clues[2].reveals[0]"),
    ("clue doc_id", _set(["clues", 3, "doc_id"], "ghost"), "clues[3].doc_id"),
    (
        "document unlock",
        _set(["documents", 1, "visibility"], {"unlocked_by": ["ghost"]}),
        "documents[1].visibility.unlocked_by[0]",
    ),
    ("solution chain", _set(["solution_chain", 1], "ghost"), "solution_chain[1]"),
    ("culprit", _set(["culprit"], "ghost"), "culprit"),
    ("fact subject", _set(["facts", 4, "subject"], "ghost"), "facts[4].subject"),
    ("fact location", _set(["facts", 2, "object"], "ghost"), "facts[2].object"),
    ("crime location", _set(["crime", "location"], "ghost"), "crime.location"),
    ("crime means", _set(["crime", "means"], "ghost"), "crime.means"),
]


@pytest.mark.parametrize("path", CASE_PATHS, ids=lambda p: p.stem)
def test_hand_written_case_parses(path: Path) -> None:
    case = Case.model_validate_json(path.read_text())
    assert len(case.suspects) == 4
    assert 6 <= len(case.clues) <= 10
    assert case.planned_lies
    evidence = [c for c in case.clues if c.kind == "evidence"]
    assert {c.doc_id for c in evidence} <= {d.id for d in case.documents}


def test_all_three_cases_exist() -> None:
    assert [p.stem for p in CASE_PATHS] == ["gallery", "lighthouse", "manor"]


@pytest.mark.parametrize(
    ("mutate", "path"),
    [pytest.param(m, p, id=name) for name, m, p in REFERENCE_CASES],
)
def test_dangling_reference_names_path_and_id(mutate: Mutation, path: str) -> None:
    data = manor()
    mutate(data)
    with pytest.raises(ValidationError) as error:
        Case.model_validate(data)
    assert f"{path}: unknown" in str(error.value)
    assert "'ghost'" in str(error.value)


def test_a_document_cannot_unlock_itself() -> None:
    data = manor()
    data["documents"][1]["visibility"] = {"unlocked_by": [data["documents"][1]["id"]]}
    with pytest.raises(ValidationError, match=r"documents\[1\].visibility.unlocked_by\[0\]"):
        Case.model_validate(data)


def test_a_document_can_be_unlocked_by_a_clue_or_a_document() -> None:
    data = manor()
    data["documents"][1]["visibility"] = {"unlocked_by": ["pike_kitchen_testimony"]}
    data["documents"][2]["visibility"] = {"unlocked_by": [data["documents"][0]["id"]]}
    Case.model_validate(data)


def test_unknown_predicate_fails() -> None:
    data = manor()
    data["facts"][0]["predicate"] = "loves"
    with pytest.raises(ValidationError, match="predicate"):
        Case.model_validate(data)


def test_time_slot_out_of_range_fails() -> None:
    data = manor()
    data["facts"][0]["time_slot"] = 9
    with pytest.raises(ValidationError, match=r"facts\[0\].time_slot: unknown time slot '9'"):
        Case.model_validate(data)


def test_planned_lie_must_hide_a_secret_of_its_suspect() -> None:
    data = manor()
    data["planned_lies"][0]["hides_fact"] = "pike_in_kitchen"
    with pytest.raises(ValidationError, match="'pike_in_kitchen' is not a secret of 'clara'"):
        Case.model_validate(data)


def test_duplicate_ids_fail() -> None:
    data = manor()
    data["clues"][1]["id"] = data["clues"][0]["id"]
    with pytest.raises(ValidationError, match="duplicate clue id 'pike_kitchen_testimony'"):
        Case.model_validate(data)


def test_cli_lists_every_path_of_a_renamed_suspect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = manor()
    data["suspects"][1]["id"] = "clara_renamed"
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data))

    assert main(["validate", str(broken)]) == 1

    out = capsys.readouterr().out
    for path in [
        "facts[0].subject",
        "facts[0].known_by[0]",
        "facts[1].subject",
        "facts[6].known_by[1]",
        "secrets.clara",
        "planned_lies[0].suspect",
        "planned_lies[0].claim.subject",
        "culprit",
    ]:
        assert f"{path}: unknown" in out


def test_cli_prints_ok_per_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", *map(str, CASE_PATHS)]) == 0
    assert capsys.readouterr().out.splitlines() == [f"OK {p}" for p in CASE_PATHS]


def test_clingo_keyword_id_fails() -> None:
    data = manor()
    data["locations"]["not"] = data["locations"].pop("ballroom")
    with pytest.raises(ValidationError, match="'not' is a clingo keyword"):
        Case.model_validate(data)


def test_person_cannot_see_themselves() -> None:
    data = manor()
    data["facts"][3]["object"] = data["facts"][3]["subject"]
    with pytest.raises(ValidationError, match="'saw' needs two different people"):
        Case.model_validate(data)


def test_duplicate_chain_entry_fails() -> None:
    data = manor()
    data["solution_chain"].append(data["solution_chain"][0])
    with pytest.raises(
        ValidationError, match="duplicate solution_chain id 'pike_kitchen_testimony'"
    ):
        Case.model_validate(data)


def test_a_document_cannot_share_an_id_with_a_clue() -> None:
    data = json.loads((CASES / "manor.json").read_text())
    data["documents"][4]["id"] = "pike_kitchen_testimony"
    with pytest.raises(
        ValidationError, match=r"documents\[4\]\.id: 'pike_kitchen_testimony' is also a clue id"
    ):
        Case.model_validate(data)
