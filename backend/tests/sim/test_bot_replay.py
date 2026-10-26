from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import sync_engine
from app.main import create_app
from engine.schema import Case
from evidence import index_case
from sim.runner import run_games

MANOR = Case.model_validate_json(
    (Path(__file__).resolve().parents[3] / "cases" / "manor.json").read_text()
)


def test_a_replayed_bot_game_ends_in_an_accusation() -> None:
    index_case(MANOR)
    with TestClient(create_app()) as client:
        result = run_games(1, 1, 1.0, cases=["manor"], client=client)

    (game,) = result.games
    assert result.status == "finished"
    assert (game.accused, game.solved) == ("Clara Ashcombe", True)
    assert game.questions_used > 0
    assert game.cost_usd == pytest.approx(result.cost_usd)
    assert result.cost_usd > 0

    with sync_engine(Settings().database_url).connect() as conn:
        rows = conn.execute(
            sa.text("select purpose, run_id, mode from llm_calls where game_id = :g"),
            {"g": game.game_id},
        ).all()
    assert {r.mode for r in rows} == {"replay"}
    assert {r.run_id for r in rows if r.purpose == "detective"} == {result.run_id}
    assert {"detective", "suspect", "extract"} <= {r.purpose for r in rows}
