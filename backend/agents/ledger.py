from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from engine.schema import Id, PlannedLie


class LieStatus(StrEnum):
    TOLD = "told"
    EXPOSED = "exposed"
    ADMITTED = "admitted"


_RANK = {LieStatus.TOLD: 0, LieStatus.EXPOSED: 1, LieStatus.ADMITTED: 2}


class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lie: PlannedLie
    turn: int
    status: LieStatus

    @property
    def suspect(self) -> Id:
        return self.lie.suspect


@dataclass(frozen=True)
class Transition:
    lie: PlannedLie
    to: LieStatus


class Ledger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: tuple[LedgerEntry, ...] = ()

    @model_validator(mode="after")
    def _one_entry_per_lie(self) -> Self:
        ids = [e.lie.id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("a planned lie has more than one ledger entry")
        return self

    def of(self, suspect_id: Id) -> tuple[LedgerEntry, ...]:
        return tuple(e for e in self.entries if e.suspect == suspect_id)

    def apply(self, transitions: Iterable[Transition], turn: int) -> "Ledger":
        by_id = {e.lie.id: e for e in self.entries}
        for t in transitions:
            current = by_id.get(t.lie.id)
            if current is None:
                by_id[t.lie.id] = LedgerEntry(lie=t.lie, turn=turn, status=t.to)
            elif _RANK[t.to] > _RANK[current.status]:
                by_id[t.lie.id] = current.model_copy(update={"status": t.to})
        return Ledger(entries=tuple(by_id.values()))
