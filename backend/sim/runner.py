import argparse
import sys
import threading
import uuid
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from fastapi.testclient import TestClient

from agents.events import VERIFIER_EVENTS
from app import llm
from app.config import Settings
from app.db import sync_engine
from app.llm import LLM_CALLS, Tags
from app.llm_replay import MissingRecording
from app.main import create_app
from engine.schema import Case
from sim.detective_bot import DetectiveBot, Played

CASES = Path(__file__).resolve().parents[2] / "cases"
HAND_WRITTEN = ("manor", "gallery", "lighthouse")


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """A run's spend. It admits a model call only while the run has room for it, so a run ends
    at most one call past its cap, however many games run at once."""

    def __init__(self, run_id: str, max_usd: float) -> None:
        self.run_id = run_id
        self.max_usd = max_usd
        self.spent = 0.0
        self.exceeded = False
        self._games: set[str] = set()
        self._in_flight = 0
        self._largest = 0.0
        self._lock = threading.Condition()

    def add_game(self, game_id: str) -> None:
        with self._lock:
            self._games.add(game_id)

    def _mine(self, tags: Tags) -> bool:
        return tags.run_id == self.run_id or tags.game_id in self._games

    def before(self, tags: Tags) -> None:
        with self._lock:
            if not self._mine(tags):
                return
            while True:
                if self.spent > self.max_usd:
                    self.exceeded = True
                    raise BudgetExceeded(f"run {self.run_id} passed ${self.max_usd:.2f}")
                known = self._largest > 0
                room = self.spent + (self._in_flight + 1) * self._largest <= self.max_usd
                if self._in_flight == 0 or (known and room):
                    self._in_flight += 1
                    return
                self._lock.wait()

    def after(self, tags: Tags, cost_usd: float) -> None:
        with self._lock:
            if not self._mine(tags):
                return
            self._in_flight -= 1
            self.spent += cost_usd
            self._largest = max(self._largest, cost_usd)
            self.exceeded |= self.spent > self.max_usd
            self._lock.notify_all()


@contextmanager
def metered(budget: Budget) -> Iterator[None]:
    llm.METERS.append(budget)
    try:
        yield
    finally:
        llm.METERS.remove(budget)


@dataclass(frozen=True)
class GameResult:
    n: int
    case_id: str
    game_id: str | None
    accused: str | None
    solved: bool
    questions_used: int
    blocks: int
    cost_usd: float
    stopped: str | None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    games: tuple[GameResult, ...]
    cost_usd: float
    max_usd: float
    status: Literal["finished", "budget_exceeded"]


Player = Callable[[TestClient, str, Budget], Played]


def detective(client: TestClient, case_id: str, budget: Budget) -> Played:
    bot = DetectiveBot(
        client,
        case_id,
        run_id=budget.run_id,
        on_start=budget.add_game,
        stop=lambda: budget.exceeded,
    )
    return bot.play()


def culprit_name(case_id: str) -> str:
    case = Case.model_validate_json((CASES / f"{case_id}.json").read_text())
    return next(s.name for s in case.suspects if s.id == case.culprit)


def _game_totals(game_id: str) -> tuple[int, float]:
    with sync_engine(Settings().database_url).connect() as conn:
        blocks = conn.execute(
            sa.select(sa.func.count())
            .select_from(VERIFIER_EVENTS)
            .where(VERIFIER_EVENTS.c.game_id == game_id)
        ).scalar_one()
        cost = conn.execute(
            sa.select(sa.func.coalesce(sa.func.sum(LLM_CALLS.c.cost_usd), 0.0)).where(
                LLM_CALLS.c.game_id == game_id
            )
        ).scalar_one()
    return int(blocks), float(cost)


def _score(n: int, case_id: str, played: Played | None, stopped: str | None) -> GameResult:
    if played is None:
        return GameResult(n, case_id, None, None, False, 0, 0, 0.0, stopped)
    blocks, cost = _game_totals(played.game_id)
    solved = played.accused is not None and played.accused == culprit_name(case_id)
    return GameResult(
        n,
        case_id,
        played.game_id,
        played.accused,
        solved,
        played.questions_used,
        blocks,
        cost,
        played.stopped or stopped,
    )


def run_games(
    n: int,
    concurrency: int,
    max_usd: float,
    *,
    cases: Sequence[str] = HAND_WRITTEN,
    client: TestClient | None = None,
    player: Player = detective,
) -> RunResult:
    budget = Budget(uuid.uuid4().hex[:12], max_usd)

    def one(i: int, c: TestClient) -> GameResult:
        case_id = cases[i % len(cases)]
        if budget.exceeded:
            return _score(i + 1, case_id, None, "budget_exceeded")
        try:
            return _score(i + 1, case_id, player(c, case_id, budget), None)
        except BudgetExceeded:
            return _score(i + 1, case_id, None, "budget_exceeded")
        except MissingRecording:
            return _score(i + 1, case_id, None, "unrecorded")

    def run_all(c: TestClient) -> list[GameResult]:
        with metered(budget), ThreadPoolExecutor(max_workers=concurrency) as pool:
            return list(pool.map(lambda i: one(i, c), range(n)))

    if client is None:
        with TestClient(create_app()) as own:
            games = run_all(own)
    else:
        games = run_all(client)
    status: Literal["finished", "budget_exceeded"] = (
        "budget_exceeded" if budget.exceeded else "finished"
    )
    return RunResult(budget.run_id, tuple(games), budget.spent, max_usd, status)


def render(result: RunResult) -> list[str]:
    lines = [
        f"game {g.n} {g.case_id:<12} "
        f"{'solved' if g.solved else 'unsolved':<9}"
        f"accused={g.accused or '-'} questions={g.questions_used} blocks={g.blocks} "
        f"cost=${g.cost_usd:.4f}{f' stopped={g.stopped}' if g.stopped else ''}"
        for g in result.games
    ]
    solved = sum(g.solved for g in result.games)
    lines.append(
        f"run {result.run_id}: {result.status}, {solved}/{len(result.games)} solved, "
        f"total ${result.cost_usd:.4f} of ${result.max_usd:g}"
    )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sim.runner")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-usd", type=float, default=None)
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args(argv)
    max_usd = Settings().eval_max_usd if args.max_usd is None else args.max_usd
    result = run_games(args.n, args.concurrency, max_usd, cases=args.case or HAND_WRITTEN)
    print("\n".join(render(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
