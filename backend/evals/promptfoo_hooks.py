"""promptfoo hooks for the P5-2 corpus: one test per entry, a provider that plays the entry
through the HTTP and WebSocket API in-process, and an assertion over its transcript."""

import json
import os
from typing import Any

from fastapi.testclient import TestClient

from app.llm import tagged
from app.main import create_app
from evals.corpus import load, play
from evals.runs import spent

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


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    run_id = os.environ.get(RUN_ID, "promptfoo")
    max_usd = float(os.environ.get("EVAL_MAX_USD", "0"))
    if spent(run_id) > max_usd:
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
