import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from engine.schema import Id
from security import abuse
from security.context import ActorType, AuthContext
from security.events import AuditRow, TraceStep, audit_row, insert_rows
from security.policy import Decision

ToolName = Literal[
    "ask_question",
    "confront_evidence",
    "open_document",
    "request_hint",
    "submit_accusation",
    "read_visible_evidence",
    "query_suspect_knowledge",
    "lookup_public_statement",
]
SideEffect = Literal["none", "game_state", "game_state+model"]
DenyCode = Literal[
    "unknown_tool", "actor_not_allowed", "bad_args", "budget_exhausted", "cooldown", "stale_state"
]


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AskArgs(Args):
    suspect: Id
    question: str = Field(min_length=1, max_length=500)


class ConfrontArgs(AskArgs):
    present: tuple[Id, ...] = Field(default=(), max_length=12)
    documents: tuple[Id, ...] = Field(default=(), max_length=12)


class OpenArgs(Args):
    doc_id: Id


class HintArgs(Args):
    pass


class AccuseArgs(Args):
    suspect: Id
    cited: tuple[Id, ...] = Field(max_length=12)


class SearchArgs(Args):
    query: str = Field(max_length=500)
    k: int = Field(default=10, ge=1, le=20)


class SuspectArgs(Args):
    suspect: Id


@dataclass(frozen=True)
class ToolSpec:
    args: type[Args]
    read_only: bool
    side_effect: SideEffect
    actors: frozenset[ActorType]
    budget: int

    @property
    def calls_model(self) -> bool:
        return self.side_effect == "game_state+model"


PLAYERS: frozenset[ActorType] = frozenset({"player", "detective_bot"})

TOOLS: Mapping[ToolName, ToolSpec] = MappingProxyType(
    {
        "ask_question": ToolSpec(AskArgs, False, "game_state+model", PLAYERS, 60),
        "confront_evidence": ToolSpec(ConfrontArgs, False, "game_state+model", PLAYERS, 60),
        "open_document": ToolSpec(OpenArgs, False, "game_state", PLAYERS, 100),
        "request_hint": ToolSpec(HintArgs, False, "game_state", PLAYERS, 10),
        "submit_accusation": ToolSpec(AccuseArgs, False, "game_state", PLAYERS, 3),
        "read_visible_evidence": ToolSpec(SearchArgs, True, "none", PLAYERS | {"eval_worker"}, 300),
        "query_suspect_knowledge": ToolSpec(
            SuspectArgs, True, "none", frozenset({"game_master"}), 200
        ),
        "lookup_public_statement": ToolSpec(SuspectArgs, True, "none", PLAYERS, 200),
    }
)


def registry_table(tools: Mapping[ToolName, ToolSpec] = TOOLS) -> list[str]:
    rows = [
        "| Tool | Arguments | Read only | Side effect | Actors | Budget per game |",
        "|---|---|---|---|---|---|",
    ]
    for name, spec in tools.items():
        args = ", ".join(f"`{f}`" for f in spec.args.model_fields) or "none"
        actors = ", ".join(f"`{a}`" for a in sorted(spec.actors))
        rows.append(
            f"| `{name}` | {args} | {'yes' if spec.read_only else 'no'} | "
            f"`{spec.side_effect}` | {actors} | {spec.budget} |"
        )
    return rows


class Denied(Exception):
    def __init__(self, code: str, retry_after_s: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after_s = retry_after_s


@dataclass
class Call[A: Args]:
    ctx: AuthContext
    tool: ToolName
    args: A
    key: str
    trace_id: str
    steps: list[TraceStep]
    settled: tuple[str, bool] = ("ok", True)
    written: bool = field(default=False)

    def parsed[T: Args](self, kind: type[T]) -> T:
        assert isinstance(self.args, kind), (self.tool, type(self.args))
        return self.args

    def row(
        self, reason: str, *, allowed: bool = True, extra: Sequence[TraceStep] = ()
    ) -> AuditRow:
        return _row(
            self.ctx, self.tool, self.key, self.trace_id, [*self.steps, *extra], reason, allowed
        )

    def settle(self, reason: str, *, allowed: bool = True) -> None:
        self.settled = (reason, allowed)


def _row(
    ctx: AuthContext,
    action: str,
    key: str,
    trace_id: str,
    steps: Sequence[TraceStep],
    reason: str,
    allowed: bool,
) -> AuditRow:
    decision = Decision("allow" if allowed else "deny", reason)
    return audit_row(
        ctx,
        trace_id=trace_id,
        turn_id=None,
        action=action,
        resource_type="tool",
        decision=decision,
        trace=steps,
        replay_ref=key,
    )


class ToolBroker:
    def __init__(self, engine: AsyncEngine, tools: Mapping[ToolName, ToolSpec] = TOOLS) -> None:
        self._engine = engine
        self.tools = tools

    async def log(self, rows: Sequence[AuditRow]) -> None:
        async with self._engine.begin() as conn:
            await insert_rows(conn, rows)

    async def record(
        self, ctx: AuthContext, action: str, key: str, reason: str, *, allowed: bool
    ) -> None:
        step = TraceStep(step="auth", outcome=reason, ms=0.0)
        await self.log([_row(ctx, action, key, uuid.uuid4().hex, [step], reason, allowed)])

    @asynccontextmanager
    async def authorized_call(
        self, ctx: AuthContext, tool: str, args: Mapping[str, object], idempotency_key: str
    ) -> AsyncIterator[Call[Args]]:
        trace_id = uuid.uuid4().hex
        steps: list[TraceStep] = []
        clock = time.perf_counter()

        def step(name: Literal["auth", "policy"], outcome: str) -> None:
            nonlocal clock
            now = time.perf_counter()
            steps.append(TraceStep(step=name, outcome=outcome, ms=round((now - clock) * 1000, 3)))
            clock = now

        async def deny(action: str, code: str, retry: int | None = None) -> Denied:
            step("policy", code)
            await self.log([_row(ctx, action, idempotency_key, trace_id, steps, code, False)])
            return Denied(code, retry)

        if tool not in self.tools:
            raise await deny("unknown_tool", "unknown_tool")
        name = cast(ToolName, tool)
        spec = self.tools[name]
        step("auth", f"actor={ctx.actor_type}")
        if ctx.actor_type not in spec.actors:
            raise await deny(name, "actor_not_allowed")
        try:
            parsed = spec.args.model_validate(args)
        except ValidationError:
            raise await deny(name, "bad_args") from None
        async with self._engine.connect() as conn:
            use = await abuse.usage(conn, ctx.game_id, self.tools)
        refusal = abuse.decide(name, spec.budget, spec.calls_model, use)
        if refusal is not None:
            raise await deny(name, refusal.code, refusal.retry_after_s)
        step("policy", "allowed")
        call: Call[Args] = Call(ctx, name, parsed, idempotency_key, trace_id, steps)
        try:
            yield call
        except Denied as d:
            await self.log([call.row(d.code, allowed=False)])
            raise
        except BaseException:
            with suppress(Exception):
                await self.log([call.row("unavailable", allowed=False)])
            raise
        if not call.written:
            reason, allowed = call.settled
            await self.log([call.row(reason, allowed=allowed)])
