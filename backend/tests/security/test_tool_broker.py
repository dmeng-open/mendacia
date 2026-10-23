import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from security.abuse import ABUSE_STRIKES, TOKEN_CAP
from security.context import ActorType, AuthContext
from security.tool_broker import TOOLS, Denied, ToolBroker, ToolName, ToolSpec, registry_table

DB = os.environ["DATABASE_URL"]
REPO = Path(__file__).resolve().parents[3]


def ctx(game: str, actor: ActorType = "player") -> AuthContext:
    return AuthContext(game, actor, game, "cv", 0)


def run[T](
    body: Callable[[ToolBroker], Awaitable[T]], tools: Mapping[ToolName, ToolSpec] = TOOLS
) -> T:
    async def go() -> T:
        engine = create_async_engine(DB)
        try:
            return await body(ToolBroker(engine, tools))
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def call(
    broker: ToolBroker, subject: AuthContext, tool: str, args: Mapping[str, object]
) -> str:
    try:
        async with broker.authorized_call(subject, tool, args, uuid.uuid4().hex) as c:
            c.settle("ok")
    except Denied as d:
        return d.code
    return "allowed"


def rows(game: str) -> list[tuple[Any, ...]]:
    with sa.create_engine(DB).connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                sa.text(
                    "select action, decision, reason_code from security_events "
                    "where game_id = :g order by id"
                ),
                {"g": game},
            )
        ]


ASK = {"suspect": "hobbs", "question": "Where were you at ten?"}


def test_unknown_tool_is_denied() -> None:
    game = uuid.uuid4().hex
    assert run(lambda b: call(b, ctx(game), "reveal_solution", {})) == "unknown_tool"
    assert rows(game) == [("unknown_tool", "deny", "unknown_tool")]


def test_write_tool_called_by_a_read_only_actor_is_denied() -> None:
    game = uuid.uuid4().hex
    subject = ctx(game, "eval_worker")
    assert run(lambda b: call(b, subject, "open_document", {"doc_id": "dinner_menu"})) == (
        "actor_not_allowed"
    )
    assert run(lambda b: call(b, subject, "read_visible_evidence", {"query": "x"})) == "allowed"
    assert rows(game) == [
        ("open_document", "deny", "actor_not_allowed"),
        ("read_visible_evidence", "allow", "ok"),
    ]


@pytest.mark.parametrize(
    "args",
    [
        {"suspect": 7, "question": "Where were you?"},
        {"suspect": "hobbs"},
        {"suspect": "Hobbs; drop table", "question": "x"},
        {**ASK, "role": "game_master"},
        {"suspect": "hobbs", "question": "x" * 501},
    ],
)
def test_bad_argument_types_are_denied(args: dict[str, object]) -> None:
    game = uuid.uuid4().hex
    assert run(lambda b: call(b, ctx(game), "ask_question", args)) == "bad_args"
    assert rows(game) == [("ask_question", "deny", "bad_args")]


def test_an_exhausted_budget_is_denied() -> None:
    game = uuid.uuid4().hex
    tools: dict[ToolName, ToolSpec] = {"request_hint": replace(TOOLS["request_hint"], budget=2)}

    async def body(b: ToolBroker) -> list[str]:
        return [await call(b, ctx(game), "request_hint", {}) for _ in range(3)]

    assert run(body, tools) == ["allowed", "allowed", "budget_exhausted"]
    assert rows(game)[-1] == ("request_hint", "deny", "budget_exhausted")


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_a_suspect_gets_no_tool(tool: str) -> None:
    game = uuid.uuid4().hex
    assert run(lambda b: call(b, ctx(game, "suspect"), tool, {})) == "actor_not_allowed"
    assert rows(game) == [(tool, "deny", "actor_not_allowed")]


def test_registry_has_no_reveal_tool_and_no_suspect_actor() -> None:
    assert "reveal_solution" not in TOOLS
    assert all("suspect" not in spec.actors for spec in TOOLS.values())


def test_each_call_writes_exactly_one_row() -> None:
    game = uuid.uuid4().hex
    assert run(lambda b: call(b, ctx(game), "request_hint", {})) == "allowed"
    assert rows(game) == [("request_hint", "allow", "ok")]


def test_a_failing_handler_is_logged_unavailable_and_reraised() -> None:
    game = uuid.uuid4().hex

    async def body(b: ToolBroker) -> None:
        async with b.authorized_call(ctx(game), "request_hint", {}, "k1"):
            raise RuntimeError("database went away")

    with pytest.raises(RuntimeError):
        run(body)
    assert rows(game) == [("request_hint", "deny", "unavailable")]


def test_strikes_put_model_tools_on_cooldown_but_not_documents() -> None:
    game = uuid.uuid4().hex

    async def body(b: ToolBroker) -> list[str]:
        for _ in range(ABUSE_STRIKES):
            await call(b, ctx(game), "ask_question", {"suspect": 1})
        return [
            await call(b, ctx(game), "ask_question", ASK),
            await call(b, ctx(game), "open_document", {"doc_id": "dinner_menu"}),
        ]

    assert run(body) == ["cooldown", "allowed"]


def test_the_token_cap_puts_model_tools_on_cooldown() -> None:
    game = uuid.uuid4().hex
    with sa.create_engine(DB).begin() as conn:
        conn.execute(
            sa.text(
                "insert into llm_calls (model, role, purpose, game_id, prompt_tokens, "
                "completion_tokens, cost_usd, latency_ms, mode) "
                "values ('m', 'fast', 'suspect', :g, :t, 0, 0, 0, 'replay')"
            ),
            {"g": game, "t": TOKEN_CAP},
        )
    assert run(lambda b: call(b, ctx(game), "ask_question", ASK)) == "cooldown"
    assert run(lambda b: call(b, ctx(game), "request_hint", {})) == "allowed"


def test_adr_010_lists_the_registry() -> None:
    adr = (REPO / "docs" / "adr" / "010-tool-broker.md").read_text()
    for line in registry_table():
        assert line in adr, line
