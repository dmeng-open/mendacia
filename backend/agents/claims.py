from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from engine.schema import TIMED_PREDICATES, Id, Predicate, Statement

ClaimPredicate = Literal[Predicate, "killed"]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: Id
    predicate: ClaimPredicate
    object: Id
    time_slot: int | None = None

    @model_validator(mode="after")
    def _untimed_takes_no_slot(self) -> Self:
        if self.predicate in ("has", "owes") and self.time_slot is not None:
            raise ValueError(f"'{self.predicate}' takes no time_slot")
        return self

    @property
    def unspecified(self) -> bool:
        return self.time_slot is None and self.predicate in TIMED_PREDICATES

    def states(self, s: Statement) -> bool:
        return (self.subject, self.predicate, self.object, self.time_slot) == (
            s.subject,
            s.predicate,
            s.object,
            s.time_slot,
        )

    def could_mean(self, s: Statement) -> bool:
        return (self.subject, self.predicate, self.object) == (
            s.subject,
            s.predicate,
            s.object,
        ) and (self.time_slot is None or self.time_slot == s.time_slot)

    def render(self) -> str:
        slot = "" if self.time_slot is None else f" @{self.time_slot}"
        return f"{self.subject} {self.predicate} {self.object}{slot}"


def contradicts(a: Statement, b: Statement) -> bool:
    return (
        a.predicate == b.predicate == "at"
        and a.subject == b.subject
        and a.time_slot == b.time_slot
        and a.object != b.object
    )
