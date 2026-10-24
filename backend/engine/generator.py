import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.config import Settings
from app.db import sync_engine
from app.llm import LLM_CALLS, ModelRole, complete
from engine.draft import (
    PROMPT,
    Archive,
    Budget,
    CaseDraft,
    Message,
    OverBudget,
    SchemaRejected,
    ask,
    data_block,
    documents_parser,
    parse_core,
)
from engine.evidence import Lint, lint_case
from engine.repair import repair_case, repair_instructions
from engine.schema import Case
from engine.solver import check_case
from security.context import case_version

CORE_MAX_TOKENS = 16000
DOCUMENTS_MAX_TOKENS = 12000
BUDGET_USD = 0.70
BUDGET_S = 280
OUT = Path(__file__).resolve().parents[2] / "cases" / "generated"
THEMES = (
    "a snowbound mountain observatory during a meteor shower",
    "a riverboat casino on its last night before the season closes",
    "a village bakery the morning of the harvest fair",
    "a museum of clocks after the annual winding ceremony",
    "a seaside boarding school on the night of the spring play",
)

METADATA = sa.MetaData()
GENERATION_LOG = sa.Table(
    "generation_log",
    METADATA,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("brief", JSONB),
    sa.Column("outcome", sa.Text),
    sa.Column("failure_reason", sa.Text),
    sa.Column("rounds", sa.Integer),
    sa.Column("round_log", JSONB),
    sa.Column("cost_usd", sa.Double),
    sa.Column("models", JSONB),
    sa.Column("prompt_version", sa.Text),
    sa.Column("case_id", sa.Text),
    sa.Column("case_version", sa.Text),
)

Verdict = Literal["passed", "schema_rejected", "core_rejected", "documents_rejected"]


@dataclass(frozen=True)
class Brief:
    theme: str
    suspects: int = 4


@dataclass(frozen=True)
class Fresh:
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Repair:
    draft: Case
    instructions: str


@dataclass(frozen=True)
class Documents:
    core: Case
    avoid: tuple[str, ...] = ()


Step = Fresh | Repair | Documents


@dataclass(frozen=True)
class Round:
    n: int
    step: Literal["generate", "repair", "documents"]
    verdict: Verdict
    notes: tuple[str, ...]
    elapsed_ms: int


@dataclass(frozen=True)
class Accepted:
    generation_id: str
    case: Case
    rounds: tuple[Round, ...]


@dataclass(frozen=True)
class Discarded:
    generation_id: str
    reason: Literal["max_rounds", "budget"]
    rounds: tuple[Round, ...]


GenerationResult = Accepted | Discarded


