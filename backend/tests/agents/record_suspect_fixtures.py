import asyncio
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

from agents.suspect import Interview
from app import llm_replay
from app.config import Settings
from app.llm_replay import LlmMode, Recording
from tests.agents.suspect_scenarios import CHOSEN, MANOR, SCENARIOS, Scenario, Script, dump, play

FIXTURES = llm_replay.FIXTURES_DIR
SAMPLES = int(os.environ.get("RECORD_SAMPLES", "3"))


def _spent(staging: Path, known: set[str]) -> float:
    new = (f for f in staging.glob("*.json") if f.name not in known)
    return sum(Recording.model_validate_json(f.read_text()).cost_usd for f in new)


def _promote(staging: Path, known: set[str], name: str, script: Script) -> None:
    for f in staging.glob("*.json"):
        if f.name not in known:
            shutil.copy(f, FIXTURES / f.name)
    chosen = json.loads(CHOSEN.read_text()) if CHOSEN.exists() else {}
    chosen[name] = dump(script)
    CHOSEN.write_text(json.dumps(chosen, indent=2, sort_keys=True) + "\n")


async def _record(scenario: Scenario, root: Path, budget: float) -> tuple[int, float]:
    spent = 0.0
    for i, script in enumerate(scenario.candidates):
        for k in range(SAMPLES):
            staging = root / scenario.name / f"{i}-{k}"
            shutil.copytree(FIXTURES, staging)
            known = {f.name for f in staging.glob("*.json")}
            llm_replay.FIXTURES_DIR = staging
            room = Interview(MANOR, f"record-{uuid.uuid4().hex[:8]}")
            reports = await play(room, scenario.suspect, script)
            spent += _spent(staging, known)
            matched = scenario.expect(reports)
            for r in reports:
                for a in r.attempts:
                    print(f"  [{i}.{k}] {a.draft!r}")
                    for line in a.feedback.splitlines():
                        print(f"      {line}")
            print(f"{scenario.name} candidate {i} sample {k}: {'MATCH' if matched else '-'}")
            if matched:
                _promote(staging, known, scenario.name, script)
                return i, spent
            if spent > budget:
                raise SystemExit(f"{scenario.name}: budget spent (${spent:.4f})")
    raise SystemExit(f"{scenario.name}: no candidate matched (spent ${spent:.4f})")


async def _main(names: list[str]) -> None:
    if Settings().llm_mode is not LlmMode.RECORD:
        raise SystemExit("set LLM_MODE=record")
    budget = float(os.environ.get("RECORD_MAX_USD", "0.5"))
    total = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for name in names or list(SCENARIOS):
            _, spent = await _record(SCENARIOS[name], Path(tmp), budget - total)
            total += spent
    print(f"total spend ${total:.4f}")


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
