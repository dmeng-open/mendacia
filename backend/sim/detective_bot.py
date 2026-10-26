import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from agents.prompts import load
from app.llm import ModelRole, complete, tagged

PROMPT = load("detective")
MAX_STEPS = 40
LOG_LINES = 12
HITS = 5
DOC_CHARS = 700
REPLY_CHARS = 400
MUST_ACCUSE = "You must accuse now. Choose the action accuse."


class Move(BaseModel):
    action: Literal["search", "open", "ask", "hint", "accuse"]
    query: str = ""
    document: str = ""
    suspect: str = ""
    question: str = ""
    present: list[int] = []
    cited: list[int] = []
    reason: str = ""


Ruling = Literal["correct", "wrong"]


@dataclass
class Played:
    game_id: str
    accused: str | None = None
    ruling: Ruling | None = None
    questions_used: int = 0
    steps: int = 0
    stopped: str | None = None


@dataclass
class _Seen:
    view: dict[str, Any]
    log: list[str] = field(default_factory=list)
    hits: list[dict[str, str]] = field(default_factory=list)
    document: dict[str, str] | None = None


class DetectiveBot:
    """Plays one game through the public HTTP and WebSocket API, as a browser would."""

    def __init__(
        self,
        client: TestClient,
        case_id: str,
        *,
        run_id: str | None = None,
        on_start: Callable[[str], None] = lambda _: None,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._client = client
        self._case_id = case_id
        self._run_id = run_id
        self._on_start = on_start
        self._stop = stop

    def play(self) -> Played:
        created = self._client.post("/games", json={"case_id": self._case_id})
        created.raise_for_status()
        seen = _Seen(created.json())
        game_id = seen.view["game_id"]
        self._on_start(game_id)
        played = Played(game_id)
        budget = seen.view["questions_left"]
        with tagged(run_id=self._run_id, game_id=game_id):
            while played.steps < MAX_STEPS and played.ruling is None:
                if self._stop():
                    played.stopped = "budget_exceeded"
                    break
                left = seen.view["questions_left"] + seen.view["hints_left"]
                must = left == 0 or played.steps == MAX_STEPS - 1
                self._act(seen, played, self._decide(seen, must), must)
                played.steps += 1
        played.questions_used = budget - seen.view["questions_left"]
        return played

    def _decide(self, seen: _Seen, must_accuse: bool) -> Move | None:
        state = {
            "case": {
                "title": seen.view["title"],
                "summary": seen.view["summary"],
                "hours": seen.view["time_slots"],
            },
            "suspects": [
                {"name": s["name"], "description": s["description"]} for s in seen.view["suspects"]
            ],
            "clues": [
                {"n": n, "text": c["description"]}
                for n, c in enumerate(seen.view["clues"], start=1)
            ],
            "documents": [
                {"id": d["id"], "title": d["title"], "opened": d["opened"]}
                for d in seen.view["documents"]
            ],
            "questions_left": seen.view["questions_left"],
            "hints_left": seen.view["hints_left"],
            "last_search": seen.hits,
            "last_document": seen.document,
            "log": seen.log[-LOG_LINES:],
        }
        user = PROMPT.render(
            "turn",
            state=json.dumps(state, ensure_ascii=False),
            must_accuse=MUST_ACCUSE if must_accuse else "",
        )
        reply = complete(
            ModelRole.STRONG,
            [
                {"role": "system", "content": PROMPT.render("intro")},
                {"role": "user", "content": user},
            ],
            purpose="detective",
            max_tokens=400,
            prompt_version=PROMPT.version,
        )
        text = reply.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        try:
            return Move.model_validate_json(text)
        except ValidationError:
            seen.log.append("your last reply was not a valid move")
            return None

    def _act(self, seen: _Seen, played: Played, move: Move | None, must_accuse: bool) -> None:
        if move is None or (must_accuse and move.action != "accuse"):
            if must_accuse:
                self._accuse(seen, played, move or Move(action="accuse"))
            return
        match move.action:
            case "search":
                self._search(seen, move.query)
            case "open":
                self._open(seen, move.document)
            case "ask":
                self._ask(seen, move)
            case "hint":
                self._hint(seen)
            case "accuse":
                self._accuse(seen, played, move)

    def _path(self, seen: _Seen, rest: str = "") -> str:
        return f"/games/{seen.view['game_id']}{rest}"

    def _post(self, seen: _Seen, rest: str, body: dict[str, Any]) -> dict[str, Any] | None:
        body = {"state_version": seen.view["state_version"], **body}
        r = self._client.post(
            self._path(seen, rest), json=body, headers={"Idempotency-Key": uuid.uuid4().hex}
        )
        if r.status_code != 200:
            seen.log.append(f"{rest.strip('/')} refused: {r.json().get('code', r.status_code)}")
            return None
        out: dict[str, Any] = r.json()
        seen.view = out["view"]
        return out

    def _search(self, seen: _Seen, query: str) -> None:
        r = self._client.get(self._path(seen, "/search"), params={"q": query})
        if r.status_code != 200:
            seen.log.append(f"search {query!r} refused: {r.json().get('code', r.status_code)}")
            return
        seen.hits = [
            {"id": h["document_id"], "title": h["title"], "highlight": h["highlight"]}
            for h in r.json()[:HITS]
        ]
        seen.log.append(f"searched {query!r}: {len(seen.hits)} documents")

    def _open(self, seen: _Seen, doc_id: str) -> None:
        out = self._post(seen, f"/documents/{doc_id}/open", {})
        if out is None or out.get("document") is None:
            return
        doc = out["document"]
        seen.document = {"id": doc["id"], "title": doc["title"], "text": doc["body"][:DOC_CHARS]}
        seen.log.append(f"opened {doc['title']}{_new(out['new_clues'])}")

    def _hint(self, seen: _Seen) -> None:
        out = self._post(seen, "/hint", {})
        if out is not None:
            seen.log.append(f"hint: {out.get('text') or ''}{_new(out['new_clues'])}")

    def _ask(self, seen: _Seen, move: Move) -> None:
        suspect = _by_name(seen.view["suspects"], move.suspect)
        if suspect is None:
            seen.log.append(f"no suspect named {move.suspect!r}")
            return
        frame = {
            "idempotency_key": uuid.uuid4().hex,
            "state_version": seen.view["state_version"],
            "suspect": suspect["id"],
            "question": move.question[:500],
            "present": _clue_ids(seen.view["clues"], move.present),
        }
        reply: list[str] = []
        with self._client.websocket_connect(self._path(seen, "/ask")) as ws:
            ws.send_json(frame)
            while (event := ws.receive_json())["type"] != "done":
                if event["type"] == "chunk":
                    reply.append(event["text"])
        said = "".join(reply)[:REPLY_CHARS]
        refused = f" (refused: {event['code']})" if event.get("code") else ""
        seen.view = self._client.get(self._path(seen)).json()
        seen.log.append(
            f"asked {suspect['name']}: {move.question!r}; reply: {said!r}{refused}"
            f"{_new(event.get('new_clues', []))}"
        )

    def _accuse(self, seen: _Seen, played: Played, move: Move) -> None:
        suspect = _by_name(seen.view["suspects"], move.suspect) or seen.view["suspects"][0]
        cited = _clue_ids(seen.view["clues"], move.cited) or [c["id"] for c in seen.view["clues"]]
        out = self._post(seen, "/accuse", {"suspect": suspect["id"], "cited": cited})
        if out is None:
            return
        played.accused = suspect["name"]
        played.ruling = "correct" if out.get("correct") else "wrong"


def _by_name(suspects: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = name.strip().lower()
    return next((s for s in suspects if s["name"].lower() == wanted), None)


def _clue_ids(clues: list[dict[str, Any]], numbers: list[int]) -> list[str]:
    return [clues[n - 1]["id"] for n in numbers if 1 <= n <= len(clues)]


def _new(clues: list[dict[str, Any]]) -> str:
    return f"; new clues: {[c['description'] for c in clues]}" if clues else ""
