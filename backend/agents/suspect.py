import argparse
import asyncio
import re
import sys
import time
import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from agents import prompts
from agents.documents import quote_document
from agents.events import Action, Rule, log_event
from agents.extract import ExtractionFailed, extract_claims
from agents.ledger import LedgerEntry
from agents.state import Attempt, Check, OnStage, Seat, SuspectState, Talk, TurnInput
from agents.verifier import UNKNOWN, Verdict, leaks_canary, verify_reply
from agents.view import (
    Exchange,
    PermittedClaims,
    PublicCase,
    SuspectView,
    build_view,
    suspect_context,
)
from app.llm import ModelRole, complete
from engine.schema import Case, Id, Statement
from security.context import AuthContext
from security.events import AuditRow, TraceStep, audit_row, log_decisions
from security.policy import Decision, PolicyContext, Resource, authorize

FALLBACK = "I'd rather not answer that."
MAX_ATTEMPTS = 3
SUSPECT_ROLE = ModelRole.FAST
SUSPECT_MAX_TOKENS = 1024
SUSPECT = prompts.load("suspect")
REWRITE = prompts.load("rewrite")
ALLOWED = {Verdict.ADMISSION: "facts", Verdict.KNOWN_TRUE: "facts", Verdict.PLANNED_LIE: "lies"}

Node = Literal[
    "retrieve",
    "permitted_claims",
    "generate",
    "extract",
    "verify",
    "rewrite",
    "fallback",
    "commit",
]


class StaleState(RuntimeError):
    pass


@dataclass(frozen=True)
class TurnReport:
    turn: int
    reply: str
    attempts: tuple[Attempt, ...]
    fell_back: bool
    ledger: tuple[LedgerEntry, ...]
    talk: Talk
    audit: tuple[AuditRow, ...]

    @property
    def rewrites(self) -> int:
        return len(self.attempts) - 1

    @property
    def checks(self) -> tuple[Check, ...]:
        return () if self.fell_back else self.attempts[-1].checks


class Interrogation:
    """Runs one suspect turn from a stored Talk and proposes the next one. Writes no game state."""

    def __init__(self, case: Case, game_id: str) -> None:
        self.case = case
        self.game_id = game_id
        self._graph = GRAPH.compile()

    async def ask(
        self,
        talk: Talk,
        suspect: Id,
        turn: TurnInput,
        *,
        state_version: int,
        on_stage: OnStage | None = None,
    ) -> TurnReport:
        if suspect not in {s.id for s in self.case.suspects}:
            raise ValueError(f"unknown suspect '{suspect}'")
        unknown = set(turn.present) - {c.id for c in self.case.clues}
        if unknown:
            raise ValueError(f"unknown clues {sorted(unknown)}")
        missing = set(turn.documents) - {d.id for d in self.case.documents}
        if missing:
            raise ValueError(f"unknown documents {sorted(missing)}")
        start = SuspectState(
            **dict(talk),
            question=turn.question,
            present=tuple(sorted(set(turn.present))),
            documents=tuple(sorted(set(turn.documents))),
        )
        seat = Seat(self.case, suspect, self.game_id, state_version, on_stage)
        state = SuspectState.model_validate(await self._graph.ainvoke(start, context=seat))
        return TurnReport(
            turn=len(state.history),
            reply=state.history[-1].reply,
            attempts=state.attempts,
            fell_back=state.fell_back,
            ledger=state.ledger.of(suspect),
            talk=Talk(ledger=state.ledger, presented=state.presented, history=state.history),
            audit=state.audit,
        )


class Interview:
    """Keeps each suspect's Talk in memory and logs its audit rows: evals and tests only.
    A served game keeps Talk in its games row and commits the rows with the turn."""

    def __init__(self, case: Case, game_id: str) -> None:
        self.room = Interrogation(case, game_id)
        self.talks: dict[Id, Talk] = {}
        self._locks: dict[Id, asyncio.Lock] = {}

    @property
    def game_id(self) -> str:
        return self.room.game_id

    def state(self, suspect: Id) -> Talk:
        return self.talks.get(suspect, Talk())

    async def ask(
        self,
        suspect: Id,
        question: str,
        present: Iterable[Id] = (),
        documents: Iterable[Id] = (),
    ) -> TurnReport:
        turn = TurnInput(question=question, present=tuple(present), documents=tuple(documents))
        async with self._locks.setdefault(suspect, asyncio.Lock()):
            talk = self.state(suspect)
            report = await self.room.ask(talk, suspect, turn, state_version=len(talk.history))
            self.talks[suspect] = report.talk
        await asyncio.to_thread(log_decisions, report.audit)
        return report


