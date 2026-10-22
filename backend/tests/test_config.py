import pytest
from pydantic import ValidationError

from app.config import Settings

FULL_ENV = {
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
    "MODEL_FAST": "fast",
    "MODEL_STRONG": "strong",
    "MODEL_EMBED": "embed",
    "EMBED_DIM": "8",
    "EVAL_MAX_USD": "1.5",
}


def load(monkeypatch: pytest.MonkeyPatch, missing: str | None = None) -> Settings:
    for name, value in FULL_ENV.items():
        if name == missing:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_loads_every_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load(monkeypatch)
    assert settings.fast_model == "fast"
    assert settings.embed_dim == 8
    assert settings.eval_max_usd == 1.5


@pytest.mark.parametrize("name", list(FULL_ENV))
def test_missing_variable_fails_with_its_name(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    with pytest.raises(ValidationError, match=name):
        load(monkeypatch, missing=name)
