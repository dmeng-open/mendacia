import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from engine.schema import Case, DanglingReferences
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
        case WrongCulprit(cx):
            lines += [
                f"uniqueness FAIL culprit={cx.culprit} expected={expected}",
                _counterexample(cx),
            ]
        case NoCulprit():
            lines.append("uniqueness FAIL no culprit: the clues rule out every suspect")
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
    warn = any(not lie.exposed or lie.true_in_case for lie in report.lies)
    lines.append(f"lies {'WARN' if warn else 'PASS'} {exposed}/{len(report.lies)} exposed")
    for lie in report.lies:
        if not lie.exposed:
            lines.append(f"  {lie.lie_id}: no clue exposes it")
        if lie.true_in_case:
            lines.append(f"  {lie.lie_id}: the case facts allow the claim to be true")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate", help="parse cases and check every reference")
    validate_cmd.add_argument("paths", nargs="+", type=Path)
    check_cmd = commands.add_parser("check", help="prove the case has exactly one culprit")
    check_cmd.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.path)
    return validate(args.paths)


if __name__ == "__main__":
    sys.exit(main())
