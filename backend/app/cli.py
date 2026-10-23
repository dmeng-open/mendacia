import argparse
import asyncio
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path

from app.config import Settings
from app.db import make_engine
from app.games import GameService, Outcome
from app.schemas import GameView
from app.session import Session
from engine.schema import Case, Id
from security.tool_broker import ToolName

HELP = (
    "/suspect <id>  /ask <question>  /read <doc_id>  /present <clue_or_doc_id>  /hint\n"
    "/accuse <suspect_id> <clue_id> <clue_id>...  /status  /quit"
)

Say = Callable[[str], None]


class Game:
    """Renders the shared game path (app.games) as a terminal game with raw ids."""

    def __init__(
        self, case: Case, games: GameService, session: Session, view: GameView, say: Say
    ) -> None:
        self.case = case
        self.games = games
        self.session = session
        self.view = view
        self.say = say
        self.suspect: Id | None = None
        self.pending: list[Id] = []
        self.pending_docs: list[Id] = []
        self.over = False

    def intro(self) -> None:
        self.say(f"{self.case.title}\n{self.case.summary}\n")
        self.say("Suspects:")
        for s in self.case.suspects:
            self.say(f"  {s.id:<12} {s.name}: {s.description}")
        self.say(self._documents())
        self.say(self._budget())
        self.say(HELP)

    def _documents(self) -> str:
        return "Documents: " + ", ".join(d.id for d in self.view.documents)

    def _budget(self) -> str:
        q, h = self.view.questions_left, self.view.hints_left
        return f"{q} question{'' if q == 1 else 's'}, {h} hint{'' if h == 1 else 's'} left"

    def _name(self, suspect: Id) -> str:
        return next(s.name for s in self.case.suspects if s.id == suspect)

    async def _run(self, tool: ToolName, args: dict[str, object]) -> Outcome:
        out = await self.games.execute(
            self.session,
            tool,
            args,
            key=uuid.uuid4().hex,
            expected_version=self.view.state_version,
        )
        self.view = out.view or self.view
        return out

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
                await self._read(rest)
            case "/present":
                self._present(rest)
            case "/hint":
                await self._hint()
            case "/accuse":
                await self._accuse(rest.split())
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
        self.pending_docs = []
        self.say(f"You sit down with {self._name(suspect)}.")

    async def _ask(self, question: str) -> None:
        if self.suspect is None:
            self.say("Choose a suspect first with /suspect <id>.")
            return
        if not question:
            self.say("Ask something: /ask <question>")
            return
        if self.view.questions_left <= 0:
            self.say("You have no questions left. Make your accusation with /accuse.")
            return
        present, self.pending = self.pending, []
        handed, self.pending_docs = self.pending_docs, []
        args: dict[str, object] = {"suspect": self.suspect, "question": question}
        tool: ToolName = "ask_question"
        if present or handed:
            tool = "confront_evidence"
            args |= {"present": present, "documents": handed}
        out = await self._run(tool, args)
        name = self._name(self.suspect)
        if out.code == "screened":
            self.say(f'{name}: "{out.reply}"')
            self.say(f"(That cost no question.) {self._budget()}")
            return
        if out.reply is not None:
            self.say(f"{name}: {out.reply.removeprefix(f'{name}:').strip()}")
        if out.code is not None:
            self.say(f"({out.code}: that cost no question.) {self._budget()}")
            return
        self._announce(out)
        self.say(self._budget())

    async def _read(self, doc_id: str) -> None:
        if doc_id not in {d.id for d in self.case.documents}:
            self.say(f"No such document. {self._documents()}")
            return
        out = await self._run("open_document", {"doc_id": doc_id})
        if out.document is None:
            self.say("That document is locked.")
            return
        self.say(f"{out.document.title}\n  {out.document.body}")
        self._announce(out)

    def _present(self, item_id: str) -> None:
        if self.suspect is None:
            self.say("Choose a suspect first with /suspect <id>.")
            return
        if item_id in {d.id for d in self.view.documents if d.opened}:
            self.pending_docs.append(item_id)
        elif item_id in {c.id for c in self.view.clues}:
            self.pending.append(item_id)
        else:
            self.say("You can present only a clue you have found or a document you have read.")
            return
        self.say(f"You will show {item_id} with your next question.")

    async def _hint(self) -> None:
        out = await self._run("request_hint", {})
        prefix = "Hint: " if out.hinted else ""
        self.say(f"{prefix}{out.text} {self._budget()}")

    async def _accuse(self, args: list[str]) -> None:
        if not args:
            self.say("Usage: /accuse <suspect_id> <clue_id> <clue_id>...")
            return
        suspect, cited = args[0], args[1:]
        unknown = [c for c in cited if c not in {c.id for c in self.view.clues}]
        if unknown:
            self.say("You can cite only clues you have found: " + ", ".join(unknown))
            return
        out = await self._run("submit_accusation", {"suspect": suspect, "cited": cited})
        if out.code == "not_visible":
            self.say("Choose one of: " + ", ".join(s.id for s in self.case.suspects))
            return
        self.say(out.text or "")
        if out.correct:
            reveal = await self.games.reveal(self.session)
            self.say("Chain clues cited: " + ", ".join(reveal.cited_chain))
            self.say("What really happened:")
            for line in reveal.timeline:
                self.say(f"  {line}")
        self.over = True

    def _status(self) -> None:
        self.say(self._budget())
        self.say("Questioning: " + (self._name(self.suspect) if self.suspect else "nobody"))
        self.say("Clues found:")
        for c in self.view.clues:
            self.say(f"  {c.id:<26} {c.description}")
        if not self.view.clues:
            self.say("  none yet")
        opened = sorted(d.id for d in self.view.documents if d.opened)
        self.say("Documents read: " + (", ".join(opened) or "none"))

    def _announce(self, out: Outcome) -> None:
        for c in out.new_clues:
            self.say(f"New clue: {c.id}: {c.description}")


async def play(
    case: Case, game_id: str, lines: AsyncIterator[str], say: Say = print, *, echo: bool = True
) -> Game:
    engine = make_engine(Settings().database_url)
    try:
        games = GameService(engine, {case.id: case})
        session, view = await games.create(case.id, game_id=game_id)
        game = Game(case, games, session, view, say)
        game.intro()
        async for line in lines:
            if echo:
                say(f"> {line}")
            await game.handle(line)
            if game.over:
                break
        return game
    finally:
        await engine.dispose()


async def _stdin() -> AsyncIterator[str]:
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            return
        yield line.rstrip("\n")


def main(argv: Sequence[str] | None = None) -> int:
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
