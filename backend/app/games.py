import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import sqlalchemy as sa
from pydantic import BaseModel, ValidationError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from agents.events import log_event
from agents.game_master import (
    Accusation,
    DocumentLocked,
    GameState,
    NoHint,
    new_game,
    next_hint,
    open_document,
    record_reply,
    rule_accusation,
    spend_question,
    timeline,
)
from agents.screening import screen_input
from agents.state import OnStage, Talk, TurnInput
from agents.suspect import FALLBACK, Interrogation, StaleState
from app.db import sync_engine
from app.schemas import (
    DocumentBody,
    GameView,
    Ids,
    PublicClue,
    PublicHit,
    RawIds,
    ReasonCode,
    Reveal,
    clues,
)
from app.session import Forbidden, Session, new_session
from engine.schema import Case, Id
from evidence import AuthorizedRetriever, PlayerScope
from security.context import ActorType, AuthContext, case_version
from security.events import AuditRow, TraceStep, insert_rows
from security.grants import grants_for
from security.tool_broker import (
    AccuseArgs,
    Args,
    AskArgs,
    Call,
    ConfrontArgs,
    Denied,
    OpenArgs,
    SearchArgs,
    SuspectArgs,
    ToolBroker,
    ToolName,
)

log = logging.getLogger(__name__)

TURN_TIMEOUT_S = 15.0
SCREENED = "I don't follow you, Detective."
PUBLIC_CODES: dict[str, ReasonCode] = {
    "unknown_tool": "denied",
    "actor_not_allowed": "denied",
    "bad_args": "bad_request",
}

METADATA = sa.MetaData()
GAMES = sa.Table(
    "games",
    METADATA,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("case_id", sa.Text),
    sa.Column("case_version", sa.Text),
    sa.Column("actor_type", sa.Text),
    sa.Column("session_digest", sa.Text),
    sa.Column("state", JSONB),
    sa.Column("state_version", sa.Integer),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("abuse_flag", sa.Boolean),
)
TURNS = sa.Table(
    "turns",
    METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("game_id", sa.Text),
    sa.Column("idempotency_key", sa.Text),
    sa.Column("args_hash", sa.Text),
    sa.Column("state_version", sa.Integer),
    sa.Column("tool", sa.Text),
    sa.Column("suspect", sa.Text),
    sa.Column("reply", sa.Text),
    sa.Column("verdict", JSONB),
    sa.Column("outcome", JSONB),
    sa.Column("cost_usd", sa.Double),
)
OUTBOX = sa.Table(
    "outbox",
    METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("game_id", sa.Text),
    sa.Column("state_version", sa.Integer),
    sa.Column("kind", sa.Text),
    sa.Column("payload", JSONB),
)
LLM_COST = sa.text(
    "select coalesce(sum(cost_usd), 0) from llm_calls where game_id = :g and created_at >= :t"
)


class NotAccused(Exception):
    pass


class Outcome(BaseModel):
    view: GameView | None = None
    reply: str | None = None
    code: ReasonCode | None = None
    text: str | None = None
    hinted: bool = False
    document: DocumentBody | None = None
    correct: bool | None = None
    new_clues: list[PublicClue] = []
    hits: list[PublicHit] = []
    replayed: bool = False
    retry_after_s: int | None = None


@dataclass(frozen=True)
class Loaded:
    case: Case
    state: GameState
    version: int
    ctx: AuthContext
    ids: Ids

    @property
    def id(self) -> str:
        return self.ctx.game_id

    @property
    def view(self) -> GameView:
        return GameView.of(self.case, self.state, self.version, self.ids)


@dataclass(frozen=True)
class Stored:
    args_hash: str
    outcome: Outcome


class _Stale(Exception):
    pass


Handler = Callable[[Loaded, Call[Args], OnStage | None], Awaitable[Outcome]]


