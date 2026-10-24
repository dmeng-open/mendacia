import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.catalog import Catalog, load_cases, publish
from app.config import Settings
from app.db import sync_engine
from engine.evidence import lint_case
from engine.generator import (
    OUT,
    THEMES,
    Accepted,
    Brief,
    Discarded,
    generate_with_repair,
    record_gate,
    write_case,
)
from engine.schema import Case, DanglingReferences, Id
from engine.solver import (
    Ambiguous,
    CheckReport,
    Conflict,
    Consistent,
    Counterexample,
    DropLeavesNoModel,
    Necessary,
    NecessitySkipped,
    NoCulprit,
    Redundant,
    Unique,
    WrongCulprit,
    check_case,
)
from evals.generation_report import batch_spend, build, gate_prefix, write
from evals.security_regress import case_attacks, run_suite
from evidence.index import index_case

RESERVE_USD = 1.3


def load_case(path: Path) -> Case:
    return Case.model_validate_json(path.read_text())


def _problems(error: ValidationError) -> list[str]:
    problems: list[str] = []
    for e in error.errors():
        cause = e.get("ctx", {}).get("error")
        if isinstance(cause, DanglingReferences):
            problems += cause.problems
        else:
            path = ".".join(str(part) for part in e["loc"]) or "<root>"
            problems.append(f"{path}: {e['msg']}")
    return problems


def validate(paths: list[Path]) -> int:
    failed = False
    for path in paths:
        try:
            load_case(path)
        except ValidationError as error:
            failed = True
            print(f"FAIL {path}")
            for problem in _problems(error):
                print(f"  {problem}")
        else:
            print(f"OK {path}")
    return 1 if failed else 0


def lint_evidence(paths: list[Path]) -> int:
    failed = False
    print(f"{'case':<16}{'docs':>5}{'key':>5}{'locked':>8}  status")
    for path in paths:
        try:
            lint = lint_case(load_case(path))
        except ValidationError as error:
            failed = True
            print(f"{path.stem:<16}{'':>18}  FAIL")
            for problem in _problems(error):
                print(f"  {problem}")
            continue
        failed |= bool(lint.problems)
        status = "FAIL" if lint.problems else "OK"
        print(f"{lint.case_id:<16}{lint.docs:>5}{lint.key:>5}{lint.locked:>8}  {status}")
        for problem in lint.problems:
            print(f"  {problem}")
    return 1 if failed else 0


def _counterexample(cx: Counterexample) -> str:
    return (
        f"  counterexample culprit={cx.culprit} breaks={','.join(cx.breaks) or '-'} "
        f"holds={','.join(cx.holds) or '-'}"
    )


def render_report(report: CheckReport, expected: str) -> list[str]:
    lines: list[str] = []
    match report.consistency:
        case Consistent():
            lines.append("consistency PASS")
        case Conflict(fact_ids, with_culprit):
            suffix = f" with culprit={expected}" if with_culprit else ""
            lines.append(f"consistency FAIL facts={','.join(fact_ids)}{suffix}")
    match report.uniqueness:
        case Unique(culprit):
            lines.append(f"uniqueness PASS culprit={culprit}")
        case Ambiguous(culprits, cx):
            lines += [f"uniqueness FAIL culprits={','.join(culprits)}", _counterexample(cx)]
        case WrongCulprit(culprits, cx):
            lines += [
                f"uniqueness FAIL culprits={','.join(culprits)} expected={expected}",
                _counterexample(cx),
            ]
        case NoCulprit():
            lines.append("uniqueness FAIL no culprit: the clues rule out every suspect")
    match report.sufficiency:
        case Unique(culprit):
            lines.append(f"sufficiency PASS chain alone proves culprit={culprit}")
        case Ambiguous(culprits, cx) | WrongCulprit(culprits, cx):
            lines += [
                f"sufficiency FAIL chain alone allows {','.join(culprits)}",
                _counterexample(cx),
            ]
        case NoCulprit():
            lines.append("sufficiency FAIL no culprit")
    match report.necessity:
        case NecessitySkipped():
            lines.append("necessity SKIP uniqueness failed")
        case verdicts:
            needed = sum(isinstance(v, Necessary) for v in verdicts)
            status = "PASS" if needed == len(verdicts) else "FAIL"
            lines.append(f"necessity {status} {needed}/{len(verdicts)} chain clues")
            for v in verdicts:
                match v:
                    case Redundant(clue_id):
                        lines.append(f"  {clue_id}: redundant, the culprit stays unique without it")
                    case DropLeavesNoModel(clue_id):
                        lines.append(f"  {clue_id}: dropping it leaves no model")
    exposed = sum(lie.exposed for lie in report.lies)
    warn = any(
        not lie.exposed or lie.true_in_case or not lie.denies_hidden_fact for lie in report.lies
    )
    lines.append(f"lies {'WARN' if warn else 'PASS'} {exposed}/{len(report.lies)} exposed")
    for lie in report.lies:
        if not lie.exposed:
            lines.append(f"  {lie.lie_id}: no clue exposes it")
        if lie.true_in_case:
            lines.append(f"  {lie.lie_id}: the case facts allow the claim to be true")
        if not lie.denies_hidden_fact:
            lines.append(f"  {lie.lie_id}: the claim does not contradict the fact it hides")
    return lines


