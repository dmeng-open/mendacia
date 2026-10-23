from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from agents.claims import Claim
from agents.events import Rule
from agents.ledger import Ledger
from agents.verifier import ClaimCheck, Verdict
from agents.view import Exchange, Frozen, PermittedClaims, SuspectView
from engine.schema import Case, Id
from security.events import AuditRow

HISTORY_WINDOW = 6
UNCHECKED = "say it again in short, plain sentences: what you know, or that you do not know"


class Check(Frozen):
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


class Attempt(Frozen):
    draft: str
    claims: tuple[Claim, ...] = ()
    checks: tuple[Check, ...] = ()
    unreadable: bool = False
    unchecked: bool = False
    leaked: bool = False

    @property
    def blocked(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.verdict.blocks)

    @property
    def verified(self) -> bool:
        return bool(self.draft) and not (
            self.unreadable or self.unchecked or self.leaked or self.blocked
        )

    @property
    def feedback(self) -> str:
        if self.unreadable or self.unchecked or self.leaked:
            return f"- {UNCHECKED}"
        return "\n".join(f"- {c.claim.render()}: {c.reason}" for c in self.blocked)


class TurnInput(Frozen):
    question: str
    present: tuple[Id, ...] = ()
    documents: tuple[Id, ...] = ()


class Talk(Frozen):
    ledger: Ledger = Ledger()
    presented: tuple[Id, ...] = ()
    history: tuple[Exchange, ...] = ()


class SuspectState(Talk):
    question: str = ""
    present: tuple[Id, ...] = ()
    documents: tuple[Id, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    fell_back: bool = False
    trace_id: str = ""
    view: SuspectView | None = None
    permitted: PermittedClaims | None = None
    audit: tuple[AuditRow, ...] = ()

    @property
    def turn(self) -> int:
        return len(self.history) + 1

    @property
    def shown(self) -> tuple[Id, ...]:
        return tuple(sorted({*self.presented, *self.present}))

    @property
    def recent(self) -> tuple[Exchange, ...]:
        return self.history[-HISTORY_WINDOW:]


Stage = Literal["validating"]
OnStage = Callable[[Stage], Awaitable[None]]


@dataclass(frozen=True)
class Seat:
    case: Case
    suspect: Id
    game_id: str
    state_version: int
    on_stage: OnStage | None = None
