import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import SecretStr, ValidationError

from app.games import GameService, Outcome
from app.schemas import (
    AccuseBody,
    ActionResult,
    AskMessage,
    Chunk,
    CreateGame,
    Done,
    Event,
    GameView,
    Problem,
    PublicHit,
    ReasonCode,
    Reveal,
    Thinking,
    Validating,
    VersionBody,
)
from app.session import COOKIE, Forbidden, Session, cookie_path, parse, sign

router = APIRouter(prefix="/games", tags=["games"])

STATUS: dict[ReasonCode, int] = {
    "bad_request": 400,
    "denied": 403,
    "not_visible": 404,
    "no_questions_left": 409,
    "no_hints_left": 409,
    "already_accused": 409,
    "not_accused": 409,
    "stale_state": 409,
    "screened": 422,
    "cooldown": 429,
    "budget_exhausted": 429,
    "unavailable": 503,
}
MESSAGES: dict[ReasonCode, str] = {
    "bad_request": "That request is malformed.",
    "denied": "That is not your game.",
    "not_visible": "You cannot see that yet.",
    "no_questions_left": "You have no questions left.",
    "no_hints_left": "You have no hints left.",
    "already_accused": "You have already made your accusation.",
    "not_accused": "The solution is revealed only after your accusation.",
    "stale_state": "The game moved on. Reload and try again.",
    "screened": "I don't follow you, Detective.",
    "cooldown": "Take a moment before you ask again.",
    "budget_exhausted": "That is enough of that for this game.",
    "unavailable": "The house is quiet for a moment. Nothing was spent; try again.",
}
MUTATION_ERRORS: dict[int | str, dict[str, Any]] = {
    s: {"model": Problem} for s in sorted(set(STATUS.values()))
}


class ProblemError(Exception):
    def __init__(self, code: ReasonCode, text: str | None = None, retry: int | None = None):
        super().__init__(code)
        self.problem = Problem(code=code, message=text or MESSAGES[code], retry_after_s=retry)


def problem_response(error: ProblemError) -> JSONResponse:
    p = error.problem
    return JSONResponse(p.model_dump(exclude_none=True), status_code=STATUS[p.code])


def games(request: Request) -> GameService:
    service: GameService | None = request.app.state.games
    if service is None:
        raise ProblemError("unavailable")
    return service


def secret(request: Request) -> SecretStr:
    value: SecretStr | None = request.app.state.secret
    if value is None:
        raise ProblemError("unavailable")
    return value


Secret = Annotated[SecretStr, Depends(secret)]


def session(game_id: str, request: Request, key: Secret) -> Session:
    return parse(request.cookies.get(COOKIE), game_id, key)


