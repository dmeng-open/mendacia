import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel

from app import llm_replay
from app.config import Settings
from app.db import sync_engine
from app.llm_replay import LlmMode, Recording

METADATA = sa.MetaData()
LLM_CALLS = sa.Table(
    "llm_calls",
    METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("model", sa.Text),
    sa.Column("role", sa.Text),
    sa.Column("purpose", sa.Text),
    sa.Column("game_id", sa.Text),
    sa.Column("prompt_tokens", sa.Integer),
    sa.Column("completion_tokens", sa.Integer),
    sa.Column("cost_usd", sa.Double),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("mode", sa.Text),
    sa.Column("prompt_version", sa.Text),
    sa.Column("run_id", sa.Text),
)


class ModelRole(StrEnum):
    FAST = "fast"
    STRONG = "strong"
    EMBED = "embed"


class MissingApiKey(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int


@dataclass(frozen=True)
class Embedding:
    vectors: list[list[float]]
    model: str
    prompt_tokens: int
    cost_usd: float
    latency_ms: int


MODELS: dict[ModelRole, Callable[[Settings], str]] = {
    ModelRole.FAST: lambda s: s.fast_model,
    ModelRole.STRONG: lambda s: s.strong_model,
    ModelRole.EMBED: lambda s: s.embed_model,
}

EXPLICIT_KEY_PROVIDERS: dict[str, tuple[str, Callable[[Settings], Any]]] = {
    "anthropic": ("MENDACIA_ANTHROPIC_API_KEY", lambda s: s.anthropic_api_key),
    "openai": ("MENDACIA_OPENAI_API_KEY", lambda s: s.openai_api_key),
}


def _explicit_key_kwargs(settings: Settings, model: str) -> dict[str, Any]:
    import litellm

    _, provider, _, _ = litellm.get_llm_provider(model)
    if provider not in EXPLICIT_KEY_PROVIDERS:
        return {}
    env_name, read = EXPLICIT_KEY_PROVIDERS[provider]
    secret = read(settings)
    if secret is None:
        raise MissingApiKey(f"{env_name} is not set")
    return {"api_key": secret.get_secret_value()}


def _run(
    settings: Settings,
    role: ModelRole,
    request: Mapping[str, Any],
    purpose: str,
    game_id: str | None,
    live_call: Callable[[str, dict[str, Any]], tuple[Any, float]],
    to_output: Callable[[Any], str | list[list[float]]],
    prompt_version: str | None = None,
    run_id: str | None = None,
) -> Recording:
    key = llm_replay.request_key(role, request)
    mode = settings.llm_mode
    if mode is LlmMode.RECORD and llm_replay.exists(key):
        mode = LlmMode.REPLAY
    if mode is LlmMode.REPLAY:
        recording = llm_replay.load(key)
    else:
        model = MODELS[role](settings)
        kwargs = _explicit_key_kwargs(settings, model)
        started = time.monotonic()
        response, cost = live_call(model, kwargs)
        latency_ms = round((time.monotonic() - started) * 1000)
        recording = Recording(
            key=key,
            model=model,
            request=dict(request),
            output=to_output(response),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=getattr(response.usage, "completion_tokens", None) or 0,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
        if mode is LlmMode.RECORD:
            llm_replay.save(recording)
    with sync_engine(settings.database_url).begin() as conn:
        conn.execute(
            sa.insert(LLM_CALLS).values(
                model=recording.model,
                role=role.value,
                purpose=purpose,
                game_id=game_id,
                prompt_tokens=recording.prompt_tokens,
                completion_tokens=recording.completion_tokens,
                cost_usd=recording.cost_usd,
                latency_ms=recording.latency_ms,
                mode=mode.value,
                prompt_version=prompt_version,
                run_id=run_id,
            )
        )
    return recording


def complete(
    role: ModelRole,
    messages: list[dict[str, Any]],
    *,
    response_format: type[BaseModel] | None = None,
    purpose: str,
    game_id: str | None = None,
    max_tokens: int | None = None,
    prompt_version: str | None = None,
    run_id: str | None = None,
    timeout: float | None = None,
) -> Completion:
    request = {
        "messages": messages,
        "max_tokens": max_tokens,
        "response_format": response_format.model_json_schema() if response_format else None,
    }

    def live_call(model: str, kwargs: dict[str, Any]) -> tuple[Any, float]:
        import litellm

        response = litellm.completion(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout,
            **kwargs,
        )
        return response, litellm.completion_cost(response)

    def to_output(response: Any) -> str:
        return str(response.choices[0].message.content or "")

    recording = _run(
        Settings(), role, request, purpose, game_id, live_call, to_output, prompt_version, run_id
    )
    assert isinstance(recording.output, str)
    return Completion(
        text=recording.output,
        model=recording.model,
        prompt_tokens=recording.prompt_tokens,
        completion_tokens=recording.completion_tokens,
        cost_usd=recording.cost_usd,
        latency_ms=recording.latency_ms,
    )


def embed(texts: list[str], *, purpose: str, run_id: str | None = None) -> Embedding:
    request = {"input": texts}

    def live_call(model: str, kwargs: dict[str, Any]) -> tuple[Any, float]:
        import litellm

        response = litellm.embedding(model=model, input=texts, **kwargs)
        return response, litellm.completion_cost(response)

    def to_output(response: Any) -> list[list[float]]:
        return [list(item["embedding"]) for item in response.data]

    recording = _run(
        Settings(), ModelRole.EMBED, request, purpose, None, live_call, to_output, run_id=run_id
    )
    assert not isinstance(recording.output, str)
    return Embedding(
        vectors=recording.output,
        model=recording.model,
        prompt_tokens=recording.prompt_tokens,
        cost_usd=recording.cost_usd,
        latency_ms=recording.latency_ms,
    )
