import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from agents.claims import Claim
from agents.ledger import Ledger, LieStatus
from agents.verifier import BlockedReply, Verdict, main, verify_reply
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
    return verify_reply(case, "clara", [CLARA_IN_LIBRARY], Ledger(), set()).commit(Ledger(), 1)


def test_known_true() -> None:
    assert verdicts("clara", HOBBS_IN_BALLROOM) == ["KNOWN_TRUE"]


def test_planned_lie_records_told() -> None:
    [entry] = told().entries
    assert (entry.lie.id, entry.status, entry.turn) == ("clara_library_lie", LieStatus.TOLD, 1)


def test_admission_moves_told_to_admitted() -> None:
    result = verify_reply(MANOR, "clara", [CLARA_IN_STUDY], told(), {"diary_page"})
    assert [c.verdict for c in result.checks] == [Verdict.ADMISSION]
    [entry] = result.commit(told(), 2).entries
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
    admitted = verify_reply(MANOR, "clara", [CLARA_IN_STUDY], told(), {"diary_page"}).commit(
        told(), 2
    )
    assert verdicts("clara", CLARA_IN_LIBRARY, ledger=admitted) == ["BLOCK_UNPLANNED"]
    assert verdicts("clara", CLARA_IN_STUDY, CLARA_IN_LIBRARY, shown="diary_page") == [
        "ADMISSION",
        "BLOCK_UNPLANNED",
    ]


def test_no_claims_pass_and_record_exposure() -> None:
    result = verify_reply(MANOR, "clara", [], told(), {"diary_page"})
    assert result.passed
    [entry] = result.commit(told(), 2).entries
    assert entry.status is LieStatus.EXPOSED


def test_verdicts_ignore_claim_order() -> None:
    claims = [HOBBS_IN_BALLROOM, CLARA_IN_LIBRARY, FINCH_IN_GARDEN, CLARA_KILLED, CLARA_IN_STUDY]
    forward = verdicts("clara", *claims, shown="diary_page")
    assert verdicts("clara", *reversed(claims), shown="diary_page") == forward[::-1]


def test_commit_is_idempotent_and_refuses_blocked_replies() -> None:
    result = verify_reply(MANOR, "clara", [CLARA_IN_LIBRARY], Ledger(), set())
    once = result.commit(Ledger(), 1)
    assert result.commit(once, 1) == once
    with pytest.raises(BlockedReply, match="you do not know this to be true"):
        verify_reply(MANOR, "clara", [CLARA_KILLED], Ledger(), set()).commit(Ledger(), 1)


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
