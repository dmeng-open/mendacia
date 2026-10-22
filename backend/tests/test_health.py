import os

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings_for(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL=database_url,
        MODEL_FAST="fast",
        MODEL_STRONG="strong",
        MODEL_EMBED="embed",
        EMBED_DIM=8,
        EVAL_MAX_USD=1.0,
    )


def test_healthz_ok_with_live_database() -> None:
    with TestClient(create_app(settings_for(os.environ["DATABASE_URL"]))) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_healthz_503_with_bad_database_url() -> None:
    bad = "postgresql+psycopg://nobody:nopass@127.0.0.1:1/nodb"
    with TestClient(create_app(settings_for(bad))) as client:
        response = client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["db"]
