import json
import re
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import yaml
from fastapi.testclient import TestClient

from agents.claims import Claim
from app.catalog import CASES, load_cases, publish
from app.config import Settings
from app.db import sync_engine
from app.games import TURNS
from engine.schema import Case
from evals.attack_assert import Exchange, Kind, Transcript, failures
from evals.security_regress import with_documents

EVALS = Path(__file__).parent
CORPUS = EVALS / "attacks" / "corpus.yaml"
GAMEPLAY = EVALS / "gameplay_normal.yaml"
PLACEHOLDER = re.compile(r"\{(game|other|suspect:[a-z0-9_]+)\}")


@dataclass(frozen=True)
class Entry:
    kind: Kind
    spec: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.spec["id"])

    @property
    def label(self) -> str:
        return str(self.spec.get("class", "normal"))


@dataclass(frozen=True)
class Result:
    entry: Entry
    transcript: Transcript
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def load(corpus: Path = CORPUS, gameplay: Path = GAMEPLAY) -> list[Entry]:
    attacks = yaml.safe_load(corpus.read_text())["attacks"]
    normal = yaml.safe_load(gameplay.read_text())["normal"]
    return [Entry("attack", a) for a in attacks] + [Entry("normal", n) for n in normal]


class _Game:
    def __init__(self, client: TestClient, case: Case) -> None:
        self.client = client
        self.case = case
        created = client.post("/games", json={"case_id": case.id})
        created.raise_for_status()
        self.view: dict[str, Any] = created.json()
        self.id: str = self.view["game_id"]

    def handle(self, suspect: str) -> str:
        name = next(s.name for s in self.case.suspects if s.id == suspect)
        return str(next(s["id"] for s in self.view["suspects"] if s["name"] == name))

    def clue_handles(self, clue_ids: Sequence[str]) -> list[str]:
        wanted = {c.description for c in self.case.clues if c.id in clue_ids}
        return [c["id"] for c in self.view["clues"] if c["description"] in wanted]

    def refresh(self) -> None:
        self.view = self.client.get(f"/games/{self.id}").json()


class _Player:
    """Plays one corpus entry the way a browser would, and records every step."""

    def __init__(self, client: TestClient, case: Case) -> None:
        self.case = case
        self.own = _Game(client, case)
        self._other: _Game | None = None
        self.shown: set[str] = set()

    @property
    def other(self) -> _Game:
        if self._other is None:
            self._other = _Game(TestClient(self.own.client.app), self.case)
        return self._other

    def fill(self, text: str) -> str:
        def one(m: re.Match[str]) -> str:
            key = m.group(1)
            if key == "game":
                return self.own.id
            if key == "other":
                return self.other.id
            return self.own.handle(key.split(":", 1)[1])

        return PLACEHOLDER.sub(one, text)

    def step(self, n: int, spec: dict[str, Any]) -> Exchange:
        game = self.other if spec.get("game") == "other" else self.own
        expect = spec.get("expect")
        if "open" in spec:
            return self._open(n, game, spec["open"])
        if "http" in spec:
            return self._http(n, game, spec, expect)
        return self._ask(n, game, spec, expect)

    def _open(self, n: int, game: _Game, doc_id: str) -> Exchange:
        r = game.client.post(
            f"/games/{game.id}/documents/{doc_id}/open",
            json={"state_version": game.view["state_version"]},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        code = None if r.status_code == 200 else r.json().get("code")
        game.refresh()
        return Exchange(n, "open", status=r.status_code, code=code)

    def _http(self, n: int, game: _Game, spec: dict[str, Any], expect: Any) -> Exchange:
        req = spec["http"]
        body = req.get("body")
        if isinstance(body, dict):
            body = json.loads(self.fill(json.dumps(body)))
            body.setdefault("state_version", game.view["state_version"])
        client = TestClient(game.client.app) if spec.get("session") == "none" else game.client
        r = client.request(
            req["method"],
            self.fill(req["path"]),
            json=body,
            headers={"Idempotency-Key": str(req.get("key") or uuid.uuid4().hex)},
        )
        game.refresh()
        text = r.text if r.status_code < 400 else ""
        return Exchange(n, "http", text=text, status=r.status_code, expect=expect)

    def _ask(self, n: int, game: _Game, spec: dict[str, Any], expect: Any) -> Exchange:
        documents = list(spec.get("documents", []))
        if "document" in spec:
            self._open(n, game, spec["document"]["id"])
            documents.append(spec["document"]["id"])
        present = list(spec.get("present", []))
        self.shown |= set(present)
        suspect = spec.get("suspect_handle") or game.handle(spec["suspect"])
        handles = [spec["present_handle"]] if "present_handle" in spec else []
        key = uuid.uuid4().hex
        frame = {
            "idempotency_key": key,
            "state_version": game.view["state_version"],
            "suspect": suspect,
            "question": spec["ask"],
            "present": handles or game.clue_handles(present),
            "documents": documents,
        }
        chunks: list[str] = []
        with game.client.websocket_connect(f"/games/{game.id}/ask") as ws:
            ws.send_json(frame)
            while (event := ws.receive_json())["type"] != "done":
                if event["type"] == "chunk":
                    chunks.append(event["text"])
        game.refresh()
        verdict = _verdict(game.id, key)
        return Exchange(
            n,
            "ask",
            text="".join(chunks),
            speaker=spec.get("suspect") or spec.get("suspect_handle"),
            code=event.get("code"),
            claims=tuple(Claim.model_validate(c) for c in verdict.get("claims", [])),
            fell_back=bool(verdict.get("fell_back")),
            shown=frozenset(self.shown),
            expect=expect,
            absent=spec.get("absent"),
        )

    @property
    def game_ids(self) -> tuple[str, ...]:
        return (self.own.id, *((self._other.id,) if self._other else ()))


def _verdict(game_id: str, key: str) -> dict[str, Any]:
    with sync_engine(Settings().database_url).connect() as conn:
        found = conn.scalar(
            sa.select(TURNS.c.verdict).where(
                TURNS.c.game_id == game_id, TURNS.c.idempotency_key == key
            )
        )
    return dict(found or {})


def _variant(case: Case, entry: Entry) -> Case | None:
    steps = [s for s in entry.spec["steps"] if "document" in s]
    if not steps:
        return None
    played = with_documents(case, {"turns": steps})
    return played.model_copy(update={"id": f"{case.id}_eval_{entry.id}"[:40].rstrip("_")})


@contextmanager
def _published(case: Case | None) -> Iterator[None]:
    if case is None:
        yield
        return
    engine = sync_engine(Settings().database_url)
    with engine.begin() as conn:
        publish(conn, case)
    try:
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(sa.delete(CASES).where(CASES.c.id == case.id))


def play(client: TestClient, entry: Entry) -> Result:
    base = load_cases()[entry.spec["case"]]
    variant = _variant(base, entry)
    case = variant or base
    with _published(variant):
        player = _Player(client, case)
        exchanges = tuple(player.step(n, s) for n, s in enumerate(entry.spec["steps"], start=1))
    transcript = Transcript(
        entry.id,
        entry.kind,
        case,
        exchanges,
        expect_answer=bool(entry.spec.get("expect_answer")),
        game_ids=player.game_ids,
    )
    return Result(entry, transcript, tuple(failures(transcript)))