def _bullets(lines: tuple[str, ...]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _system() -> Message:
    return {"role": "system", "content": PROMPT.render("system")}


def generate_case(
    brief: Brief, *, notes: tuple[str, ...] = (), budget: Budget
) -> Case | SchemaRejected:
    """First call: the case without documents; placeholders stand in for the cited ones."""

    def send(messages: list[Message]) -> str:
        return complete(
            ModelRole.STRONG,
            messages,
            response_format=CaseDraft,
            purpose="generate",
            max_tokens=CORE_MAX_TOKENS,
            prompt_version=PROMPT.version,
            run_id=budget.run_id,
            timeout=budget.timeout(),
        ).text

    user = PROMPT.render("core", theme=brief.theme, suspects=brief.suspects)
    if notes:
        user += "\n\n" + PROMPT.render("rejected", problems=_bullets(notes))
    return ask(send, parse_core, [_system(), {"role": "user", "content": user}], "core")


def write_documents(
    core: Case, *, avoid: tuple[str, ...] = (), budget: Budget
) -> Case | SchemaRejected:
    """Second call: the 15 to 20 evidence documents, with source and visibility."""

    def send(messages: list[Message]) -> str:
        return complete(
            ModelRole.STRONG,
            messages,
            response_format=Archive,
            purpose="generate",
            max_tokens=DOCUMENTS_MAX_TOKENS,
            prompt_version=PROMPT.version,
            run_id=budget.run_id,
            timeout=budget.timeout(),
        ).text

    avoid_text = PROMPT.render("rejected", problems=_bullets(avoid)) if avoid else ""
    user = PROMPT.render("documents", avoid=avoid_text, draft=data_block(core))
    messages = [_system(), {"role": "user", "content": user}]
    return ask(send, documents_parser(core), messages, "documents")


def _unsafe(lint: Lint) -> tuple[str, ...]:
    """Hints for text that must not be echoed; an unsafe id hides every hint that names ids."""
    bad_ids = tuple(f.hint for f in lint.findings if f.kind == "id")
    return bad_ids or tuple(f.hint for f in lint.findings if f.kind == "text")


def _judge_core(core: Case) -> tuple[Verdict, tuple[str, ...], Step | None]:
    flagged = _unsafe(lint_case(core))
    if flagged:
        return "core_rejected", flagged, Fresh(flagged)
    report = check_case(core)
    if report.passed:
        return "passed", (), None
    instructions = repair_instructions(report)
    notes = tuple(line.removeprefix("- ") for line in instructions.splitlines())
    return "core_rejected", notes, Repair(core, instructions)


def _documents(
    core: Case, avoid: tuple[str, ...], budget: Budget
) -> tuple[Verdict, tuple[str, ...], Step | Case]:
    case = write_documents(core, avoid=avoid, budget=budget)
    if isinstance(case, SchemaRejected):
        return "schema_rejected", case.errors, Documents(core, case.errors)
    lint = lint_case(case)
    hints = _unsafe(lint) or tuple(f.hint for f in lint.findings)
    if not check_case(case).passed:
        hints += ("the documents changed the solver result",)
    if hints:
        return "documents_rejected", hints, Documents(core, hints)
    return "passed", (), case


def _core_round(
    got: Case | SchemaRejected, retry: Step, budget: Budget
) -> tuple[Verdict, tuple[str, ...], Step | Case]:
    if isinstance(got, SchemaRejected):
        return "schema_rejected", got.errors, retry
    verdict, notes, nxt = _judge_core(got)
    if nxt is None:
        return _documents(got, (), budget)
    return verdict, notes, nxt


def run_round(brief: Brief, n: int, step: Step, *, budget: Budget) -> tuple[Round, Step | Case]:
    """One round: one core or documents attempt, gated by schema, lint, and the solver."""
    started = time.monotonic()
    name: Literal["generate", "repair", "documents"]
    match step:
        case Fresh(prior):
            name = "generate"
            got = generate_case(brief, notes=prior, budget=budget)
            retry = Fresh(got.errors) if isinstance(got, SchemaRejected) else step
            verdict, notes, nxt = _core_round(got, retry, budget)
        case Repair(draft, instructions):
            name = "repair"
            got = repair_case(draft, instructions, budget=budget)
            verdict, notes, nxt = _core_round(got, step, budget)
        case Documents(core, avoid):
            name = "documents"
            verdict, notes, nxt = _documents(core, avoid, budget)
    elapsed = round((time.monotonic() - started) * 1000)
    return Round(n, name, verdict, notes, elapsed), nxt


def _db() -> sa.Engine:
    return sync_engine(Settings().database_url)


def _start(generation_id: str, brief: Brief) -> None:
    with _db().begin() as conn:
        conn.execute(
            sa.insert(GENERATION_LOG).values(
                id=generation_id, brief=asdict(brief), prompt_version=PROMPT.version
            )
        )


def _record(generation_id: str, rnd: Round) -> None:
    entry = {**asdict(rnd), "notes": list(rnd.notes[:20])}
    with _db().begin() as conn:
        conn.execute(
            sa.update(GENERATION_LOG)
            .where(GENERATION_LOG.c.id == generation_id)
            .values(
                rounds=GENERATION_LOG.c.rounds + 1,
                round_log=GENERATION_LOG.c.round_log.op("||")(sa.cast([entry], JSONB)),
            )
        )


def spent_usd(generation_id: str) -> float:
    with _db().connect() as conn:
        total = conn.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(LLM_CALLS.c.cost_usd), 0.0)).where(
                LLM_CALLS.c.run_id == generation_id
            )
        )
    return float(total or 0.0)


