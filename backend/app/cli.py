import argparse
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path

import pydantic_ai

from agents.events import log_event
from agents.game_master import (
    GameState,
    Hint,
    new_game,
    next_hint,
    open_document,
    record_reply,
    rule_accusation,
    spend_question,
    timeline,
)
from agents.screening import screen_input
from agents.state import open_checkpointer
from agents.suspect import Interrogation
from app.config import Settings
from engine.schema import Case, Id

HELP = (
    "/suspect <id>  /ask <question>  /read <doc_id>  /present <clue_id>  /hint\n"
    "/accuse <suspect_id> <clue_id> <clue_id>...  /status  /quit"
)

Say = Callable[[str], None]


class Game:
    def __init__(self, case: Case, room: Interrogation, say: Say) -> None:
        self.case = case
        self.room = room
        self.say = say
        self.state: GameState = new_game(case, room.game_id)
        self.suspect: Id | None = None
        self.pending: list[Id] = []
        self.over = False
        self.turns: dict[Id, int] = {}

    def intro(self) -> None:
        self.say(f"{self.case.title}\n{self.case.summary}\n")
        self.say("Suspects:")
        for s in self.case.suspects:
            self.say(f"  {s.id:<12} {s.name}: {s.description}")
        self.say("Documents: " + ", ".join(d.id for d in self.case.documents))
        self.say(self._budget())
        self.say(HELP)

    def _budget(self) -> str:
        return f"{self.state.questions_left} questions, {self.state.hints_left} hints left"

    def _name(self, suspect: Id) -> str:
        return next(s.name for s in self.case.suspects if s.id == suspect)

    async def handle(self, line: str) -> None:
        command, _, rest = line.strip().partition(" ")
        rest = rest.strip()
        match command:
            case "":
                return
            case "/suspect":
                self._choose(rest)
            case "/ask":
                await self._ask(rest)
            case "/read":
                self._read(rest)
            case "/present":
                self._present(rest)
            case "/hint":
                self._hint()
            case "/accuse":
                self._accuse(rest.split())
            case "/status":
                self._status()
            case "/quit":
                self.over = True
            case _ if not command.startswith("/"):
                await self._ask(line.strip())
            case _:
                self.say(f"Unknown command {command}.\n{HELP}")

    def _choose(self, suspect: str) -> None:
        if suspect not in {s.id for s in self.case.suspects}:
            self.say("Choose one of: " + ", ".join(s.id for s in self.case.suspects))
            return
        self.suspect = suspect
        self.pending = []
        self.say(f"You sit down with {self._name(suspect)}.")

    async def _ask(self, question: str) -> None:
        if self.suspect is None:
            self.say("Choose a suspect first with /suspect <id>.")
            return
        if not question:
            self.say("Ask something: /ask <question>")
            return
        if self.state.questions_left <= 0:
            self.say("You have no questions left. Make your accusation with /accuse.")
            return
        turn = self.turns.get(self.suspect, 0) + 1
        screened = screen_input(question)
        if not screened.allowed:
            await asyncio.to_thread(
                log_event,
                game_id=self.room.game_id,
                suspect=self.suspect,
                turn=turn,
                rule="input_screen",
                claim=question,
                action="refuse",
            )
            self.say(f'{self._name(self.suspect)}: "I don\'t follow you, Detective."')
            self.say(f"(That cost no question.) {self._budget()}")
            return
        present, self.pending = self.pending, []
        report = await self.room.ask(self.suspect, question, present)
        self.turns[self.suspect] = turn
        before = set(self.state.discovered)
        self.state = record_reply(
            self.case,
            spend_question(self.state),
            [(c.verdict, c.ref) for c in report.checks],
        )
        self.say(f"{self._name(self.suspect)}: {report.reply}")
        self._announce(before)
        self.say(self._budget())

    def _read(self, doc_id: str) -> None:
        before = set(self.state.discovered)
        try:
            self.state, doc = open_document(self.case, self.state, doc_id)
        except KeyError:
            self.say("No such document. Documents: " + ", ".join(d.id for d in self.case.documents))
            return
        self.say(f"{doc.title}\n  {doc.body}")
        self._announce(before)

    def _present(self, clue_id: str) -> None:
        if self.suspect is None:
            self.say("Choose a suspect first with /suspect <id>.")
            return
        if clue_id not in self.state.discovered:
            self.say("You can present only a clue you have found. See /status.")
            return
        self.pending.append(clue_id)
        self.say(f"You will show {clue_id} with your next question.")

    def _hint(self) -> None:
        self.state, hint = next_hint(self.case, self.state)
        prefix = "Hint: " if isinstance(hint, Hint) else ""
        self.say(f"{prefix}{hint.text} {self._budget()}")

    def _accuse(self, args: list[str]) -> None:
        if not args:
            self.say("Usage: /accuse <suspect_id> <clue_id> <clue_id>...")
            return
        suspect, cited = args[0], args[1:]
        unknown = [c for c in cited if c not in self.state.discovered]
        if unknown:
            self.say("You can cite only clues you have found: " + ", ".join(unknown))
            return
        ruling = rule_accusation(self.case, suspect, cited)
        self.say(ruling.text)
        if ruling.correct:
            self.say("Chain clues cited: " + ", ".join(ruling.chain_cited))
            self.say("What really happened:")
            for line in timeline(self.case):
                self.say(f"  {line}")
        self.over = True

    def _status(self) -> None:
        self.say(self._budget())
        self.say("Questioning: " + (self._name(self.suspect) if self.suspect else "nobody"))
        self.say("Clues found:")
        for c in self.case.clues:
            if c.id in self.state.discovered:
                self.say(f"  {c.id:<26} {c.description}")
        if not self.state.discovered:
            self.say("  none yet")
        self.say("Documents read: " + (", ".join(self.state.opened) or "none"))

    def _announce(self, before: set[Id]) -> None:
        for c in self.case.clues:
            if c.id in self.state.discovered and c.id not in before:
                self.say(f"New clue: {c.id}: {c.description}")


async def play(
    case: Case, game_id: str, lines: AsyncIterator[str], say: Say = print, *, echo: bool = True
) -> Game:
    async with open_checkpointer(Settings().database_url) as saver:
        game = Game(case, Interrogation(case, game_id, saver), say)
        game.intro()
        async for line in lines:
            if echo:
                say(f"> {line}")
            await game.handle(line)
            if game.over:
                break
        return game


async def _stdin() -> AsyncIterator[str]:
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            return
        yield line.rstrip("\n")


def main(argv: Sequence[str] | None = None) -> int:
    pydantic_ai.BANNER_ENABLED = False
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--game-id", default=None)
    args = parser.parse_args(argv)
    case = Case.model_validate_json(args.case.read_text())
    game_id = args.game_id or uuid.uuid4().hex
    asyncio.run(play(case, game_id, _stdin(), echo=not sys.stdin.isatty()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
