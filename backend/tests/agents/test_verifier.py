import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from agents.claims import Claim
from agents.ledger import Ledger, LieStatus
from agents.verifier import BlockedReply, Verdict, main, stateable_facts, verify_reply
from engine.schema import Case, PlannedLie, Statement

CASES = Path(__file__).resolve().parents[3] / "cases"
MANOR = Case.model_validate_json((CASES / "manor.json").read_text())

HOBBS_IN_BALLROOM = Claim(subject="hobbs", predicate="at", object="ballroom", time_slot=2)
CLARA_IN_LIBRARY = Claim(subject="clara", predicate="at", object="library", time_slot=3)
CLARA_IN_STUDY = Claim(subject="clara", predicate="at", object="study", time_slot=3)
FINCH_IN_GARDEN = Claim(subject="dr_finch", predicate="at", object="garden", time_slot=3)
CLARA_KILLED = Claim(subject="clara", predicate="killed", object="lord_ashcombe")
CLARA_HAS_OPENER = Claim(subject="clara", predicate="has", object="letter_opener")
FINCH_OWES = Claim(subject="dr_finch", predicate="owes", object="lord_ashcombe")


def verdicts(
    suspect: str, *claims: Claim, ledger: Ledger | None = None, shown: str = ""
) -> list[str]:
    result = verify_reply(
        MANOR, suspect, claims, ledger or Ledger(), set(filter(None, shown.split(",")))
    )
    return [c.verdict.name for c in result.checks]


def told(case: Case = MANOR) -> Ledger:
    return verify_reply(case, "clara", [CLARA_IN_LIBRARY], Ledger(), set()).commit(1)


def test_known_true() -> None:
    assert verdicts("clara", HOBBS_IN_BALLROOM) == ["KNOWN_TRUE"]


def test_planned_lie_records_told() -> None:
    [entry] = told().entries
    assert (entry.lie.id, entry.status, entry.turn) == ("clara_library_lie", LieStatus.TOLD, 1)


def test_admission_moves_told_to_admitted() -> None:
    result = verify_reply(MANOR, "clara", [CLARA_IN_STUDY], told(), {"diary_page"})
    assert [c.verdict for c in result.checks] == [Verdict.ADMISSION]
    [entry] = result.commit(2).entries
    assert (entry.status, entry.turn) == (LieStatus.ADMITTED, 1)


def test_culprit_as_killer_blocks_for_every_speaker() -> None:
    for suspect in ("clara", "hobbs", "mrs_pike", "dr_finch"):
        assert verdicts(suspect, CLARA_KILLED, shown="diary_page,opener_case") == ["BLOCK_CULPRIT"]


def test_unexposed_culprit_secret_blocks_even_when_known() -> None:
    assert verdicts("hobbs", CLARA_HAS_OPENER) == ["BLOCK_CULPRIT"]
    assert verdicts("hobbs", CLARA_HAS_OPENER, shown="opener_case") == ["KNOWN_TRUE"]


def test_unspecified_slot_reads_as_any_slot_for_blocks() -> None:
    vague = Claim(subject="clara", predicate="at", object="study")
    assert verdicts("clara", vague) == ["BLOCK_CULPRIT"]
    assert verdicts("clara", Claim(subject="hobbs", predicate="at", object="ballroom")) == [
        "BLOCK_UNPLANNED"
    ]


def test_unknown_fact_blocks() -> None:
    assert verdicts("clara", FINCH_IN_GARDEN) == ["BLOCK_UNPLANNED"]


def test_hidden_fact_before_its_clue_blocks_then_admits() -> None:
    assert verdicts("dr_finch", FINCH_OWES) == ["BLOCK_UNPLANNED"]
    assert verdicts("dr_finch", FINCH_OWES, shown="debt_ledger") == ["ADMISSION"]


def test_lie_that_contradicts_an_earlier_ledger_entry_blocks() -> None:
    ballroom = Statement(subject="clara", predicate="at", object="ballroom", time_slot=3)
    second = PlannedLie(
        id="clara_ballroom_lie",
        suspect="clara",
        hides_fact="clara_in_study",
        claim=ballroom,
        says="I was dancing alone in the ballroom.",
    )
    case = MANOR.model_copy(update={"planned_lies": (*MANOR.planned_lies, second)})
    claim = Claim(**ballroom.model_dump())
    fresh = verify_reply(case, "clara", [claim], Ledger(), set())
    assert [c.verdict for c in fresh.checks] == [Verdict.PLANNED_LIE]
    after = verify_reply(case, "clara", [claim], told(case), set())
    assert [(c.verdict, c.ref) for c in after.checks] == [
        (Verdict.BLOCK_UNPLANNED, "clara_ballroom_lie")
    ]
    both = verify_reply(case, "clara", [CLARA_IN_LIBRARY, claim], Ledger(), set())
    assert [c.verdict for c in both.checks] == [Verdict.BLOCK_UNPLANNED] * 2