def _finish(
    generation_id: str,
    outcome: Literal["accepted", "discarded", "crashed"],
    reason: str | None = None,
    case: Case | None = None,
) -> None:
    with _db().begin() as conn:
        models = conn.scalars(
            sa.select(LLM_CALLS.c.model)
            .where(LLM_CALLS.c.run_id == generation_id)
            .distinct()
            .order_by(LLM_CALLS.c.model)
        ).all()
        conn.execute(
            sa.update(GENERATION_LOG)
            .where(GENERATION_LOG.c.id == generation_id)
            .values(
                finished_at=sa.func.now(),
                outcome=outcome,
                failure_reason=reason,
                cost_usd=spent_usd(generation_id),
                models=list(models),
                case_id=case.id if case else None,
                case_version=case_version(case) if case else None,
            )
        )


def _reason(kind: str, rounds: list[Round]) -> str:
    if not rounds:
        return f"{kind}: before round 1"
    last = rounds[-1]
    detail = f": {last.notes[0]}" if last.notes else ""
    return f"{kind}: round {last.n} {last.step} {last.verdict}{detail}"


def generate_with_repair(brief: Brief, max_rounds: int = 5) -> GenerationResult:
    generation_id = uuid4().hex
    _start(generation_id, brief)
    budget = Budget(generation_id, BUDGET_USD, BUDGET_S, lambda: spent_usd(generation_id))
    rounds: list[Round] = []
    step: Step = Fresh()
    try:
        for n in range(1, max_rounds + 1):
            rnd, nxt = run_round(brief, n, step, budget=budget)
            rounds.append(rnd)
            _record(generation_id, rnd)
            if isinstance(nxt, Case):
                _finish(generation_id, "accepted", case=nxt)
                return Accepted(generation_id, nxt, tuple(rounds))
            step = nxt
    except OverBudget:
        _finish(generation_id, "discarded", _reason("budget", rounds))
        return Discarded(generation_id, "budget", tuple(rounds))
    except BaseException as error:
        _finish(generation_id, "crashed", type(error).__name__)
        raise
    _finish(generation_id, "discarded", _reason("max_rounds", rounds))
    return Discarded(generation_id, "max_rounds", tuple(rounds))


def write_case(case: Case, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{case.id}.json"
    path.write_text(json.dumps(case.model_dump(mode="json"), indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.generator")
    parser.add_argument("--once", action="store_true", required=True, help="run one generation")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--suspects", type=int, default=4)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    brief = Brief(args.theme or random.choice(THEMES), args.suspects)
    print(f"brief theme={brief.theme!r} suspects={brief.suspects}")
    result = generate_with_repair(brief)
    for r in result.rounds:
        print(f"round {r.n} {r.step:<9} {r.verdict:<18} {r.elapsed_ms / 1000:6.1f} s")
        for note in r.notes[:5]:
            print(f"  {note}")
    cost = spent_usd(result.generation_id)
    match result:
        case Accepted(generation_id, case, rounds):
            path = write_case(case, args.out)
            print(
                f"accepted case={case.id} rounds={len(rounds)} cost=${cost:.4f} id={generation_id}"
            )
            print(f"wrote {path}")
            return 0
        case Discarded(generation_id, reason, rounds):
            print(
                f"discarded reason={reason} rounds={len(rounds)} cost=${cost:.4f} "
                f"id={generation_id}"
            )
            return 1


if __name__ == "__main__":
    sys.exit(main())
