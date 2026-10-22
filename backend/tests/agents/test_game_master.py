from pathlib import Path

import pytest

from agents.game_master import (
    HINTS,
    QUESTIONS,
    Hint,
    NoHint,
    new_game,
    next_hint,
    open_document,
    record_reply,
    rule_accusation,
    spend_question,
    timeline,
)
from agents.verifier import Verdict
from engine.schema import Case

CASES = Path(__file__).resolve().parents[3] / "cases"
MANOR = Case.model_validate_json((CASES / "manor.json").read_text())


def test_new_game_has_the_full_budget() -> None:
    state = new_game(MANOR, "g")
    assert (state.questions_left, state.hints_left) == (QUESTIONS, HINTS) == (20, 3)


def test_question_budget_runs_out() -> None:
    state = new_game(MANOR, "g")
    for _ in range(QUESTIONS):
        state = spend_question(state)
    assert state.questions_left == 0
    with pytest.raises(ValueError, match="no questions left"):
        spend_question(state)


def test_fourth_hint_is_refused() -> None:
    state = new_game(MANOR, "g")
    hints = []
    for _ in range(4):
        state, hint = next_hint(MANOR, state)
        hints.append(hint)
    assert [type(h) for h in hints] == [Hint, Hint, Hint, NoHint]
    assert hints[-1].text == "You have no hints left."
    assert state.hints_left == 0


def test_hint_skips_discovered_clues() -> None:
    state = record_reply(MANOR, new_game(MANOR, "g"), [(Verdict.KNOWN_TRUE, "pike_in_kitchen")])
    assert state.discovered == ("pike_kitchen_testimony",)
    state, hint = next_hint(MANOR, state)
    assert isinstance(hint, Hint) and hint.clue_id == "pike_saw_hobbs_testimony"
    state, _ = open_document(MANOR, state, "pavilion_visitors_book")
    state = record_reply(MANOR, state, [(Verdict.ADMISSION, "pike_saw_hobbs")])
    _, done = next_hint(MANOR, state)
    assert isinstance(done, NoHint) and "every clue" in done.text


def test_evidence_hint_names_the_document() -> None:
    state = record_reply(
        MANOR,
        new_game(MANOR, "g"),
        [(Verdict.KNOWN_TRUE, "pike_in_kitchen"), (Verdict.KNOWN_TRUE, "pike_saw_hobbs")],
    )
    _, hint = next_hint(MANOR, state)
    assert isinstance(hint, Hint) and hint.clue_id == "pavilion_book"
    assert "/read pavilion_visitors_book" in hint.text


def test_lies_and_blocked_claims_discover_nothing() -> None:
    state = record_reply(
        MANOR,
        new_game(MANOR, "g"),
        [(Verdict.PLANNED_LIE, "clara_library_lie"), (Verdict.BLOCK_UNPLANNED, None)],
    )
    assert state.discovered == ()


def test_reading_a_document_discovers_its_clue() -> None:
    state, doc = open_document(MANOR, new_game(MANOR, "g"), "pavilion_visitors_book")
    assert doc.is_key and state.discovered == ("pavilion_book",)
    with pytest.raises(KeyError):
        open_document(MANOR, state, "no_such_doc")


def test_wrong_culprit_is_wrong() -> None:
    ruling = rule_accusation(MANOR, "hobbs", MANOR.solution_chain)
    assert not ruling.correct and ruling.text.startswith("Wrong")


def test_right_culprit_with_one_chain_clue_is_not_proven() -> None:
    ruling = rule_accusation(MANOR, "clara", ["pavilion_book", "debt_ledger"])
    assert not ruling.correct
    assert ruling.chain_cited == ("pavilion_book",)
    assert ruling.text.startswith("Not proven")


def test_right_culprit_with_two_chain_clues_is_correct() -> None:
    ruling = rule_accusation(MANOR, "clara", ["pavilion_book", "pike_kitchen_testimony"])
    assert ruling.correct and ruling.text == "Correct."
    assert ruling.chain_cited == ("pike_kitchen_testimony", "pavilion_book")


def test_timeline_puts_the_killing_in_its_slot() -> None:
    lines = timeline(MANOR)
    killing = "10pm  Clara Ashcombe killed Lord Edmund Ashcombe in the study"
    assert f"{killing} with the silver letter opener." in lines
    assert lines.index("9pm  Mr. Hobbs was in the ballroom.") < lines.index(
        "10pm  Clara Ashcombe was in the study."
    )
