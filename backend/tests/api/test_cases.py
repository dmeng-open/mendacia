import os

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.catalog import publish
from tests.api.conftest import Player
from tests.engine.generator_scenarios import manor


def test_cases_lists_titles_and_summaries_and_a_published_case_is_playable(
    client: TestClient,
) -> None:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sa.text("delete from cases where id = 'manor_published'"))
        publish(conn, manor("manor_published"))

    listed = client.get("/cases").json()

    assert [c["id"] for c in listed][:3] == ["gallery", "lighthouse", "manor"]
    assert "manor_published" in [c["id"] for c in listed]
    assert set(listed[0]) == {"id", "title", "summary"}
    game = Player(client, "manor_published")
    assert game.view["title"] == "Death at Ashcombe Manor"