def check(path: Path) -> int:
    try:
        case = load_case(path)
    except ValidationError as error:
        print(f"FAIL {path}")
        for problem in _problems(error):
            print(f"  {problem}")
        return 1
    report = check_case(case)
    print("\n".join(render_report(report, case.culprit)))
    return 0 if report.passed else 1


def unique(case: Case, taken: Catalog) -> Case:
    if case.id not in taken:
        return case
    n = 2
    while f"{case.id}_{n}" in taken:
        n += 1
    return case.model_copy(update={"id": Id(f"{case.id}_{n}")})


def generate(n: int, out: Path = OUT) -> int:
    settings = Settings()
    cap = settings.eval_max_usd
    engine = sync_engine(settings.database_url)
    catalog = Catalog(load_cases(), engine)
    batch_id = uuid4().hex[:12]
    print(f"batch {batch_id}: {n} cases, cap ${cap:.2f}")
    for i in range(n):
        spent = batch_spend(batch_id)
        if spent + RESERVE_USD > cap:
            print(f"stopped before case {i + 1}: ${spent:.4f} spent, one more could pass the cap")
            break
        result = generate_with_repair(Brief(THEMES[i % len(THEMES)]), batch_id=batch_id)
        match result:
            case Discarded(generation_id, reason, rounds):
                print(f"case {i + 1}: discarded ({reason}) after {len(rounds)} rounds")
            case Accepted(generation_id, accepted, rounds):
                case = unique(accepted, catalog)
                prefix = f"{gate_prefix(batch_id)}{generation_id[:8]}"
                left = cap - batch_spend(batch_id)
                suite = asyncio.run(run_suite(case, case_attacks(case), left, prefix))
                if not suite.passed:
                    record_gate(generation_id, "security_rejected", ",".join(suite.failed), case)
                    print(f"case {i + 1}: {case.id} security-rejected ({', '.join(suite.failed)})")
                    continue
                index_case(case, engine)
                with engine.begin() as conn:
                    publish(conn, case, generation_id)
                path = write_case(case, out)
                record_gate(generation_id, "passed", None, case)
                print(f"case {i + 1}: {case.id} accepted after {len(rounds)} rounds, wrote {path}")
    report = build(batch_id)
    print(f"wrote {write(report)}, batch cost ${report.cost_usd:.4f}")
    print(report.summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate", help="parse cases and check every reference")
    validate_cmd.add_argument("paths", nargs="+", type=Path)
    check_cmd = commands.add_parser("check", help="prove the case has exactly one culprit")
    check_cmd.add_argument("path", type=Path)
    lint_cmd = commands.add_parser("lint-evidence", help="lint each case's evidence archive")
    lint_cmd.add_argument("paths", nargs="+", type=Path)
    generate_cmd = commands.add_parser("generate", help="generate, gate, and publish new cases")
    generate_cmd.add_argument("--n", type=int, default=1)
    generate_cmd.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if args.command == "generate":
        return generate(args.n, args.out)
    if args.command == "check":
        return check(args.path)
    if args.command == "lint-evidence":
        return lint_evidence(args.paths)
    return validate(args.paths)


if __name__ == "__main__":
    sys.exit(main())
