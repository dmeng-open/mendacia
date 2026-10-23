import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app import llm_replay
from app.llm import MissingApiKey, ModelRole, complete, embed
from app.llm_replay import MissingRecording, request_key

READY = [{"role": "user", "content": "Reply with the single word: ready"}]


def rows(purpose: str) -> list[Any]:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        return list(
            conn.execute(
                sa.text(
                    "select model, role, prompt_tokens, completion_tokens, cost_usd, mode "
                    "from llm_calls where purpose = :p"
                ),
                {"p": purpose},
            )
        )


def fake_completion(text: str) -> Any:
    def fake(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    return fake


def fail(**_: Any) -> Any:
    raise AssertionError("network call in replay mode")


@pytest.fixture
def anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENDACIA_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_FAST", "anthropic/test-model")


def test_replay_hit_writes_one_row() -> None:
    purpose = uuid4().hex
    result = complete(ModelRole.FAST, READY, purpose=purpose, max_tokens=5)
    recorded = llm_replay.load(
        request_key("fast", {"messages": READY, "max_tokens": 5, "response_format": None})
    )
    assert result.text == recorded.output
    [row] = rows(purpose)
    assert (row.role, row.mode, row.model) == ("fast", "replay", recorded.model)
    assert (row.prompt_tokens, row.completion_tokens) == (
        recorded.prompt_tokens,
        recorded.completion_tokens,
    )
    assert row.cost_usd == recorded.cost_usd


def test_replay_miss_names_the_key() -> None:
    messages = [{"role": "user", "content": uuid4().hex}]
    key = request_key("fast", {"messages": messages, "max_tokens": None, "response_format": None})
    with pytest.raises(MissingRecording, match=key):
        complete(ModelRole.FAST, messages, purpose=uuid4().hex)


def test_record_then_replay_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, anthropic_key: None
) -> None:
    monkeypatch.setattr(llm_replay, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr("litellm.completion", fake_completion("pong"))
    monkeypatch.setattr("litellm.completion_cost", lambda _: 0.0)
    monkeypatch.setenv("LLM_MODE", "record")
    messages = [{"role": "user", "content": uuid4().hex}]
    recorded_purpose = uuid4().hex
    first = complete(ModelRole.FAST, messages, purpose=recorded_purpose)

    monkeypatch.setattr("litellm.completion", fail)
    monkeypatch.setenv("LLM_MODE", "replay")
    replay_purpose = uuid4().hex
    second = complete(ModelRole.FAST, messages, purpose=replay_purpose)

    assert first.text == second.text == "pong"
    assert (second.prompt_tokens, second.completion_tokens, second.cost_usd) == (7, 3, 0.0)
    assert [r.mode for r in rows(recorded_purpose)] == ["record"]
    assert [r.mode for r in rows(replay_purpose)] == ["replay"]


def test_record_then_replay_embed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm_replay, "FIXTURES_DIR", tmp_path)

    def fake_embedding(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            data=[{"embedding": [0.5, 1.5]}],
            usage=SimpleNamespace(prompt_tokens=4),
        )

    monkeypatch.setattr("litellm.embedding", fake_embedding)
    monkeypatch.setattr("litellm.completion_cost", lambda _: 0.0)
    monkeypatch.setenv("LLM_MODE", "record")
    texts = [uuid4().hex]
    first = embed(texts, purpose=uuid4().hex)

    monkeypatch.setattr("litellm.embedding", fail)
    monkeypatch.setenv("LLM_MODE", "replay")
    purpose = uuid4().hex
    second = embed(texts, purpose=purpose)

    assert first.vectors == second.vectors == [[0.5, 1.5]]
    assert [(r.role, r.mode, r.prompt_tokens) for r in rows(purpose)] == [("embed", "replay", 4)]


def test_replay_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MENDACIA_ANTHROPIC_API_KEY", raising=False)
    assert complete(ModelRole.FAST, READY, purpose=uuid4().hex, max_tokens=5).text


@pytest.mark.parametrize("mode", ["live", "record"])
def test_live_and_record_without_key_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    monkeypatch.setattr(llm_replay, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr("litellm.completion", fail)
    monkeypatch.setenv("MODEL_FAST", "anthropic/test-model")
    monkeypatch.delenv("MENDACIA_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", mode)
    with pytest.raises(MissingApiKey, match="MENDACIA_ANTHROPIC_API_KEY is not set"):
        complete(ModelRole.FAST, READY, purpose=uuid4().hex)


def test_openai_embed_without_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm_replay, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr("litellm.embedding", fail)
    monkeypatch.setenv("MODEL_EMBED", "openai/test-embed")
    monkeypatch.delenv("MENDACIA_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODE", "live")
    with pytest.raises(MissingApiKey, match="MENDACIA_OPENAI_API_KEY is not set"):
        embed([uuid4().hex], purpose=uuid4().hex)


def test_openai_embed_passes_its_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def fake_embedding(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(data=[{"embedding": [1.0]}], usage=SimpleNamespace(prompt_tokens=1))

    monkeypatch.setattr(llm_replay, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr("litellm.embedding", fake_embedding)
    monkeypatch.setattr("litellm.completion_cost", lambda _: 0.0)
    monkeypatch.setenv("MODEL_EMBED", "openai/test-embed")
    monkeypatch.setenv("MENDACIA_OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("LLM_MODE", "live")
    embed([uuid4().hex], purpose=uuid4().hex)
    assert seen["api_key"] == "openai-test-key"