def args_hash(tool: ToolName, args: Args) -> str:
    canonical = json.dumps({"tool": tool, "args": args.model_dump(mode="json")}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class GameService:
    """The one game path for HTTP, WebSocket, the CLI, and (P5) the detective bot."""

    def __init__(
        self,
        engine: AsyncEngine,
        cases: Mapping[Id, Case],
        *,
        ids: Callable[[str], Ids] = lambda _: RawIds(),
        broker: ToolBroker | None = None,
        retriever: AuthorizedRetriever | None = None,
        timeout_s: float = TURN_TIMEOUT_S,
    ) -> None:
        self._engine = engine
        self._cases = cases
        self._ids = ids
        self._broker = broker or ToolBroker(engine)
        self._retriever = retriever or AuthorizedRetriever(
            sync_engine(engine.url.render_as_string(hide_password=False))
        )
        self._timeout = timeout_s
        self._inflight: dict[tuple[str, str], asyncio.Future[Outcome]] = {}
        self._handlers: dict[ToolName, Handler] = {
            "ask_question": self._ask,
            "confront_evidence": self._ask,
            "open_document": self._open,
            "request_hint": self._hint,
            "submit_accusation": self._accuse,
            "read_visible_evidence": self._search,
            "query_suspect_knowledge": self._knowledge,
            "lookup_public_statement": self._statement,
        }
        assert set(self._handlers) == set(self._broker.tools), "every tool needs one handler"

    async def create(
        self, case_id: Id, actor: ActorType = "player", game_id: str | None = None
    ) -> tuple[Session, GameView]:
        case = self._cases[case_id]
        session = new_session(game_id or uuid.uuid4().hex)
        state = new_game(case, session.game_id)
        async with self._engine.begin() as conn:
            await conn.execute(
                sa.insert(GAMES).values(
                    id=session.game_id,
                    case_id=case.id,
                    case_version=case_version(case),
                    actor_type=actor,
                    session_digest=session.digest,
                    state=state.model_dump(mode="json"),
                )
            )
        return session, GameView.of(case, state, 0, self._ids(session.game_id))

    async def view(self, session: Session) -> GameView:
        return (await self._load(session)).view

    async def execute(
        self,
        session: Session,
        tool: str,
        args: Mapping[str, object],
        *,
        key: str,
        expected_version: int | None,
        on_stage: OnStage | None = None,
    ) -> Outcome:
        flight = (session.game_id, key)
        running = self._inflight.get(flight)
        if running is None:
            running = asyncio.ensure_future(
                self._settle(session, tool, args, key, expected_version, on_stage)
            )
            self._inflight[flight] = running
            running.add_done_callback(lambda _: self._inflight.pop(flight, None))
            return await asyncio.shield(running)
        out = await asyncio.shield(running)
        return out.model_copy(update={"replayed": True})

    async def search(self, session: Session, query: str) -> Outcome:
        args = {"query": query}
        return await self.execute(
            session, "read_visible_evidence", args, key=uuid.uuid4().hex, expected_version=None
        )

    async def reveal(self, session: Session) -> Reveal:
        g = await self._load(session)
        accusation = g.state.accusation
        if accusation is None:
            raise NotAccused(g.id)
        return Reveal(
            ruling=accusation.text,
            correct=accusation.correct,
            culprit=g.case.culprit,
            accused=accusation.suspect,
            chain=list(g.case.solution_chain),
            cited_chain=list(accusation.chain_cited),
            timeline=timeline(g.case),
        )

    async def honeypot(self, game_id: str) -> None:
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    sa.update(GAMES)
                    .where(GAMES.c.id == game_id)
                    .values(abuse_flag=True)
                    .returning(GAMES.c.case_version, GAMES.c.state_version)
                )
            ).first()
        if row is not None:
            ctx = AuthContext(game_id, "player", game_id, row.case_version, row.state_version)
            await self._broker.record(ctx, "honeypot", uuid.uuid4().hex, "honeypot", allowed=False)

    async def _settle(
        self,
        session: Session,
        tool: str,
        args: Mapping[str, object],
        key: str,
        expected_version: int | None,
        on_stage: OnStage | None,
    ) -> Outcome:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._execute(session, tool, args, key, expected_version, on_stage)
        except Forbidden:
            raise
        except Denied as d:
            code = PUBLIC_CODES.get(d.code, d.code)
            view = await self._view_or_none(session)
            return Outcome(view=view, code=code, retry_after_s=d.retry_after_s)
        except Exception:
            log.exception("turn failed closed: game=%s tool=%s", session.game_id, tool)
            view = await self._view_or_none(session)
            return Outcome(view=view, reply=FALLBACK, code="unavailable")

    async def _view_or_none(self, session: Session) -> GameView | None:
        try:
            return await self.view(session)
        except Exception:
            return None

    async def _execute(
        self,
        session: Session,
        tool: str,
        args: Mapping[str, object],
        key: str,
        expected_version: int | None,
        on_stage: OnStage | None,
    ) -> Outcome:
        g = await self._load(session)
        raw = self._raw_args(g, args)
        stored = await self._stored(g.id, key)
        if stored is not None:
            return await self._replay(g, tool, raw, key, stored)
        if expected_version is not None and expected_version != g.version:
            raise Denied("stale_state")
        async with self._broker.authorized_call(g.ctx, tool, raw, key) as call:
            return await self._handlers[call.tool](g, call, on_stage)

    async def _replay(
        self, g: Loaded, tool: str, raw: Mapping[str, object], key: str, stored: Stored
    ) -> Outcome:
        if tool not in self._broker.tools:
            raise Denied("bad_request")
        name = cast(ToolName, tool)
        try:
            same = stored.args_hash == args_hash(name, self._broker.tools[name].args(**raw))
        except ValidationError:
            same = False
        if not same:
            raise Denied("bad_request")
        await self._broker.record(g.ctx, name, key, "replayed", allowed=True)
        return stored.outcome.model_copy(update={"view": g.view, "replayed": True})

    async def _load(self, session: Session) -> Loaded:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(sa.select(GAMES).where(GAMES.c.id == session.game_id))
            ).first()
        if row is None or row.session_digest != session.digest:
            raise Forbidden(session.game_id)
        case = self._cases[row.case_id]
        if case_version(case) != row.case_version:
            raise Forbidden(session.game_id)
        ctx = AuthContext(
            session.game_id, row.actor_type, session.game_id, row.case_version, row.state_version
        )
        state = GameState.model_validate(row.state)
        return Loaded(case, state, row.state_version, ctx, self._ids(session.game_id))

    async def _stored(self, game_id: str, key: str) -> Stored | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.select(TURNS.c.args_hash, TURNS.c.outcome).where(
                        TURNS.c.game_id == game_id, TURNS.c.idempotency_key == key
                    )
                )
            ).first()
        return None if row is None else Stored(row.args_hash, Outcome.model_validate(row.outcome))

    def _raw_args(self, g: Loaded, args: Mapping[str, object]) -> dict[str, object]:
        suspects = [s.id for s in g.case.suspects]
        found = [c.id for c in g.case.clues]
        raw = dict(args)
        if isinstance(raw.get("suspect"), str):
            raw["suspect"] = g.ids.parse(str(raw["suspect"]), suspects)
        for name in ("present", "cited"):
            value = raw.get(name)
            if isinstance(value, list | tuple):
                raw[name] = tuple(g.ids.parse(v, found) if isinstance(v, str) else v for v in value)
        return raw

    async def _commit(
        self,
        g: Loaded,
        call: Call[Args],
        nxt: GameState,
        out: Outcome,
        reason: str,
        *,
        suspect: Id | None = None,
        verdict: Mapping[str, object] | None = None,
        rows: tuple[AuditRow, ...] = (),
        started: datetime | None = None,
    ) -> Outcome:
        version = g.version + 1
        stored = out.model_dump(mode="json", exclude={"view", "replayed"})
        clock = datetime.now(UTC)
        try:
            async with self._engine.begin() as conn:
                updated = await conn.execute(
                    sa.update(GAMES)
                    .where(GAMES.c.id == g.id, GAMES.c.state_version == g.version)
                    .values(
                        state=nxt.model_dump(mode="json"),
                        state_version=version,
                        finished_at=sa.func.now() if nxt.accusation else None,
                    )
                )
                if updated.rowcount == 0:
                    raise _Stale
                cost = await conn.scalar(LLM_COST, {"g": g.id, "t": started or clock})
                await conn.execute(
                    sa.insert(TURNS).values(
                        game_id=g.id,
                        idempotency_key=call.key,
                        args_hash=args_hash(call.tool, call.args),
                        state_version=version,
                        tool=call.tool,
                        suspect=suspect,
                        reply=out.reply,
                        verdict=dict(verdict or {}),
                        outcome=stored,
                        cost_usd=cost,
                    )
                )
                await conn.execute(
                    sa.insert(OUTBOX).values(
                        game_id=g.id, state_version=version, kind=call.tool, payload=stored
                    )
                )
                ms = round((datetime.now(UTC) - clock).total_seconds() * 1000, 3)
                step = TraceStep(step="commit", outcome=reason, ms=ms)
                await insert_rows(conn, [*rows, call.row(reason, extra=[step])])
        except _Stale:
            won = await self._stored(g.id, call.key)
            if won is None:
                raise Denied("stale_state") from None
            call.settle("replayed")
            return won.outcome.model_copy(update={"view": g.view, "replayed": True})
        call.written = True
        return out.model_copy(update={"view": GameView.of(g.case, nxt, version, g.ids)})

    def _refuse(self, g: Loaded, call: Call[Args], code: ReasonCode, text: str = "") -> Outcome:
        call.settle(code, allowed=False)
        return Outcome(view=g.view, code=code, text=text or None)

    def _found(self, g: Loaded, before: GameState, after: GameState) -> list[PublicClue]:
        return clues(g.case, set(after.discovered) - set(before.discovered), g.ids)

    async def _ask(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(AskArgs)
        s = g.state
        present = a.present if isinstance(a, ConfrontArgs) else ()
        documents = a.documents if isinstance(a, ConfrontArgs) else ()
        if s.accusation is not None:
            return self._refuse(g, call, "already_accused")
        if a.suspect not in {p.id for p in g.case.suspects}:
            return self._refuse(g, call, "not_visible")
        if s.questions_left <= 0:
            return self._refuse(g, call, "no_questions_left")
        talk = s.talks.get(a.suspect, Talk())
        if not screen_input(a.question).allowed:
            await asyncio.to_thread(
                log_event,
                game_id=g.id,
                suspect=a.suspect,
                turn=len(talk.history) + 1,
                rule="input_screen",
                claim=a.question,
                action="refuse",
            )
            call.settle("screened", allowed=False)
            return Outcome(view=g.view, reply=SCREENED, code="screened")
        if not (set(present) <= set(s.discovered) and set(documents) <= set(s.opened)):
            return self._refuse(g, call, "not_visible")
        started = datetime.now(UTC)
        turn = TurnInput(question=a.question, present=present, documents=documents)
        try:
            report = await Interrogation(g.case, g.id).ask(
                talk, a.suspect, turn, state_version=g.version, on_stage=on_stage
            )
        except StaleState:
            raise Denied("stale_state") from None
        nxt = s.model_copy(update={"talks": {**s.talks, a.suspect: report.talk}})
        if not report.fell_back:
            told = [(c.verdict, c.ref) for c in report.checks]
            nxt = record_reply(g.case, spend_question(nxt), told)
        verdict = {
            "fell_back": report.fell_back,
            "drafts": len(report.attempts),
            "verdicts": sorted(c.verdict.value for c in report.checks),
        }
        out = Outcome(reply=report.reply, new_clues=self._found(g, s, nxt))
        reason = "fallback" if report.fell_back else "released"
        return await self._commit(
            g,
            call,
            nxt,
            out,
            reason,
            suspect=a.suspect,
            verdict=verdict,
            rows=report.audit,
            started=started,
        )

    async def _open(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(OpenArgs)
        try:
            nxt, doc = open_document(g.case, g.state, a.doc_id)
        except (KeyError, DocumentLocked):
            return self._refuse(g, call, "not_visible")
        body = DocumentBody(id=doc.id, title=doc.title, source=doc.source, body=doc.body)
        out = Outcome(document=body, new_clues=self._found(g, g.state, nxt))
        return await self._commit(g, call, nxt, out, "opened")

    async def _hint(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        if g.state.accusation is not None:
            return self._refuse(g, call, "already_accused")
        nxt, hint = next_hint(g.case, g.state)
        if isinstance(hint, NoHint):
            if g.state.hints_left <= 0:
                return self._refuse(g, call, "no_hints_left", hint.text)
            call.settle("no_lead")
            return Outcome(view=g.view, text=hint.text)
        return await self._commit(g, call, nxt, Outcome(text=hint.text, hinted=True), "hint")

    async def _accuse(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(AccuseArgs)
        s = g.state
        if s.accusation is not None:
            return self._refuse(g, call, "already_accused")
        known = a.suspect in {p.id for p in g.case.suspects}
        if not (known and set(a.cited) <= set(s.discovered)):
            return self._refuse(g, call, "not_visible")
        ruling = rule_accusation(g.case, a.suspect, a.cited)
        accusation = Accusation(
            suspect=a.suspect,
            cited=a.cited,
            chain_cited=ruling.chain_cited,
            correct=ruling.correct,
            text=ruling.text,
        )
        nxt = s.model_copy(update={"accusation": accusation})
        out = Outcome(text=ruling.text, correct=ruling.correct)
        return await self._commit(g, call, nxt, out, "accused")

    async def _search(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(SearchArgs)
        scope = PlayerScope.of(g.ctx, g.case, g.state)
        hits = await asyncio.to_thread(self._retriever.search, scope, a.query, a.k)
        public = [
            PublicHit(
                document_id=h.document_id,
                title=h.title,
                source=h.source,
                visibility=h.visibility,
                highlight=h.highlight,
                score=h.score,
            )
            for h in hits
        ]
        return Outcome(view=g.view, hits=public)

    async def _statement(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(SuspectArgs)
        person = next((p for p in g.case.suspects if p.id == a.suspect), None)
        if person is None:
            return self._refuse(g, call, "not_visible")
        return Outcome(view=g.view, text=f"{person.name}: {person.description}")

    async def _knowledge(self, g: Loaded, call: Call[Args], on_stage: OnStage | None) -> Outcome:
        a = call.parsed(SuspectArgs)
        known = sorted(f for who, f in grants_for(g.case) if who == a.suspect)
        return Outcome(text=", ".join(known))