def test_lie_is_spent_once_exposed_or_admitted() -> None:
    assert verdicts("clara", CLARA_IN_LIBRARY, ledger=told(), shown="diary_page") == [
        "BLOCK_UNPLANNED"
    ]
    admitted = verify_reply(MANOR, "clara", [CLARA_IN_STUDY], told(), {"diary_page"}).commit(2)
    assert verdicts("clara", CLARA_IN_LIBRARY, ledger=admitted) == ["BLOCK_UNPLANNED"]
    assert verdicts("clara", CLARA_IN_STUDY, CLARA_IN_LIBRARY, shown="diary_page") == [
        "ADMISSION",
        "BLOCK_UNPLANNED",
    ]


def test_no_claims_pass_and_record_exposure() -> None:
    result = verify_reply(MANOR, "clara", [], told(), {"diary_page"})
    assert result.passed
    [entry] = result.commit(2).entries
    assert entry.status is LieStatus.EXPOSED


def test_verdicts_ignore_claim_order() -> None:
    claims = [HOBBS_IN_BALLROOM, CLARA_IN_LIBRARY, FINCH_IN_GARDEN, CLARA_KILLED, CLARA_IN_STUDY]
    forward = verdicts("clara", *claims, shown="diary_page")
    assert verdicts("clara", *reversed(claims), shown="diary_page") == forward[::-1]


def test_commit_is_idempotent_and_refuses_blocked_replies() -> None:
    result = verify_reply(MANOR, "clara", [CLARA_IN_LIBRARY], Ledger(), set())
    once = result.commit(1)
    assert result.commit(1) == once
    with pytest.raises(BlockedReply, match="leave this claim out"):
        verify_reply(MANOR, "clara", [CLARA_KILLED], Ledger(), set()).commit(1)


def test_lever_lane_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    claims = tmp_path / "claims.json"
    claims.write_text(
        "["
        + ",".join(
            c.model_dump_json()
            for c in (HOBBS_IN_BALLROOM, CLARA_IN_LIBRARY, FINCH_IN_GARDEN, CLARA_KILLED)
        )
        + "]"
    )
    code = main(
        ["--case", str(CASES / "manor.json"), "--suspect", "clara", "--claims", str(claims)]
    )
    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert [line.split()[0] for line in lines] == [
        "KNOWN_TRUE",
        "PLANNED_LIE",
        "BLOCK_UNPLANNED",
        "BLOCK_CULPRIT",
    ]


def test_feedback_never_singles_out_the_culprit() -> None:
    culprit = verify_reply(MANOR, "hobbs", [CLARA_KILLED], Ledger(), set())
    other = verify_reply(
        MANOR,
        "hobbs",
        [Claim(subject="hobbs", predicate="killed", object="lord_ashcombe")],
        Ledger(),
        set(),
    )
    assert [c.verdict for c in culprit.checks] == [Verdict.BLOCK_CULPRIT]
    assert [c.verdict for c in other.checks] == [Verdict.BLOCK_UNPLANNED]
    assert culprit.blocked[0].reason == other.blocked[0].reason


def test_lever_logs_one_row_per_blocked_claim(tmp_path: Path) -> None:
    game_id = f"lever-{uuid4().hex}"
    claims = tmp_path / "claims.json"
    claims.write_text(
        "["
        + ",".join(
            c.model_dump_json()
            for c in (HOBBS_IN_BALLROOM, CLARA_IN_LIBRARY, FINCH_IN_GARDEN, CLARA_KILLED)
        )
        + "]"
    )
    argv = ["--case", str(CASES / "manor.json"), "--suspect", "clara", "--claims", str(claims)]

    assert main([*argv, "--log", "--game-id", game_id]) == 1

    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "select rule, claim, action from verifier_events where game_id = :g order by id"
            ),
            {"g": game_id},
        ).all()
    assert [tuple(r) for r in rows] == [
        ("block_unplanned", "dr_finch at garden @3", "block"),
        ("block_culprit", "clara killed lord_ashcombe", "block"),
    ]


@pytest.mark.parametrize("slot", [3, None])
def test_block_reason_does_not_depend_on_the_culprit(slot: int | None) -> None:
    def reason(subject: str, place: str) -> str:
        claim = Claim(subject=subject, predicate="at", object=place, time_slot=slot)
        [check] = verify_reply(MANOR, "hobbs", [claim], Ledger(), set()).blocked
        return check.reason

    culprit_hit = reason("clara", "study")
    assert {reason("clara", "garden"), reason("clara", "library"), reason("mrs_pike", "study")} == {
        culprit_hit
    }


