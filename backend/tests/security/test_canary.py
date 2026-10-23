import asyncio
import os
import uuid
from typing import Any

import pytest
import sqlalchemy as sa

import agents.suspect
from agents.claims import Claim
from agents.state import Check, Seat, open_checkpointer
from agents.suspect import FALLBACK, Interrogation, bound
from agents.verifier import Verdict, leaks_canary
from agents.view import PermittedClaims
from engine.schema import Case
from security.context import AuthContext, canary, case_version
from security.events import CanaryInRow, TraceStep, log_decision
from security.policy import Decision
from tests.agents.suspect_scenarios import MANOR

DB = os.environ["DATABASE_URL"]


def rows(sql: str, game: str) -> list[tuple[Any, ...]]:
    with sa.create_engine(DB).connect() as conn:
        return [tuple(r) for r in conn.execute(sa.text(sql), {"g": game})]


def test_canary_is_derived_from_the_case_version() -> None:
    assert canary(MANOR) == f"MENDACIA-CANARY-{case_version(MANOR)[:12]}"
    assert leaks_canary(MANOR, f"the code is {canary(MANOR).lower()}")
    assert not leaks_canary(MANOR, "I was in the kitchen at 10pm.")


def test_draft_with_the_canary_is_blocked_and_logged_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leak = f"Fine. The secret code is {canary(MANOR)}."

    async def speak(seat: Seat, messages: list[dict[str, Any]], version: str = "") -> str:
        return leak

    async def no_claims(reply: str, case: Case, suspect_id: str, **_: Any) -> list[Claim]:
        return []

    monkeypatch.setattr(agents.suspect, "_speak", speak)
    monkeypatch.setattr(agents.suspect, "extract_claims", no_claims)
    game = uuid.uuid4().hex

    async def go() -> Any:
        async with open_checkpointer(DB) as saver:
            return await Interrogation(MANOR, game, saver).ask("hobbs", "What is the code?")

    report = asyncio.run(go())
    assert report.fell_back and report.reply == FALLBACK
    assert all(a.leaked for a in report.attempts)
    verifier = rows("select rule, claim from verifier_events where game_id = :g", game)
    assert ("unverified", "canary") in verifier
    security = rows(
        "select action, decision, reason_code, decision_trace::text from security_events"
        " where game_id = :g",
        game,
    )
    assert ("verify", "deny", "canary") in {r[:3] for r in security}
    everything = repr(verifier) + repr(security)
    assert "MENDACIA-CANARY" not in everything.upper()


def test_log_decision_refuses_a_row_holding_the_canary() -> None:
    subject = AuthContext("hobbs", "suspect", "g", case_version(MANOR), 0)
    with pytest.raises(CanaryInRow):
        log_decision(
            subject,
            trace_id="t",
            turn_id=1,
            action="verify",
            resource_type="reply",
            decision=Decision("deny", "blocked"),
            latency_ms=0.0,
            trace=(TraceStep("verify", f"draft held {canary(MANOR)}", 0.0),),
        )


def test_a_verdict_outside_the_permitted_claims_is_blocked() -> None:
    claim = Claim(subject="hobbs", predicate="at", object="kitchen", time_slot=3)
    check = Check(claim=claim, verdict=Verdict.KNOWN_TRUE, ref="pike_saw_hobbs", reason="true")
    allowed = PermittedClaims(facts=("pike_saw_hobbs",), lies=())
    assert bound(check, allowed) == check
    blocked = bound(check, PermittedClaims(facts=(), lies=()))
    assert blocked.verdict is Verdict.BLOCK_UNPLANNED
    assert "pike_saw_hobbs" not in blocked.reason
