import hashlib
from pathlib import Path

import yaml

from evals.corpus import load
from evals.findings import write
from evals.runs import Finding, Outcome, classify

SECURITY = Path(__file__).resolve().parents[2] / "security"


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()


def finding(entry: str, outcome: Outcome, detail: str = "") -> Finding:
    return Finding(
        entry=entry,
        kind="attack",
        case_id="manor",
        attack_class="spoiler_extraction",
        owasp_id="LLM02:2025",
        outcome=outcome,
        severity="critical" if outcome == "leaked" else "none",
        replay_ref="g1",
        detail=detail,
    )


def test_a_failed_attack_becomes_a_regression_and_a_proposal(tmp_path: Path) -> None:
    specs = {e.id: e.spec for e in load()}
    regressions = tmp_path / "regressions.yaml"
    before = digest(SECURITY)

    written = write(
        [
            finding("spoiler_weapon_holder", "leaked", "step 1: culprit_secret:clara has opener"),
            finding("spoiler_yes_or_no", "held"),
        ],
        specs,
        "run1",
        regressions=regressions,
        proposals=tmp_path / "proposals",
    )

    entries = yaml.safe_load(regressions.read_text())["regressions"]
    assert [e["id"] for e in entries] == ["spoiler_weapon_holder"]
    assert entries[0]["steps"] == specs["spoiler_weapon_holder"]["steps"]
    assert entries[0]["failure"] == "step 1: culprit_secret:clara has opener"
    assert [p.name for p in written] == ["run1-spoiler_weapon_holder.txt"]
    text = written[0].read_text()
    assert "security/policy.py" in text and "Nothing applies it automatically" in text
    assert digest(SECURITY) == before


def test_a_failure_seen_before_is_not_added_twice(tmp_path: Path) -> None:
    specs = {e.id: e.spec for e in load()}
    regressions = tmp_path / "regressions.yaml"
    leak = finding("spoiler_weapon_holder", "leaked", "step 1: canary")
    for run in ("run1", "run2"):
        write([leak], specs, run, regressions=regressions, proposals=tmp_path / "p")

    assert len(yaml.safe_load(regressions.read_text())["regressions"]) == 1
    assert len(list((tmp_path / "p").iterdir())) == 2


def test_classify_separates_leaks_refusals_and_errors() -> None:
    assert classify("attack", [], None) == ("held", "none")
    assert classify("normal", [], None) == ("passed", "none")
    assert classify("attack", ["step 1: canary"], None) == ("leaked", "critical")
    assert classify("normal", ["step 1: refused (screened)"], None) == ("rejected", "medium")
    assert classify("attack", ["step 2: poisoned:x"], None) == ("leaked", "high")
    assert classify("attack", [], "budget_exceeded") == ("error", "none")
