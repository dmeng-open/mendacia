import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable

import sqlalchemy as sa

from agents.ledger import LieStatus
from agents.state import SERDE, STATE_TYPES, open_checkpointer
from agents.suspect import FALLBACK, Interrogation, TurnReport
from agents.verifier import Verdict
from tests.agents.suspect_scenarios import MANOR, SCENARIOS, chosen, play

DB = os.environ["DATABASE_URL"]


def run[T](body: Callable[[Interrogation], Awaitable[T]], game_id: str | None = None) -> T:
    async def go() -> T:
        async with open_checkpointer(DB) as saver:
            return await body(Interrogation(MANOR, game_id or uuid.uuid4().hex, saver))

    return asyncio.run(go())


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
    assert [c.verdict for c in lie.checks] == [Verdict.PLANNED_LIE]
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


def test_restart_rebuilds_graph_and_keeps_ledger() -> None:
    game = uuid.uuid4().hex
    first, second = chosen("lie_then_admit")
    run(lambda room: room.ask("clara", first.question, first.present), game)

    async def after_restart(room: Interrogation) -> TurnReport:
        before = await room.state("clara")
        assert [(e.status, e.turn) for e in before.ledger.entries] == [(LieStatus.TOLD, 1)]
        assert len(before.history) == 1
        return await room.ask("clara", second.question, second.present)

    admit = run(after_restart, game)
    assert admit.turn == 2
    assert statuses(admit) == [("clara_library_lie", LieStatus.ADMITTED, 1)]


def test_every_state_type_is_registered_with_the_serializer() -> None:
    names = {t.__name__ for t in STATE_TYPES}
    assert {"SuspectState", "Ledger", "LedgerEntry", "LieStatus", "Claim", "Verdict"} <= names
    assert SERDE is not None


def test_replayed_turn_overhead() -> None:
    script = chosen("lie_then_admit")

    async def turns(room: Interrogation) -> list[float]:
        out = []
        for _ in range(10):
            for t in script:
                started = time.perf_counter()
                await room.ask("clara", t.question, t.present)
                out.append(time.perf_counter() - started)
            room.game_id = uuid.uuid4().hex
        return out

    durations = sorted(run(turns))
    p95 = durations[int(0.95 * len(durations)) - 1]
    print(f"replayed turn p50={durations[len(durations) // 2] * 1000:.0f}ms p95={p95 * 1000:.0f}ms")
    assert p95 < 0.2