def idempotency_key(key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    if key is None or not 8 <= len(key) <= 64:
        raise ProblemError("bad_request", "Send an Idempotency-Key header of 8 to 64 characters.")
    return key


Games = Annotated[GameService, Depends(games)]
Owned = Annotated[Session, Depends(session)]
Key = Annotated[str, Depends(idempotency_key)]


def result(out: Outcome) -> ActionResult:
    if out.code is not None:
        raise ProblemError(out.code, out.text, out.retry_after_s)
    assert out.view is not None
    return ActionResult(
        view=out.view,
        text=out.text,
        document=out.document,
        correct=out.correct,
        new_clues=out.new_clues,
        replayed=out.replayed,
    )


@router.post("", status_code=201, responses={404: {"model": Problem}})
async def create(body: CreateGame, response: Response, service: Games, key: Secret) -> GameView:
    try:
        owner, view = await service.create(body.case_id)
    except KeyError:
        raise ProblemError("not_visible", "No such case.") from None
    response.set_cookie(
        COOKIE,
        sign(owner, key),
        httponly=True,
        samesite="strict",
        path=cookie_path(owner.game_id),
    )
    return view


@router.get("/{game_id}", responses={403: {"model": Problem}})
async def view(owner: Owned, service: Games) -> GameView:
    return await service.view(owner)


@router.get("/{game_id}/search", responses=MUTATION_ERRORS)
async def search(owner: Owned, service: Games, q: str = "") -> list[PublicHit]:
    out = await service.search(owner, q)
    if out.code is not None:
        raise ProblemError(out.code, out.text, out.retry_after_s)
    return out.hits


@router.post("/{game_id}/documents/{doc_id}/open", responses=MUTATION_ERRORS)
async def open_document(
    doc_id: str, body: VersionBody, owner: Owned, service: Games, key: Key
) -> ActionResult:
    args = {"doc_id": doc_id}
    return result(
        await service.execute(
            owner, "open_document", args, key=key, expected_version=body.state_version
        )
    )


@router.post("/{game_id}/hint", responses=MUTATION_ERRORS)
async def hint(body: VersionBody, owner: Owned, service: Games, key: Key) -> ActionResult:
    return result(
        await service.execute(
            owner, "request_hint", {}, key=key, expected_version=body.state_version
        )
    )


@router.post("/{game_id}/accuse", responses=MUTATION_ERRORS)
async def accuse(body: AccuseBody, owner: Owned, service: Games, key: Key) -> ActionResult:
    args = {"suspect": body.suspect, "cited": body.cited}
    return result(
        await service.execute(
            owner, "submit_accusation", args, key=key, expected_version=body.state_version
        )
    )


@router.get("/{game_id}/reveal", responses={403: {"model": Problem}, 409: {"model": Problem}})
async def reveal(owner: Owned, service: Games) -> Reveal:
    return await service.reveal(owner)


@router.get("/{game_id}/solution", include_in_schema=False)
async def honeypot(game_id: str, service: Games) -> JSONResponse:
    await service.honeypot(game_id)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def chunks(text: str) -> list[str]:
    words = re.findall(r"\S+\s*", text)
    size = max(1, min(5, len(words) // 2))
    return ["".join(words[i : i + size]) for i in range(0, len(words), size)]


def release(out: Outcome, *, validating_sent: bool) -> list[Event]:
    """Every chunk is text the service already committed, or a fixed in-character line."""
    events: list[Event] = []
    if out.code is None and out.reply and not validating_sent:
        events.append(Validating())
    events += [Chunk(text=t) for t in chunks(out.reply or "")]
    view = out.view
    events.append(
        Done(
            questions_left=view.questions_left if view else None,
            state_version=view.state_version if view else None,
            new_clues=out.new_clues,
            code=out.code,
            replayed=out.replayed,
            retry_after_s=out.retry_after_s,
        )
    )
    return events


@router.websocket("/{game_id}/ask")
async def ask(ws: WebSocket, game_id: str) -> None:
    service: GameService | None = ws.app.state.games
    try:
        if service is None:
            raise Forbidden(game_id)
        owner = parse(ws.cookies.get(COOKIE), game_id, ws.app.state.secret)
    except Forbidden:
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        while True:
            await _turn(ws, service, owner, await ws.receive_text())
    except WebSocketDisconnect:
        return
    except Forbidden:
        await ws.close(code=4403)


async def _turn(ws: WebSocket, service: GameService, owner: Session, frame: str) -> None:
    try:
        msg = AskMessage.model_validate(json.loads(frame))
    except (ValueError, ValidationError):
        bad = Done(questions_left=None, state_version=None, code="bad_request")
        await ws.send_json(bad.model_dump())
        return
    await ws.send_json(Thinking().model_dump())
    sent = False

    async def stage(_: str) -> None:
        nonlocal sent
        if not sent:
            sent = True
            await ws.send_json(Validating().model_dump())

    confront = bool(msg.present or msg.documents)
    args: dict[str, object] = {"suspect": msg.suspect, "question": msg.question}
    if confront:
        args |= {"present": msg.present, "documents": msg.documents}
    out = await service.execute(
        owner,
        "confront_evidence" if confront else "ask_question",
        args,
        key=msg.idempotency_key,
        expected_version=msg.state_version,
        on_stage=stage,
    )
    for event in release(out, validating_sent=sent):
        await ws.send_json(event.model_dump())
