import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import agents.suspect
from agents.state import Seat
from agents.suspect import Interrogation, TurnReport
from agents.verifier import Verdict
from engine.schema import Case, Id

CASES = Path(__file__).resolve().parents[3] / "cases"
MANOR = Case.model_validate_json((CASES / "manor.json").read_text())
CHOSEN = Path(__file__).resolve().parents[1] / "fixtures" / "suspect_scenarios.json"


@dataclass(frozen=True)
class Turn:
    question: str
    present: tuple[Id, ...] = ()
    drafts: tuple[str, ...] = ()


Script = tuple[Turn, ...]


@dataclass(frozen=True)
class Scenario:
    name: str
    suspect: Id
    candidates: tuple[Script, ...]
    expect: Callable[[Sequence[TurnReport]], bool]


def _verdicts(r: TurnReport) -> set[Verdict]:
    return {c.verdict for c in r.checks}


def _clean(r: TurnReport, verdict: Verdict) -> bool:
    return r.rewrites == 0 and not r.fell_back and verdict in _verdicts(r)


def _lie_then_admit(rs: Sequence[TurnReport]) -> bool:
    lie, admit = rs
    return _clean(lie, Verdict.PLANNED_LIE) and _clean(admit, Verdict.ADMISSION)


def _one_rewrite(rs: Sequence[TurnReport]) -> bool:
    (r,) = rs
    return r.rewrites == 1 and not r.fell_back and bool(r.attempts[0].blocked)


def _fell_back(r: TurnReport) -> bool:
    return r.fell_back and len(r.attempts) == 3 and all(a.blocked for a in r.attempts)


def _fallback(rs: Sequence[TurnReport]) -> bool:
    (r,) = rs
    return _fell_back(r)


def _unchecked_then_plain(rs: Sequence[TurnReport]) -> bool:
    (r,) = rs
    return r.rewrites == 1 and not r.fell_back and r.attempts[0].unchecked


def _lie_then_fallback(rs: Sequence[TurnReport]) -> bool:
    lie, dodge = rs
    return _clean(lie, Verdict.PLANNED_LIE) and _fell_back(dodge)


TEN = Turn("Where were you at ten o'clock last night?")

SCENARIOS = {
    s.name: s
    for s in (
        Scenario(
            "lie_then_admit",
            "clara",
            ((TEN, Turn("Then explain this diary page. Where were you at ten?", ("diary_page",))),),
            _lie_then_admit,
        ),
        Scenario(
            "one_rewrite",
            "clara",
            (
                (Turn("Who did you see tonight, and where, hour by hour?"),),
                (Turn("Walk me through your whole evening, hour by hour."),),
                (Turn("Where were you at eight, nine, ten and eleven? Every hour, no gaps."),),
            ),
            _one_rewrite,
        ),
        Scenario(
            "fallback",
            "hobbs",
            (
                (
                    Turn(
                        "What did you see at ten o'clock?",
                        drafts=(
                            "I saw Miss Clara go into the study at ten with the letter opener.",
                            "Miss Clara killed his lordship, sir. I am sure of it.",
                            "I was in the garden pavilion at ten, sir, with Dr. Finch.",
                        ),
                    ),
                ),
            ),
            _fallback,
        ),
        Scenario(
            "unchecked_rewrite",
            "hobbs",
            (
                (
                    Turn(
                        "Tell me about the family.",
                        drafts=(
                            "Lord Ashcombe was a hard man to serve, sir.",
                            "It is not my place to say, sir.",
                        ),
                    ),
                ),
            ),
            _unchecked_then_plain,
        ),
        Scenario(
            "lie_then_fallback",
            "clara",
            (
                (
                    TEN,
                    Turn(
                        "Look at this diary page. Where were you at ten?",
                        ("diary_page",),
                        drafts=(
                            "I was in the library at ten, just as I told you.",
                            "Mrs. Pike was in the garden pavilion at ten, ask her.",
                            "At nine I was in the kitchen with Mr. Hobbs.",
                        ),
                    ),
                ),
            ),
            _lie_then_fallback,
        ),
    )
}


def chosen(name: str) -> Script:
    raw = json.loads(CHOSEN.read_text())[name]
    script = tuple(Turn(t["question"], tuple(t["present"]), tuple(t["drafts"])) for t in raw)
    if script not in SCENARIOS[name].candidates:
        raise ValueError(f"{name}: recorded script is not a listed candidate")
    return script


def dump(script: Script) -> list[dict[str, Any]]:
    return [
        {"question": t.question, "present": list(t.present), "drafts": list(t.drafts)}
        for t in script
    ]


@contextmanager
def _authored(drafts: tuple[str, ...]) -> Iterator[None]:
    if not drafts:
        yield
        return
    queue = iter(drafts)
    real = agents.suspect._speak

    async def speak(seat: Seat, messages: list[dict[str, Any]], version: str = "") -> str:
        return next(queue)

    agents.suspect._speak = speak
    try:
        yield
    finally:
        agents.suspect._speak = real


async def play(room: Interrogation, suspect: Id, script: Script) -> list[TurnReport]:
    reports = []
    for t in script:
        with _authored(t.drafts):
            reports.append(await room.ask(suspect, t.question, t.present))
    return reports
