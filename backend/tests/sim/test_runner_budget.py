import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.llm import ModelRole, complete, tagged
from sim.detective_bot import Played
from sim.runner import Budget, Player, run_games

COST = 0.01


@pytest.fixture(autouse=True)
def fixed_cost_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(**_: Any) -> SimpleNamespace:
        time.sleep(0.05)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setattr("app.llm._explicit_key_kwargs", lambda *_: {})
    monkeypatch.setattr("litellm.completion", fake)
    monkeypatch.setattr("litellm.completion_cost", lambda _: COST)


def spender(calls: int) -> Player:
    def play(client: TestClient, case_id: str, budget: Budget) -> Played:
        played = Played(uuid4().hex)
        budget.add_game(played.game_id)
        with tagged(run_id=budget.run_id, game_id=played.game_id):
            for _ in range(calls):
                if budget.exceeded:
                    played.stopped = "budget_exceeded"
                    break
                complete(ModelRole.STRONG, [{"role": "user", "content": "x"}], purpose="detective")
                played.steps += 1
        return played

    return play


def test_a_run_under_its_cap_finishes() -> None:
    result = run_games(2, 2, 1.0, player=spender(3))

    assert result.status == "finished"
    assert result.cost_usd == pytest.approx(6 * COST)


def test_a_run_stops_once_its_spend_passes_the_cap() -> None:
    result = run_games(3, 1, 0.035, player=spender(10))

    assert result.status == "budget_exceeded"
    assert result.cost_usd == pytest.approx(4 * COST)
    assert [g.stopped for g in result.games] == ["budget_exceeded"] * 3
    assert [g.game_id is None for g in result.games] == [False, True, True]


@pytest.mark.parametrize("concurrency", [2, 4])
def test_concurrent_games_pass_the_cap_by_at_most_one_call(concurrency: int) -> None:
    result = run_games(6, concurrency, 0.035, player=spender(10))

    assert result.status == "budget_exceeded"
    assert result.cost_usd <= 0.035 + COST


def test_a_tiny_cap_stops_after_the_first_call() -> None:
    result = run_games(2, 2, 0.001, player=spender(10))

    assert result.status == "budget_exceeded"
    assert result.cost_usd == pytest.approx(COST)
