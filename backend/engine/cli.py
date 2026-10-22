import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from engine.schema import Case, DanglingReferences


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate", help="parse cases and check every reference")
    validate_cmd.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    return validate(args.paths)


if __name__ == "__main__":
    sys.exit(main())
