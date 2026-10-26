"""promptfoo hooks for the P5-2 corpus: one test per entry, a provider that plays the entry
through the HTTP and WebSocket API in-process, and an assertion over its transcript."""

import json
import os
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import sync_engine
from app.llm import LLM_CALLS, tagged
from app.main import create_app
from evals.corpus import load, play

RUN_ID = "EVAL_RUN_ID"


def generate_tests() -> list[dict[str, Any]]:
    return [
        {
            "description": f"{e.kind} {e.label} {e.id}",
            "vars": {"entry": e.id},
            "metadata": {
                "kind": e.kind,
                "class": e.label,
                "owasp": e.spec.get("owasp"),
                "chained": bool(e.spec.get("chained")),
            },
        }
        for e in load()
    ]


def _spent(run_id: str) -> float:
    with sync_engine(Settings().database_url).connect() as conn:
        total = conn.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(LLM_CALLS.c.cost_usd), 0.0)).where(
                LLM_CALLS.c.run_id == run_id, LLM_CALLS.c.mode != "replay"
            )
        )
    return float(total or 0.0)


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    run_id = os.environ.get(RUN_ID, "promptfoo")
    max_usd = float(os.environ.get("EVAL_MAX_USD", "0"))
    if _spent(run_id) > max_usd:
        return {"error": f"budget_exceeded: run {run_id} passed ${max_usd:g}"}
    entry = next(e for e in load() if e.id == prompt.strip())
    with TestClient(create_app()) as client, tagged(run_id=run_id):
        result = play(client, entry)
    output = {
        "entry": entry.id,
        "kind": entry.kind,
        "class": entry.label,
        "owasp": entry.spec.get("owasp"),
        "problems": list(result.problems),
        "games": list(result.transcript.game_ids),
    }
    return {"output": json.dumps(output)}


def get_assert(output: str, context: dict[str, Any]) -> dict[str, Any]:
    problems = json.loads(output)["problems"]
    return {"pass": not problems, "score": 0.0 if problems else 1.0, "reason": "; ".join(problems)}
