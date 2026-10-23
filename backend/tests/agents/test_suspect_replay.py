import asyncio
import math
import os
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
import sqlalchemy as sa

from agents.ledger import LieStatus
from agents.state import Talk, TurnInput
from agents.suspect import FALLBACK, Interview, TurnReport
from agents.verifier import Verdict
from tests.agents.suspect_scenarios import MANOR, SCENARIOS, Turn, chosen, play

DB = os.environ["DATABASE_URL"]


def run[T](body: Callable[[Interview], Coroutine[Any, Any, T]], game_id: str | None = None) -> T:
    return asyncio.run(body(Interview(MANOR, game_id or uuid.uuid4().hex)))


def scenario(name: str, game_id: str | None = None) -> list[TurnReport]:
    s = SCENARIOS[name]
    return run(lambda room: play(room, s.suspect, chosen(name)), game_id)


def events(game_id: str) -> list[tuple[str, str, str, int]]:
    with sa.create_engine(DB).connect() as conn:
        rows = conn.execute(
            sa.text(
                "select action, rule, claim, turn from verifier_events"
                " where game_id = :g order by id"
            ),
            {"g": game_id},
        )
        return [tuple(r) for r in rows]


def statuses(report: TurnReport) -> list[tuple[str, LieStatus, int]]:
    return [(e.lie.id, e.status, e.turn) for e in report.ledger]


def test_suspect_tells_its_planned_lie() -> None:
    lie, _ = scenario("lie_then_admit")
    assert {c.verdict for c in lie.checks} == {Verdict.PLANNED_LIE}
    assert lie.rewrites == 0
    assert statuses(lie) == [("clara_library_lie", LieStatus.TOLD, 1)]


def test_suspect_admits_hidden_fact_after_clue() -> None:
    _, admit = scenario("lie_then_admit")
    assert Verdict.ADMISSION in {c.verdict for c in admit.checks}
    assert statuses(admit) == [("clara_library_lie", LieStatus.ADMITTED, 1)]


def test_blocked_draft_passes_after_one_rewrite() -> None:
    game = uuid.uuid4().hex
    (r,) = scenario("one_rewrite", game)
    assert r.rewrites == 1 and not r.fell_back
    assert r.reply == r.attempts[1].draft
    assert not any(c.verdict.blocks for c in r.checks)
    logged = events(game)
    assert {a for a, *_ in logged} == {"rewrite"}
    assert len(logged) == len(r.attempts[0].blocked)


def test_three_blocked_drafts_fall_back_and_log() -> None:
    game = uuid.uuid4().hex
    (r,) = scenario("fallback", game)
    assert r.fell_back and r.reply == FALLBACK and r.rewrites == 2
    logged = events(game)
    assert [a for a, *_ in logged].count("fallback") == len(r.attempts[-1].blocked) >= 1
    assert "block_culprit" in {rule for _, rule, *_ in logged}
    assert r.ledger == ()


def test_fallback_still_commits_the_exposure() -> None:
    _, dodge = scenario("lie_then_fallback")
    assert dodge.reply == FALLBACK
    assert statuses(dodge) == [("clara_library_lie", LieStatus.EXPOSED, 1)]


def test_a_fresh_graph_continues_from_the_stored_talk() -> None:
    game = uuid.uuid4().hex
    first, second = chosen("lie_then_admit")
    lie = run(lambda room: room.ask("clara", first.question, first.present), game)
    stored = Talk.model_validate_json(lie.talk.model_dump_json())
    assert [(e.status, e.turn) for e in stored.ledger.entries] == [(LieStatus.TOLD, 1)]
    assert len(stored.history) == 1

    async def after_restart(room: Interview) -> TurnReport:
        room.talks["clara"] = stored
        return await room.ask("clara", second.question, second.present)

    admit = run(after_restart, game)
    assert admit.turn == 2
    assert statuses(admit) == [("clara_library_lie", LieStatus.ADMITTED, 1)]


def test_a_turn_writes_nothing_until_its_caller_commits() -> None:
    first, _ = chosen("lie_then_admit")
    game = uuid.uuid4().hex

    async def body(room: Interview) -> TurnReport:
        return await room.room.ask(
            Talk(), "clara", TurnInput(question=first.question), state_version=7
        )

    report = asyncio.run(body(Interview(MANOR, game)))
    with sa.create_engine(DB).connect() as conn:
        logged = conn.execute(
            sa.text("select count(*) from security_events where game_id = :g"), {"g": game}
        ).scalar_one()
    assert logged == 0
    assert [r.action for r in report.audit] == ["retrieve", "verify", "commit_turn"]
    assert {r.state_version for r in report.audit} == {7}


def test_unknown_document_is_refused_before_the_turn() -> None:
    async def body(room: Interview) -> None:
        with pytest.raises(ValueError, match="unknown documents"):
            await room.ask("clara", "What is this?", documents=["no_such_doc"])

    run(body)


def test_unknown_clue_is_refused_before_the_turn_and_leaves_the_thread_usable() -> None:
    first, _ = chosen("lie_then_admit")

    async def body(room: Interview) -> TurnReport:
        with pytest.raises(ValueError, match="unknown clues"):
            await room.ask("clara", first.question, ["no_such_clue"])
        with pytest.raises(ValueError, match="unknown suspect"):
            await room.ask("nobody", first.question)
        return await room.ask("clara", first.question, first.present)

    lie = run(body)
    assert {c.verdict for c in lie.checks} == {Verdict.PLANNED_LIE}


def test_concurrent_asks_on_one_suspect_run_one_after_the_other() -> None:
    first, second = chosen("lie_then_admit")

    async def body(room: Interview) -> tuple[list[int], int]:
        lie, admit = await asyncio.gather(
            room.ask("clara", first.question, first.present),
            room.ask("clara", second.question, second.present),
        )
        return [lie.turn, admit.turn], len(room.state("clara").history)

    assert run(body) == ([1, 2], 2)


def test_claimless_reply_that_names_the_case_is_rewritten() -> None:
    (r,) = scenario("unchecked_rewrite")
    assert r.attempts[0].unchecked and not r.attempts[0].claims
    assert r.reply == r.attempts[1].draft and not r.fell_back


def test_empty_draft_falls_back_without_extraction_and_logs_a_row() -> None:
    game = uuid.uuid4().hex
    (r,) = run(lambda room: play(room, "hobbs", (Turn("Anything?", drafts=("",)),)), game)
    assert r.fell_back and r.reply == FALLBACK and len(r.attempts) == 1
    assert events(game) == [("fallback", "unverified", "empty draft", 1)]


def test_replayed_turn_overhead() -> None:
    script = chosen("lie_then_admit")

    async def turns(room: Interview) -> list[float]:
        out = []
        for _ in range(50):
            for t in script:
                started = time.perf_counter()
                await room.ask("clara", t.question, t.present)
                out.append(time.perf_counter() - started)
            room.talks.clear()
        return out

    durations = sorted(run(turns))
    p95 = durations[math.ceil(0.95 * len(durations)) - 1]
    slowest = " ".join(f"{d * 1000:.0f}" for d in durations[-5:])
    print(
        f"replayed turn n={len(durations)} p50={durations[len(durations) // 2] * 1000:.0f}ms"
        f" p95={p95 * 1000:.0f}ms slowest={slowest}ms"
    )
    assert p95 < 0.2
