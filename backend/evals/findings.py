"""Turn each failed attack into a minimal reproduction and a proposed patch. Nothing here edits
code: a person reviews each proposal and lands it in a normal PR."""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from evals.runs import Finding

ROOT = Path(__file__).resolve().parents[2]
REGRESSIONS = Path(__file__).parent / "attacks" / "regressions.yaml"
PROPOSALS = ROOT / "reports" / "proposals"

FIX_IN = {
    "direct_injection": "agents/screening.py (a screening rule for this phrasing)",
    "role_spoofing": "agents/screening.py (a screening rule for this claimed authority)",
    "false_positive": "agents/screening.py (narrow the rule that refused legitimate play)",
    "spoiler_extraction": "security/policy.py or agents/verifier.py (the grant or block rule "
    "that let the culprit fact through)",
    "indirect_injection": "engine/evidence.py (a lint rule) and agents/documents.py (how "
    "presented document text is quoted)",
    "tool_misuse": "security/tool_broker.py (the argument check or actor rule that allowed it)",
    "cross_session": "app/session.py or app/routes/games.py (the ownership check)",
    "ledger_replay": "agents/ledger.py or app/games.py (the state or idempotency check)",
    "normal": "agents/screening.py or agents/verifier.py (the rule that refused legitimate play)",
}


def reproduction(spec: Mapping[str, Any], finding: Finding, run_id: str) -> dict[str, Any]:
    return {
        **{k: spec[k] for k in ("id", "class", "owasp", "case", "steps") if k in spec},
        "found_in": run_id,
        "failure": finding.detail,
        "replay_ref": finding.replay_ref,
    }


def proposal(spec: Mapping[str, Any], finding: Finding, run_id: str) -> str:
    asks = [s["ask"] for s in spec.get("steps", []) if "ask" in s]
    return "\n".join(
        [
            f"Proposed fix for {finding.entry} ({finding.attack_class}, {finding.owasp_id}), "
            f"found in eval run {run_id}.",
            "",
            f"Failure: {finding.detail}",
            f"Severity: {finding.severity}. Replay: {finding.replay_ref or '-'}",
            "",
            "Player input:",
            *(f"  - {a}" for a in asks),
            "",
            f"Where to fix: {FIX_IN[finding.attack_class]}.",
            "Add the reproduction from evals/attacks/regressions.yaml to the regression test of "
            "that module, change the rule, and show the attack holding in the PR description.",
            "This file is a proposal. Nothing applies it automatically.",
            "",
        ]
    )


def write(
    findings: Iterable[Finding],
    specs: Mapping[str, Mapping[str, Any]],
    run_id: str,
    regressions: Path = REGRESSIONS,
    proposals: Path = PROPOSALS,
) -> list[Path]:
    """Append each new failing entry to `regressions` and write one proposal per failure."""
    failed = [f for f in findings if f.outcome in ("leaked", "rejected")]
    known = yaml.safe_load(regressions.read_text()) if regressions.exists() else None
    entries: list[dict[str, Any]] = list((known or {}).get("regressions", []))
    seen = {e["id"] for e in entries}
    written: list[Path] = []
    for f in failed:
        spec = specs[f.entry]
        if f.entry not in seen:
            entries.append(reproduction(spec, f, run_id))
            seen.add(f.entry)
        proposals.mkdir(parents=True, exist_ok=True)
        path = proposals / f"{run_id}-{f.entry}.txt"
        path.write_text(proposal(spec, f, run_id))
        written.append(path)
    if failed:
        regressions.write_text(yaml.safe_dump({"regressions": entries}, sort_keys=False))
    return written
