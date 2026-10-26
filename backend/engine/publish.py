"""`make publish CASE=<path>`: the four release gates and the P0 blockers of docs/spec.md §8.3.
A case that fails is not published: the last verified case stays live, and the reason and its
reproduction are written to reports/publish/<case id>.json."""

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory

from agents.game_master import QUESTIONS
from agents.inventory import problems, scan_module, sources
from app.catalog import CASES_DIR, publish
from app.config import Settings
from app.db import sync_engine
from engine.evidence import lint_case, obtainable
from engine.schema import Case
from engine.solver import check_case
from evals.security_regress import BASELINE, Suite, case_attacks, run_suite

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND.parent / "reports" / "publish"
SPOILER_MARKS = ("culprit:", "names:", "spent_lie:")
RELEASE_MARKS = ("prompt:", "narration")


@dataclass(frozen=True)
class Gate:
    name: str
    blockers: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class Checks:
    """What the gates read from outside the case. Tests replace these."""

    inventory: Callable[[], list[str]]
    migrations_at_head: Callable[[], bool]
    suite: Callable[[Case], Suite]
    reviewed: Callable[[Path], bool] = field(default=lambda p: p.parent == CASES_DIR)


def inventory_problems() -> list[str]:
    return problems([scan_module(m, s) for m, s in sources()])


def migrations_at_head() -> bool:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    with sync_engine(Settings().database_url).connect() as conn:
        current = conn.scalar(sa.text("select version_num from alembic_version"))
    return bool(current == script.get_current_head())


def security_suite(case: Case) -> Suite:
    baseline = yaml.safe_load(BASELINE.read_text())
    spec = baseline if baseline["case"] == f"{case.id}.json" else case_attacks(case)
    return asyncio.run(run_suite(case, spec, 1.0, f"publish-{uuid.uuid4().hex[:8]}"))


DEFAULT = Checks(inventory_problems, migrations_at_head, security_suite)


def code_gate(checks: Checks) -> Gate:
    found = checks.inventory()
    blockers = [f"a tool bypasses authorization: {p}" for p in found if "tool" in p or "model" in p]
    blockers += [f"the regression set can read Truth: {p}" for p in found if "truth" in p]
    blockers += [f"agent inventory: {p}" for p in found if not any(p in b for b in blockers)]
    if not checks.migrations_at_head():
        blockers.append("migrations are not at head")
    return Gate("code", tuple(blockers))


def logic_gate(case: Case) -> Gate:
    report = check_case(case)
    blockers = [] if report.passed else ["the case has no unique solution"]
    structure = [f.message for f in lint_case(case).findings if f.kind == "structure"]
    blockers += [f"evidence provenance: {m}" for m in structure]
    notes = [f"lie {lie.lie_id} has no exposing clue" for lie in report.lies if not lie.exposed]
    return Gate("logic", tuple(blockers), tuple(notes))


def agent_gate(case: Case, checks: Checks) -> Gate:
    suite = checks.suite(case)
    blockers: list[str] = []
    for o in suite.outcomes:
        if o.ok:
            continue
        if o.kind == "normal":
            blockers.append(f"normal confrontations are blocked: {o.id} ({o.detail})")
        elif any(m in o.detail for m in SPOILER_MARKS):
            blockers.append(f"a player gets the solution early: {o.id} ({o.detail})")
        elif any(m in o.detail for m in RELEASE_MARKS):
            blockers.append(f"a failed verification still releases text: {o.id} ({o.detail})")
        else:
            blockers.append(f"attack did not hold: {o.id} ({o.detail})")
    if suite.canary:
        blockers.append(f"the canary leaks: {suite.canary} rows")
    return Gate("agent", tuple(blockers))


def content_gate(case: Case, path: Path, checks: Checks) -> Gate:
    blockers: list[str] = []
    reachable = obtainable(case)
    blockers += [
        f"unplayable: solution_chain clue {c} cannot be found"
        for c in case.solution_chain
        if c not in reachable
    ]
    if len(case.solution_chain) > QUESTIONS:
        chain = len(case.solution_chain)
        blockers.append(f"too hard: {chain} chain clues for {QUESTIONS} questions")
    text = [f.message for f in lint_case(case).findings if f.kind != "structure"]
    blockers += [f"content limits: {m}" for m in text]
    if not checks.reviewed(path):
        blockers.append("no human sample review: hand-written cases only, or review it first")
    notes = ("spoiler-free share check: no share cards exist yet (roadmap stage D)",)
    return Gate("content", tuple(blockers), notes)


def gates(case: Case, path: Path, checks: Checks = DEFAULT) -> list[Gate]:
    return [
        code_gate(checks),
        logic_gate(case),
        agent_gate(case, checks),
        content_gate(case, path, checks),
    ]


def record(case: Case, path: Path, results: Sequence[Gate], out: Path = OUT) -> Path:
    blocked = [b for g in results for b in g.blockers]
    entry: dict[str, Any] = {
        "case": case.id,
        "path": str(path),
        "status": "blocked_with_reason" if blocked else "published",
        "gates": {g.name: {"passed": g.passed, "blockers": list(g.blockers)} for g in results},
    }
    if blocked:
        entry["reason"] = blocked[0]
        entry["reproduction"] = f"make publish CASE={path}"
    out.mkdir(parents=True, exist_ok=True)
    written = out / f"{case.id}.json"
    written.write_text(json.dumps(entry, indent=2) + "\n")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.publish")
    parser.add_argument("case", type=Path)
    args = parser.parse_args(argv)
    case = Case.model_validate_json(args.case.read_text())
    results = gates(case, args.case.resolve())
    for g in results:
        print(f"{g.name:<8} {'PASS' if g.passed else 'FAIL'}")
        for b in g.blockers:
            print(f"  {b}")
        for n in g.notes:
            print(f"  note: {n}")
    written = record(case, args.case, results)
    if all(g.passed for g in results):
        if args.case.resolve().parent != CASES_DIR:
            with sync_engine(Settings().database_url).begin() as conn:
                publish(conn, case)
        print(f"published {case.id}; wrote {written}")
        return 0
    print(f"blocked_with_reason; the last verified case stays live; wrote {written}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