def test_feedback_names_no_verdict_or_fact_id() -> None:
    feedback = verify_reply(
        MANOR, "hobbs", [CLARA_KILLED, CLARA_HAS_OPENER, CLARA_IN_STUDY], Ledger(), set()
    ).feedback()
    for leak in ("culprit", "clara_in_study", "clara_has_opener", "BLOCK"):
        assert leak not in feedback


def test_spent_lie_stays_spent_when_the_clue_is_not_passed_again() -> None:
    exposed = verify_reply(MANOR, "clara", [], told(), {"diary_page"}).commit(2)
    assert verdicts("clara", CLARA_IN_LIBRARY, ledger=exposed) == ["BLOCK_UNPLANNED"]


def test_commit_applies_to_the_ledger_it_was_verified_against() -> None:
    result = verify_reply(MANOR, "clara", [], told(), {"diary_page"})
    [entry] = result.commit(2).entries
    assert entry.status is LieStatus.EXPOSED


def test_ledger_from_another_case_is_refused() -> None:
    gallery = Case.model_validate_json((CASES / "gallery.json").read_text())
    foreign = verify_reply(
        gallery,
        "sam_okafor",
        [Claim(subject="sam_okafor", predicate="at", object="west_hall", time_slot=2)],
        Ledger(),
        set(),
    ).commit(1)
    with pytest.raises(ValueError, match="sam_west_hall_lie"):
        verify_reply(MANOR, "clara", [], foreign, set())


def test_lie_contradicting_a_true_claim_in_the_same_reply_blocks() -> None:
    second = PlannedLie(
        id="finch_library_lie",
        suspect="dr_finch",
        hides_fact="finch_owes_ashcombe",
        claim=Statement(subject="dr_finch", predicate="at", object="library", time_slot=3),
        says="I was in the library.",
    )
    case = MANOR.model_copy(update={"planned_lies": (*MANOR.planned_lies, second)})
    lie = Claim(subject="dr_finch", predicate="at", object="library", time_slot=3)
    result = verify_reply(case, "dr_finch", [FINCH_IN_GARDEN, lie], Ledger(), set())
    assert [c.verdict for c in result.checks] == [Verdict.KNOWN_TRUE, Verdict.BLOCK_UNPLANNED]


def test_stateable_facts_hide_unexposed_culprit_secrets() -> None:
    assert [f.id for f in stateable_facts(MANOR, "hobbs", set())] == [
        "pike_in_kitchen",
        "pike_saw_hobbs",
        "hobbs_in_ballroom",
    ]
    assert "clara_has_opener" in {f.id for f in stateable_facts(MANOR, "hobbs", {"opener_case"})}


def test_killed_takes_no_time_slot() -> None:
    with pytest.raises(ValueError, match="takes no time_slot"):
        Claim(subject="clara", predicate="killed", object="lord_ashcombe", time_slot=3)


CLARA_NOT_IN_STUDY = Claim(subject="clara", predicate="at", object="study", negated=True)


def test_denying_the_hidden_fact_is_the_planned_lie_until_exposed() -> None:
    result = verify_reply(MANOR, "clara", [CLARA_NOT_IN_STUDY], Ledger(), set())
    assert [(c.verdict, c.ref) for c in result.checks] == [
        (Verdict.PLANNED_LIE, "clara_library_lie")
    ]
    assert [e.status for e in result.commit(1).entries] == [LieStatus.TOLD]
    assert verdicts("clara", CLARA_NOT_IN_STUDY, shown="diary_page") == ["BLOCK_UNPLANNED"]


def test_denying_a_known_true_fact_blocks() -> None:
    denial = Claim(subject="hobbs", predicate="at", object="ballroom", time_slot=2, negated=True)
    assert verdicts("hobbs", denial) == ["BLOCK_UNPLANNED"]


def test_innocent_denying_a_culprit_secret_blocks_with_a_neutral_reason() -> None:
    [check] = verify_reply(MANOR, "hobbs", [CLARA_NOT_IN_STUDY], Ledger(), set()).checks
    assert check.verdict is Verdict.BLOCK_UNPLANNED
    other = Claim(subject="mrs_pike", predicate="at", object="study", time_slot=3)
    [plain] = verify_reply(MANOR, "hobbs", [other], Ledger(), set()).checks
    assert check.reason == plain.reason


def test_denial_the_case_does_not_contradict_passes() -> None:
    denials = [
        Claim(subject="clara", predicate="killed", object="lord_ashcombe", negated=True),
        Claim(subject="hobbs", predicate="at", object="study", time_slot=3, negated=True),
    ]
    assert verdicts("hobbs", *denials) == ["DENIAL", "DENIAL"]


def test_denial_renders_with_not() -> None:
    assert CLARA_NOT_IN_STUDY.render() == "not clara at study"
