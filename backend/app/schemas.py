import hmac
from collections.abc import Iterable
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field, SecretStr

from agents.game_master import GameState
from engine.schema import Case, Id

ReasonCode = Literal[
    "no_questions_left",
    "no_hints_left",
    "not_visible",
    "already_accused",
    "not_accused",
    "screened",
    "cooldown",
    "stale_state",
    "denied",
    "unavailable",
    "budget_exhausted",
    "bad_request",
]


class Ids(Protocol):
    def show(self, raw: Id) -> str: ...

    def parse(self, shown: str, among: Iterable[Id]) -> str: ...


class RawIds:
    def show(self, raw: Id) -> str:
        return raw

    def parse(self, shown: str, among: Iterable[Id]) -> str:
        return shown


class Handles:
    """Suspect and clue ids over HTTP: a per-game handle, so no response names the culprit or a
    solution_chain clue by id before the reveal."""

    def __init__(self, secret: SecretStr, game_id: str) -> None:
        self._key = secret.get_secret_value().encode()
        self._game = game_id

    def show(self, raw: Id) -> str:
        mac = hmac.new(self._key, f"{self._game}:{raw}".encode(), "sha256").hexdigest()
        return f"h_{mac[:10]}"

    def parse(self, shown: str, among: Iterable[Id]) -> str:
        return next((raw for raw in among if self.show(raw) == shown), "")


class PublicSuspect(BaseModel):
    id: str
    name: str
    description: str


class PublicClue(BaseModel):
    id: str
    description: str


class PublicDoc(BaseModel):
    id: Id
    title: str
    source: Id
    opened: bool


class GameView(BaseModel):
    game_id: str
    title: str
    summary: str
    time_slots: list[str]
    suspects: list[PublicSuspect]
    documents: list[PublicDoc]
    clues: list[PublicClue]
    questions_left: int
    hints_left: int
    state_version: int
    accused: bool

    @classmethod
    def of(cls, case: Case, state: GameState, state_version: int, ids: Ids) -> "GameView":
        return cls(
            game_id=state.game_id,
            title=case.title,
            summary=case.summary,
            time_slots=list(case.time_slots),
            suspects=[
                PublicSuspect(id=ids.show(s.id), name=s.name, description=s.description)
                for s in case.suspects
            ],
            documents=[
                PublicDoc(id=d.id, title=d.title, source=d.source, opened=d.id in state.opened)
                for d in state.visible(case)
            ],
            clues=clues(case, state.discovered, ids),
            questions_left=state.questions_left,
            hints_left=state.hints_left,
            state_version=state_version,
            accused=state.accusation is not None,
        )


def clues(case: Case, found: Iterable[Id], ids: Ids) -> list[PublicClue]:
    found = set(found)
    return [
        PublicClue(id=ids.show(c.id), description=c.description)
        for c in case.clues
        if c.id in found
    ]


class DocumentBody(BaseModel):
    id: Id
    title: str
    source: Id
    body: str


class PublicHit(BaseModel):
    document_id: Id
    title: str
    source: Id
    visibility: Literal["open", "unlocked"]
    sensitivity: Literal["player"] = "player"
    provenance: Literal["case_document"] = "case_document"
    highlight: str
    score: float


class ActionResult(BaseModel):
    view: GameView
    text: str | None = None
    document: DocumentBody | None = None
    correct: bool | None = None
    new_clues: list[PublicClue] = []
    replayed: bool = False


class Reveal(BaseModel):
    ruling: str
    correct: bool
    culprit: Id
    accused: Id
    chain: list[Id]
    cited_chain: list[Id]
    timeline: list[str]


class Problem(BaseModel):
    code: ReasonCode
    message: str
    retry_after_s: int | None = None


class CreateGame(BaseModel):
    case_id: Id


class VersionBody(BaseModel):
    state_version: int


class AccuseBody(VersionBody):
    suspect: str
    cited: list[str]


class AskMessage(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    state_version: int
    suspect: str
    question: str = Field(max_length=500)
    present: list[str] = []
    documents: list[str] = []


class Thinking(BaseModel):
    type: Literal["thinking"] = "thinking"


class Validating(BaseModel):
    type: Literal["validating"] = "validating"


class Chunk(BaseModel):
    type: Literal["chunk"] = "chunk"
    text: str


class Done(BaseModel):
    type: Literal["done"] = "done"
    questions_left: int | None
    state_version: int | None
    new_clues: list[PublicClue] = []
    code: ReasonCode | None = None
    replayed: bool = False
    retry_after_s: int | None = None


Event = Annotated[Thinking | Validating | Chunk | Done, Field(discriminator="type")]
