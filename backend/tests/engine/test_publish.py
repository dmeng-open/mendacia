import json
from pathlib import Path

import pytest

from engine.publish import Checks, gates, record
from engine.schema import Case
from evals.security_regress import Outcome, Suite

CASES = Path(__file__).resolve().parents[3] / "cases"
MANOR_PATH = CASES / "manor.json"
MANOR = Case.model_validate_json(MANOR_PATH.read_text())
HELD = Outcome("attack", "probe", "direct_injection", True, "held")


def checks(
    inventory: list[str] | None = None,
    outcomes: tuple[Outcome, ...] = (HELD,),
    canary: int = 0,
) -> Checks:
    return Checks(
        inventory=lambda: inventory or [],
        migrations_at_head=lambda: True,
        suite=lambda _: Suite(outcomes, canary, 0.0),
    )


def blocked(case: Case, c: Checks, tmp_path: Path) -> dict[str, object]:
    written = record(case, MANOR_PATH, gates(case, MANOR_PATH, c), out=tmp_path)
    entry: dict[str, object] = json.loads(written.read_text())
    return entry


def test_a_clean_case_passes_all_four_gates(tmp_path: Path) -> None:
    results = gates(MANOR, MANOR_PATH, checks())
    assert [(g.name, g.passed) for g in results] == [
        ("code", True),
        ("logic", True),
        ("agent", True),
        ("content", True),
    ]
    assert blocked(MANOR, checks(), tmp_path)["status"] == "published"


@pytest.mark.parametrize(
    ("case", "c", "reason"),
    [
        (
            MANOR.model_copy(update={"culprit": "hobbs"}),
            checks(),
            "the case has no unique solution",
        ),
        (
            MANOR,
            checks(["evals.x: attack_runner reads the truth layer outside its manifest"]),
            "the regression set can read Truth",
        ),
        (
            MANOR,
            checks(["app.x: tool 'open_document' belongs to no agent"]),
            "a tool bypasses authorization",
        ),
        (
            MANOR,
            checks(outcomes=(Outcome("attack", "a", "spoiler", False, "leak culprit:x"),)),
            "a player gets the solution early",
        ),
        (
            MANOR,
            checks(outcomes=(Outcome("attack", "a", "direct", False, "leak prompt:What you"),)),
            "a failed verification still releases text",
        ),
        (MANOR, checks(canary=1), "the canary leaks"),
        (
            MANOR,
            checks(outcomes=(Outcome("normal", "n", "normal", False, "screened (x)"),)),
            "normal confrontations are blocked",
        ),
    ],
    ids=["unique", "truth", "tool", "spoiler", "release", "canary", "false_reject"],
)
def test_each_p0_blocker_blocks_with_its_reason(
    case: Case, c: Checks, reason: str, tmp_path: Path
) -> None:
    entry = blocked(case, c, tmp_path)
    assert entry["status"] == "blocked_with_reason"
    assert str(entry["reason"]).startswith(reason)
    assert entry["reproduction"] == f"make publish CASE={MANOR_PATH}"


def test_a_generated_case_needs_a_human_review(tmp_path: Path) -> None:
    elsewhere = tmp_path / "manor.json"
    content = next(g for g in gates(MANOR, elsewhere, checks()) if g.name == "content")
    assert content.blockers == (
        "no human sample review: hand-written cases only, or review it first",
    )
