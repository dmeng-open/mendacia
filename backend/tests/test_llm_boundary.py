import ast
import re
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
LITELLM_HOME = BACKEND / "app" / "llm.py"
MODEL_NAME = re.compile(
    "|".join(re.escape(p + "-") for p in ("gpt", "claude", "gemini", "text-embedding"))
)


def _scanned_files() -> list[Path]:
    files = [
        p
        for d in ("agents", "app", "engine", "evals", "migrations", "security", "tests")
        for p in (BACKEND / d).rglob("*.py")
        if ".venv" not in p.parts and "fixtures" not in p.parts
    ]
    files += [ROOT / "Makefile", ROOT / "docker-compose.yml", BACKEND / "Dockerfile"]
    files += [p for p in (ROOT / "frontend" / "src").rglob("*") if p.is_file()]
    return [p for p in files if p.is_file()]


def _imports_litellm(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import) and any(
            a.name.split(".")[0] == "litellm" for a in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "litellm":
            return True
    return False


def violations() -> list[str]:
    found = []
    for path in _scanned_files():
        rel = path.relative_to(ROOT)
        if path.suffix == ".py" and path != LITELLM_HOME and _imports_litellm(path):
            found.append(f"{rel}: imports litellm; call app.llm instead")
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if MODEL_NAME.search(line):
                found.append(
                    f"{rel}:{number}: model name literal; "
                    "configure MODEL_* and call app.llm instead"
                )
    return found


def test_tree_has_no_violations() -> None:
    assert violations() == []


def test_seeded_litellm_import_is_caught_then_cleared() -> None:
    seeded = BACKEND / "app" / f"_seeded_{uuid.uuid4().hex}.py"
    seeded.write_text("import litellm\n")
    try:
        assert violations() == [
            f"{seeded.relative_to(ROOT)}: imports litellm; call app.llm instead"
        ]
    finally:
        seeded.unlink()
    assert violations() == []
