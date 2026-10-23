import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from engine.schema import Case
from evidence import index_case
from security.context import canary

ROOT = Path(__file__).resolve().parents[3]
MANOR = Case.model_validate_json((ROOT / "cases" / "manor.json").read_text())


@pytest.fixture
def client() -> Iterator[TestClient]:
    index_case(MANOR)
    with TestClient(create_app()) as c:
        yield c


class Player:
    def __init__(self, client: TestClient, case_id: str = "manor") -> None:
        self.client = client
        self.bodies: list[str] = []
        created = client.post("/games", json={"case_id": case_id})
        assert created.status_code == 201, created.text
        self.view: dict[str, Any] = created.json()
        self.id: str = self.view["game_id"]
        self.bodies.append(created.text)

    @property
    def version(self) -> int:
        return int(self.view["state_version"])

    def suspect(self, name: str) -> str:
        return str(next(s["id"] for s in self.view["suspects"] if s["name"] == name))

    def get(self, path: str, **kw: Any) -> Any:
        r = self.client.get(f"/games/{self.id}{path}", **kw)
        self.bodies.append(r.text)
        return r

    def post(self, path: str, body: dict[str, Any], key: str | None = None, **kw: Any) -> Any:
        headers = {"Idempotency-Key": key or uuid.uuid4().hex, **kw.pop("headers", {})}
        r = self.client.post(f"/games/{self.id}{path}", json=body, headers=headers, **kw)
        self.bodies.append(r.text)
        if r.status_code == 200:
            self.view = r.json()["view"]
        return r

    def refresh(self) -> dict[str, Any]:
        self.view = self.get("").json()
        return self.view

    def ask(
        self, suspect: str, question: str, key: str | None = None, **frame: Any
    ) -> list[dict[str, Any]]:
        message = {
            "idempotency_key": key or uuid.uuid4().hex,
            "state_version": self.version,
            "suspect": suspect,
            "question": question,
            **frame,
        }
        with self.client.websocket_connect(f"/games/{self.id}/ask") as ws:
            ws.send_json(message)
            events: list[dict[str, Any]] = []
            while not events or events[-1]["type"] != "done":
                events.append(ws.receive_json())
        self.bodies += [json.dumps(e) for e in events]
        self.refresh()
        return events


def tokens(case: Case) -> set[str]:
    secret = {f for facts in case.secrets.values() for f in facts}
    return {case.culprit, *case.solution_chain, *secret, canary(case)}


def leaked(case: Case, bodies: list[str]) -> list[tuple[str, str]]:
    found = []
    for t in tokens(case):
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])")
        found += [(t, b[:120]) for b in bodies if pattern.search(b)]
    return found
