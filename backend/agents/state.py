import types
import typing
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel, ConfigDict

from agents.claims import Claim
from agents.events import Rule
from agents.ledger import Ledger
from agents.verifier import ClaimCheck, Verdict
from engine.schema import Case, Id

HISTORY_WINDOW = 6
UNCHECKED = "say it again in short, plain sentences: what you know, or that you do not know"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Exchange(_Frozen):
    question: str
    shown: tuple[Id, ...]
    reply: str


class Check(_Frozen):
    claim: Claim
    verdict: Verdict
    ref: Id | None
    reason: str

    @classmethod
    def of(cls, c: ClaimCheck) -> "Check":
        return cls(claim=c.claim, verdict=c.verdict, ref=c.ref, reason=c.reason)

    @property
    def rule(self) -> Rule:
        return ClaimCheck(self.claim, self.verdict, self.ref, self.reason).rule


class Attempt(_Frozen):
    draft: str
    claims: tuple[Claim, ...] = ()
    checks: tuple[Check, ...] = ()
    unreadable: bool = False
    unchecked: bool = False

    @property
    def blocked(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.verdict.blocks)

    @property
    def verified(self) -> bool:
        return bool(self.draft) and not (self.unreadable or self.unchecked or self.blocked)

    @property
    def feedback(self) -> str:
        if self.unreadable or self.unchecked:
            return f"- {UNCHECKED}"
        return "\n".join(f"- {c.claim.render()}: {c.reason}" for c in self.blocked)


class TurnInput(_Frozen):
    question: str
    present: tuple[Id, ...] = ()


class SuspectState(_Frozen):
    ledger: Ledger = Ledger()
    presented: tuple[Id, ...] = ()
    history: tuple[Exchange, ...] = ()

    question: str = ""
    present: tuple[Id, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    fell_back: bool = False

    @property
    def turn(self) -> int:
        return len(self.history) + 1

    @property
    def shown(self) -> tuple[Id, ...]:
        return tuple(sorted({*self.presented, *self.present}))

    @property
    def recent(self) -> tuple[Exchange, ...]:
        return self.history[-HISTORY_WINDOW:]


@dataclass(frozen=True)
class Seat:
    case: Case
    suspect: Id
    game_id: str

    @property
    def thread_id(self) -> str:
        return f"{self.game_id}:{self.suspect}"

    @property
    def config(self) -> RunnableConfig:
        return {"configurable": {"thread_id": self.thread_id}}


def _model_types(root: type) -> Iterator[type]:
    seen: set[type] = set()
    stack: list[object] = [root]
    while stack:
        tp = stack.pop()
        if isinstance(tp, type) and issubclass(tp, BaseModel | Enum):
            if tp in seen:
                continue
            seen.add(tp)
            yield tp
            if issubclass(tp, BaseModel):
                stack += [f.annotation for f in tp.model_fields.values()]
        elif isinstance(tp, types.UnionType) or typing.get_origin(tp) is not None:
            stack += typing.get_args(tp)


STATE_TYPES = tuple(_model_types(SuspectState))
SERDE = JsonPlusSerializer(allowed_msgpack_modules=list(STATE_TYPES))


def libpq_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(libpq_url(database_url), serde=SERDE) as saver:
        await saver.setup()
        yield saver
