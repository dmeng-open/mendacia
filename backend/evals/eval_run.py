"""`make eval N=<n>`: the attack corpus and the gameplay set through promptfoo, the retrieval eval,
n simulated games, then the report. One run id tags every model call, and the whole run stays
under EVAL_MAX_USD."""

import argparse
import os
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from app.config import Settings
from evals import findings, report, runs
from evals.corpus import load
from sim.runner import HAND_WRITTEN, render, run_games

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
PROMPTFOO = "promptfoo@0.124.1"
PROJECT_GAMES = 100


def corpus(run_id: str, max_usd: float, out: Path) -> None:
    env = {
        **os.environ,
        "EVAL_RUN_ID": run_id,
        "EVAL_MAX_USD": str(max_usd),
        "PROMPTFOO_PYTHON": sys.executable,
        "PYTHONPATH": str(BACKEND),
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "PROMPTFOO_CACHE_ENABLED": "false",
    }
    subprocess.run(
        ["npx", "-y", PROMPTFOO, "eval", "-c", "promptfooconfig.yaml", "-o", str(out)],
        cwd=BACKEND / "evals",
        env=env,
        check=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.eval_run")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args(argv)
    max_usd = Settings().eval_max_usd
    run_id = f"eval-{uuid.uuid4().hex[:10]}"
    runs.start(run_id, max_usd, args.n)
    print(f"eval run {run_id}: corpus, gameplay set, retrieval, {args.n} games, cap ${max_usd:g}")

    out = ROOT / "reports" / "promptfoo.json"
    corpus(run_id, max_usd, out)
    entries = load()
    found = runs.findings_from(out, {e.id: e.spec["case"] for e in entries})
    runs.record(run_id, found)
    proposals = findings.write(found, {e.id: e.spec for e in entries}, run_id)
    print(f"corpus: {len(found)} entries, {len(proposals)} proposals")

    subprocess.run(["make", "-C", str(ROOT), "retrieval-eval"], check=True)
    corpus_usd = runs.spent(run_id)
    budget = max(max_usd - corpus_usd, 0.0)
    sim = run_games(args.n, args.concurrency, budget, cases=args.case or HAND_WRITTEN)
    print("\n".join(render(sim)))

    runs.finish(run_id, sim.status, sim.run_id)
    built = report.build(run_id)
    print(f"wrote {report.write(built)}")
    per_game = sum(g.cost_usd for g in sim.games) / max(len(sim.games), 1)
    projected = runs.spent(run_id) + per_game * PROJECT_GAMES
    print(
        f"projected {PROJECT_GAMES}-game run: ${projected:.2f} against a ${max_usd:g} cap"
        + ("; over the cap, write it to docs/QUESTIONS.md" if projected > max_usd else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
