import os
from pathlib import Path

import pytest
import sqlalchemy as sa

from engine import generator
from engine.cli import load_case
from engine.generator import Discarded, generate_with_repair
from engine.mutate import add_contradiction, drop_clue
from engine.repair import repair_instructions
from engine.schema import Case
from engine.solver import (
    CheckReport,
    Consistent,
    DropLeavesNoModel,
    LieCheck,
    Unique,
    check_case,
)
from tests.engine.generator_scenarios import SCENARIOS

CASES = Path(__file__).resolve().parents[3] / "cases"


def manor() -> Case:
    return load_case(CASES / "manor.json")


def test_a_passing_case_needs_no_instructions() -> None:
    assert repair_instructions(check_case(manor())) == ""


def test_ambiguity_names_the_alternative_culprit_and_the_fact_to_reveal() -> None:
    text = repair_instructions(check_case(drop_clue(manor(), "pavilion_book")))

    assert "uniqueness: with every clue, clara, dr_finch can each be the culprit" in text
    assert "these case facts are false: finch_in_garden" in text
    assert "placing dr_finch in another location in the crime slot" in text


def test_a_short_chain_asks_for_the_missing_alibi_in_solution_chain() -> None:
    case = manor()
    text = repair_instructions(
        check_case(case.model_copy(update={"solution_chain": case.solution_chain[:2]}))
    )

    assert text.startswith("- sufficiency: with only the solution_chain clues")
    assert "dr_finch" in text


def test_a_contradiction_names_both_facts() -> None:
    text = repair_instructions(check_case(add_contradiction(manor(), "pike_in_kitchen")))

    assert "consistency: facts pike_in_kitchen, pike_in_kitchen_contradiction" in text
    assert "Change or remove one of them." in text


def test_a_wrong_culprit_names_who_remains() -> None:
    text = repair_instructions(check_case(manor().model_copy(update={"culprit": "hobbs"})))

    assert "once the intended culprit is at the crime scene" in text
    assert "the intended culprit is ruled out and only clara remain" in text


def test_clues_that_rule_out_everyone_say_so() -> None:
    data = manor().model_dump(mode="json")
    data["facts"].append(
        {
            "id": "clara_in_garden",
            "subject": "clara",
            "predicate": "at",
            "object": "garden",
            "time_slot": 3,
        }
    )
    data["clues"].append(
        {
            "id": "gardener_testimony",
            "kind": "testimony",
            "description": "Clara was in the garden at 10pm.",
            "reveals": ["clara_in_garden"],
        }
    )

    text = repair_instructions(check_case(Case.model_validate(data)))

    assert "uniqueness: with every clue, no suspect can be the culprit" in text


def test_a_redundant_chain_clue_is_named() -> None:
    case = manor()
    padded = case.model_copy(update={"solution_chain": (*case.solution_chain, "debt_ledger")})

    text = repair_instructions(check_case(padded))

    assert "solution_chain clue debt_ledger is redundant" in text


def test_a_chain_drop_with_no_model_is_named() -> None:
    report = CheckReport(
        "manor",
        Consistent(),
        Unique("clara"),
        Unique("clara"),
        (DropLeavesNoModel("diary_page"),),
        (),
    )

    assert "dropping solution_chain clue diary_page leaves no possible world" in (
        repair_instructions(report)
    )


def test_each_lie_warning_becomes_an_instruction() -> None:
    report = check_case(manor())
    lies = (LieCheck("bad_lie", exposed=False, true_in_case=True, denies_hidden_fact=False),)

    text = repair_instructions(
        CheckReport(report.case_id, Consistent(), Unique("clara"), Unique("clara"), (), lies)
    )

    assert "lie bad_lie: no clue exposes it" in text
    assert "lie bad_lie: the case facts allow its claim to be true" in text
    assert "lie bad_lie: its claim does not contradict the fact it hides" in text


def test_a_case_that_fails_five_rounds_is_discarded_with_its_reason() -> None:
    scenario = SCENARIOS["discarded"]

    result = generate_with_repair(scenario.brief, scenario.max_rounds)

    assert isinstance(result, Discarded)
    assert result.reason == "max_rounds"
    assert [r.step for r in result.rounds] == ["generate", *["repair"] * 4]
    assert {r.verdict for r in result.rounds} == {"core_rejected"}
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("select outcome, rounds, failure_reason from generation_log where id = :id"),
            {"id": result.generation_id},
        ).one()
    assert (row.outcome, row.rounds) == ("discarded", 5)
    assert row.failure_reason.startswith("max_rounds: round 5 repair core_rejected: uniqueness")
    assert "dr_finch" in row.failure_reason


def test_the_budget_stops_new_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generator, "BUDGET_S", 0)
    scenario = SCENARIOS["discarded"]

    result = generate_with_repair(scenario.brief, scenario.max_rounds)

    assert isinstance(result, Discarded)
    assert (result.reason, len(result.rounds)) == ("budget", 1)


def test_a_crash_marks_the_log_row_crashed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("provider down")

    monkeypatch.setattr(generator, "run_round", boom)

    with pytest.raises(RuntimeError):
        generate_with_repair(SCENARIOS["discarded"].brief)

    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "select outcome, failure_reason from generation_log "
                "order by started_at desc limit 1"
            )
        ).one()
    assert (row.outcome, row.failure_reason) == ("crashed", "RuntimeError")
