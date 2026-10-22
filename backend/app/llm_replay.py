import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "llm"


class LlmMode(StrEnum):
    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"


class Recording(BaseModel):
    key: str
    model: str
    request: dict[str, Any]
    output: str | list[list[float]]
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int


class MissingRecording(LookupError):
    pass


def request_key(role: str, request: Mapping[str, Any]) -> str:
    payload = json.dumps({"role": role, "request": request}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _path(key: str) -> Path:
    return FIXTURES_DIR / f"{key}.json"


def load(key: str) -> Recording:
    path = _path(key)
    if not path.exists():
        raise MissingRecording(f"no recording for key {key} at {path}; run with LLM_MODE=record")
    return Recording.model_validate_json(path.read_text())


def save(recording: Recording) -> Path:
    path = _path(recording.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(recording.model_dump_json(indent=2) + "\n")
    return path