async def retrieve(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    seat = runtime.context
    subject = suspect_context(seat.case, seat.suspect, seat.game_id, seat.state_version)
    view, trace = build_view(
        seat.case, subject, state.shown, state.ledger.of(seat.suspect), state.recent
    )
    trace_id = uuid.uuid4().hex
    row = _row(subject, trace_id, state.turn, "retrieve", "knowledge", _ok("view_built"), trace)
    return {
        "attempts": (),
        "fell_back": False,
        "trace_id": trace_id,
        "view": view,
        "audit": (row,),
    }


async def permitted_claims(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    return {"permitted": PermittedClaims.of(_view(state))}


async def generate(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    text = await _speak(
        runtime.context, suspect_messages(_view(state), state, runtime.context.case)
    )
    return {"attempts": (Attempt(draft=text),)}


async def extract(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    seat = runtime.context
    if seat.on_stage is not None and len(state.attempts) == 1:
        await seat.on_stage("validating")
    last = state.attempts[-1]
    try:
        claims = await extract_claims(
            last.draft, seat.case, seat.suspect, question=state.question, game_id=seat.game_id
        )
        update: dict[str, object] = {"claims": tuple(claims)}
    except ExtractionFailed:
        update = {"unreadable": True}
    return {"attempts": (*state.attempts[:-1], last.model_copy(update=update))}


async def verify(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    seat = runtime.context
    last = state.attempts[-1]
    started = time.perf_counter()
    result = verify_reply(seat.case, seat.suspect, last.claims, state.ledger, state.shown)
    permitted = state.permitted or PermittedClaims(facts=(), lies=())
    checks = tuple(bound(Check.of(c), permitted) for c in result.checks)
    unchecked = narrates(last.draft) or (not last.claims and mentions_case(seat.case, last.draft))
    leaked = leaks_canary(seat.case, last.draft)
    attempt = last.model_copy(update={"checks": checks, "unchecked": unchecked, "leaked": leaked})
    reason = (
        "verified"
        if attempt.verified
        else "canary"
        if leaked
        else "blocked_claims"
        if attempt.blocked
        else "unchecked"
    )
    decision = _ok(reason) if attempt.verified else Decision("deny", reason)
    ms = (time.perf_counter() - started) * 1000
    outcome = f"claims={len(checks)} blocked={len(attempt.blocked)} attempt={len(state.attempts)}"
    trace = (TraceStep(step="verify", outcome=outcome, ms=round(ms, 3)),)
    subject = _subject(seat, state)
    row = _row(subject, state.trace_id, state.turn, "verify", "reply", decision, trace)
    return {"attempts": (*state.attempts[:-1], attempt), "audit": (*state.audit, row)}


def bound(check: Check, permitted: PermittedClaims) -> Check:
    kind = ALLOWED.get(check.verdict)
    if kind is None or check.ref in getattr(permitted, kind):
        return check
    return check.model_copy(update={"verdict": Verdict.BLOCK_UNPLANNED, "reason": UNKNOWN})


def after_draft(state: SuspectState) -> Literal["extract", "fallback"]:
    return "extract" if state.attempts[-1].draft else "fallback"


def after_verify(state: SuspectState) -> Literal["commit", "rewrite", "fallback"]:
    if state.attempts[-1].verified:
        return "commit"
    return "rewrite" if len(state.attempts) < MAX_ATTEMPTS else "fallback"


def mentions_case(case: Case, text: str) -> bool:
    words = set(re.findall(r"[a-z]+", text.lower()))
    names = [p.name for p in (case.victim, *case.suspects)]
    names += [*case.locations.values(), *case.items.values()]
    names += [*case.locations, *case.items, *(p.id for p in case.suspects)]
    tokens = {w for n in names for w in re.findall(r"[a-z]+", n.lower().replace("_", " "))}
    return bool(words & (tokens - _COMMON))


_COMMON = frozenset({"the", "mr", "mrs", "dr", "lord", "lady", "miss", "of", "and"})


def narrates(text: str) -> bool:
    return len([p for p in re.split(r"\n\s*\n", text) if p.strip()]) > 1


async def rewrite(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    seat = runtime.context
    last = state.attempts[-1]
    messages = [
        *suspect_messages(_view(state), state, seat.case),
        {"role": "assistant", "content": last.draft},
        {"role": "user", "content": rewrite_request(last.feedback)},
    ]
    text = await _speak(seat, messages, f"{SUSPECT.version}+{REWRITE.version}")
    await _log_unverified(seat, state, "rewrite")
    return {"attempts": (*state.attempts, Attempt(draft=text))}


async def fallback(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    await _log_unverified(runtime.context, state, "fallback")
    return {"fell_back": True}


async def commit(state: SuspectState, runtime: Runtime[Seat]) -> dict[str, object]:
    seat = runtime.context
    view = _view(state)
    master = AuthContext(
        "game_master", "game_master", seat.game_id, view.case_version, view.state_version
    )
    turn = Resource("turn", str(state.turn), view.case_version, "conversation")
    decision = authorize(master, "commit_turn", turn, PolicyContext(seat.state_version))
    outcome = "fallback" if state.fell_back else "released"
    trace = (TraceStep(step="commit", outcome=outcome, ms=0.0),)
    row = _row(master, state.trace_id, state.turn, "commit_turn", "turn", decision, trace)
    if not decision.allowed:
        raise StaleState(decision.reason_code)
    claims = () if state.fell_back else state.attempts[-1].claims
    result = verify_reply(seat.case, seat.suspect, claims, state.ledger, state.shown)
    reply = FALLBACK if state.fell_back else state.attempts[-1].draft
    exchange = Exchange(
        question=state.question, shown=state.present, reply=reply, handed=state.documents
    )
    return {
        "ledger": result.commit(state.turn),
        "history": (*state.history, exchange),
        "presented": state.shown,
        "audit": (*state.audit, row),
    }


def _build() -> StateGraph[SuspectState, Seat, SuspectState, SuspectState]:
    g = StateGraph(SuspectState, context_schema=Seat)
    g.add_node("retrieve", retrieve)
    g.add_node("permitted_claims", permitted_claims)
    g.add_node("generate", generate)
    g.add_node("extract", extract)
    g.add_node("verify", verify)
    g.add_node("rewrite", rewrite)
    g.add_node("fallback", fallback)
    g.add_node("commit", commit)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "permitted_claims")
    g.add_edge("permitted_claims", "generate")
    g.add_conditional_edges("generate", after_draft)
    g.add_edge("extract", "verify")
    g.add_conditional_edges("verify", after_verify)
    g.add_conditional_edges("rewrite", after_draft)
    g.add_edge("fallback", "commit")
    g.add_edge("commit", END)
    return g


GRAPH = _build()


async def _speak(seat: Seat, messages: list[dict[str, Any]], version: str = "") -> str:
    out = await asyncio.to_thread(
        complete,
        SUSPECT_ROLE,
        messages,
        purpose="suspect",
        game_id=seat.game_id,
        max_tokens=SUSPECT_MAX_TOKENS,
        prompt_version=version or SUSPECT.version,
    )
    return out.text.strip()


def _view(state: SuspectState) -> SuspectView:
    if state.view is None:
        raise RuntimeError("the turn has no view; retrieve must run first")
    return state.view


def _subject(seat: Seat, state: SuspectState) -> AuthContext:
    view = _view(state)
    return AuthContext(seat.suspect, "suspect", seat.game_id, view.case_version, view.state_version)


def _ok(reason: str) -> Decision:
    return Decision("allow", reason)


def _row(
    subject: AuthContext,
    trace_id: str,
    turn: int,
    action: str,
    resource_type: str,
    decision: Decision,
    trace: tuple[TraceStep, ...],
) -> AuditRow:
    return audit_row(
        subject,
        trace_id=trace_id,
        turn_id=turn,
        action=action,
        resource_type=resource_type,
        decision=decision,
        trace=trace,
        prompt_version=SUSPECT.version,
    )


async def _log_unverified(seat: Seat, state: SuspectState, action: Action) -> None:
    last = state.attempts[-1]
    rows: list[tuple[Rule, str]] = [(c.rule, c.claim.render()) for c in last.blocked]
    if last.leaked:
        rows.append(("unverified", "canary"))
    if not rows:
        reason = "empty draft" if not last.draft else "no checkable claims"
        rows = [("unverified", reason)]
    for rule, claim in rows:
        await asyncio.to_thread(
            log_event,
            game_id=seat.game_id,
            suspect=seat.suspect,
            turn=state.turn,
            rule=rule,
            claim=claim,
            action=action,
        )


def suspect_messages(view: SuspectView, state: SuspectState, case: Case) -> list[dict[str, Any]]:
    docs = {d.id: d for d in case.documents}

    def line(question: str, shown: Collection[Id], handed: Collection[Id]) -> str:
        quoted = [SUSPECT.render("document", quoted=quote_document(docs[i])) for i in handed]
        return _player_line(view, question, shown, quoted)

    messages: list[dict[str, Any]] = [{"role": "system", "content": suspect_brief(view)}]
    for x in view.history:
        messages.append({"role": "user", "content": line(x.question, x.shown, x.handed)})
        messages.append({"role": "assistant", "content": x.reply})
    messages.append(
        {"role": "user", "content": line(state.question, state.present, state.documents)}
    )
    return messages


def suspect_brief(view: SuspectView) -> str:
    public, me = view.public, view.me.id

    def say(s: Statement) -> str:
        return render_statement(public, s, me)

    intro = SUSPECT.render(
        "intro",
        name=view.me.name,
        description=view.me.description,
        title=public.title,
        summary=public.summary,
        hours=", ".join(public.time_slots),
    )
    lines = [intro, *([f"- {say(f)}" for f in view.stateable] or [SUSPECT.render("nothing")])]
    if view.hidden:
        lines += ["", SUSPECT.render("secrets"), *(f"- {say(f)}" for f in view.hidden)]
    if view.shown:
        lines += ["", SUSPECT.render("shown"), *(f"- {c.description}" for c in view.shown)]
    if view.proven:
        lines += ["", SUSPECT.render("proven"), *(f"- {say(f)}" for f in view.proven)]
    for s in view.lies:
        claim = say(s.lie.claim)
        section = "spent_lie" if s.spent else "cover_story"
        lines += ["", SUSPECT.render(section, claim=claim, says=s.lie.says)]
    lines += ["", SUSPECT.render("closing")]
    return "\n".join(lines)


def render_statement(case: PublicCase, s: Statement, me: Id) -> str:
    names = {p.id: p.name for p in (*case.suspects, case.victim)}
    who = "you" if s.subject == me else names.get(s.subject, s.subject)
    obj = "you" if s.object == me else names.get(s.object, s.object)
    hour = f" at {case.time_slots[s.time_slot - 1]}" if s.time_slot else ""
    match s.predicate:
        case "at":
            place = case.locations.get(s.object, s.object)
            return f"{who} {'were' if who == 'you' else 'was'} in {place}{hour}"
        case "has":
            return f"{who} {'have' if who == 'you' else 'has'} {case.items.get(s.object, s.object)}"
        case "saw":
            return f"{who} saw {obj}{hour}"
        case "heard":
            return f"{who} heard {obj}{hour}"
        case "owes":
            return f"{who} {'owe' if who == 'you' else 'owes'} {obj} money"


def _player_line(
    view: SuspectView, question: str, shown: Collection[Id], documents: Sequence[str]
) -> str:
    clues = [c for c in view.shown if c.id in shown]
    evidence = " ".join(SUSPECT.render("evidence", description=c.description) for c in clues)
    return "\n".join([*([evidence] if evidence else []), *documents, question])


def rewrite_request(feedback: str) -> str:
    return REWRITE.render("request", feedback=feedback)


def _print_report(report: TurnReport, elapsed_ms: int) -> None:
    for i, a in enumerate(report.attempts, start=1):
        print(f"attempt {i}: {a.draft}")
        for c in a.checks:
            print(f"  {c.verdict.name:<16} {c.claim.render():<32} {c.ref or '-':<20} {c.reason}")
        if not a.checks:
            print("  (no claims)")
    print(f"reply: {report.reply}")
    print(f"rewrites: {report.rewrites}  fallback: {report.fell_back}  turn: {report.turn}")
    print("ledger:")
    for e in report.ledger:
        print(f"  {e.lie.id:<24} {e.status.value:<9} turn {e.turn}")
    if not report.ledger:
        print("  (empty)")
    print(f"elapsed_ms: {elapsed_ms}")


async def _main(args: argparse.Namespace) -> int:
    case = Case.model_validate_json(args.case.read_text())
    game_id = uuid.uuid4().hex
    print(f"game: {game_id}")
    started = time.monotonic()
    report = await Interview(case, game_id).ask(args.suspect, args.ask, args.present)
    _print_report(report, round((time.monotonic() - started) * 1000))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agents.suspect")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--suspect", required=True)
    parser.add_argument("--ask", required=True)
    parser.add_argument("--present", action="append", default=[], help="clue id; repeatable")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
