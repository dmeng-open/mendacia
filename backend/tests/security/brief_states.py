from collections.abc import Iterator
from pathlib import Path

from agents.ledger import Ledger, LedgerEntry, LieStatus
from agents.state import SuspectState
from engine.schema import Case

CASES = sorted(Path(__file__).resolve().parents[3].joinpath("cases").glob("*.json"))


def load_cases() -> list[Case]:
    return [Case.model_validate_json(p.read_text()) for p in CASES]


def brief_states(case: Case, me: str) -> Iterator[tuple[str, SuspectState]]:
    shown_sets = [("none", ()), ("all", tuple(c.id for c in case.clues))]
    shown_sets += [(c.id, (c.id,)) for c in case.clues]
    for label, shown in shown_sets:
        yield f"shown={label}", SuspectState(presented=shown)
    for lie in (lie for lie in case.planned_lies if lie.suspect == me):
        for status in LieStatus:
            entry = LedgerEntry(lie=lie, turn=1, status=status)
            yield f"{lie.id}={status.value}", SuspectState(ledger=Ledger(entries=(entry,)))
