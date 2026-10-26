"""The P5-2 security and quality report. Every number is read from a table or a report file and
the definitions are in docs/adr/013-metric-definitions.md."""

import json
import statistics
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from agents.game_master import QUESTIONS
from agents.verifier import leaks_canary
from app.catalog import load_cases
from app.config import Settings
from app.db import sync_engine
from evals.runs import COMPONENTS, FINDINGS, RUNS

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
UNAUTHORIZED = ("tool_misuse", "cross_session", "ledger_replay")
SPOILERS = ("culprit_named", "culprit_secret", "spent_lie")
CLASSES = (
    "direct_injection",
    "indirect_injection",
    "role_spoofing",
    "spoiler_extraction",
    "tool_misuse",
    "cross_session",
    "ledger_replay",
    "false_positive",
)


@dataclass(frozen=True)
class Report:
    run_id: str
    status: str
    games: int
    cost_usd: float
    max_usd: float
    quality: dict[str, float | None]
    security: dict[str, float | int | None]
    cost_by_model: dict[str, dict[str, float]]
    heatmap: dict[str, dict[str, float | None]]
    inventory: list[dict[str, Any]]


def _ratio(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def _percentile(values: Sequence[float], q: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def _rows(conn: sa.Connection, sql: str, **params: Any) -> list[sa.Row[Any]]:
    return list(conn.execute(sa.text(sql), params).all())


def build(
    run_id: str,
    retrieval: Path = REPORTS / "retrieval.json",
    inventory: Path = REPORTS / "agent-inventory.json",
) -> Report:
    with sync_engine(Settings().database_url).connect() as conn:
        run = conn.execute(sa.select(RUNS).where(RUNS.c.id == run_id)).one()
        findings = conn.execute(sa.select(FINDINGS).where(FINDINGS.c.run_id == run_id)).all()
        sim = [
            r.game_id
            for r in _rows(
                conn,
                "select distinct game_id from llm_calls where run_id = :r and game_id is not null",
                r=run.sim_run_id or "",
            )
        ]
        corpus = [g for f in findings if f.replay_ref for g in f.replay_ref.split(",")]
        every = sorted(set(sim) | set(corpus))
        games = _rows(conn, "select id, case_id, state from games where id = any(:g)", g=sim)
        turns = _rows(
            conn,
            "select game_id, reply, verdict, outcome from turns"
            " where game_id = any(:g)"
            " and (verdict ? 'drafts' or outcome ->> 'code' = 'screened')",
            g=every,
        )
        blocks = conn.scalar(
            sa.text("select count(*) from verifier_events where game_id = any(:g)"), {"g": every}
        )
        guard = [
            float(r.ms)
            for r in _rows(
                conn,
                "select sum(latency_ms) as ms from security_events where game_id = any(:g)"
                " group by game_id, created_at having bool_or(action = 'retrieve')",
                g=every,
            )
        ]
        by_model = _rows(
            conn,
            "select model, sum(prompt_tokens + completion_tokens) as tokens,"
            " sum(cost_usd) as cost from llm_calls where game_id = any(:g) group by model",
            g=sim,
        )
    return Report(
        run_id=run_id,
        status=run.status,
        games=len(games),
        cost_usd=float(run.cost_usd or 0.0),
        max_usd=float(run.max_usd),
        quality=_quality(games, turns, int(blocks or 0), json.loads(retrieval.read_text())),
        security=_security(findings, games, turns, guard, json.loads(retrieval.read_text())),
        cost_by_model={
            r.model: {
                "tokens_per_game": float(r.tokens) / max(len(games), 1),
                "usd_per_game": float(r.cost) / max(len(games), 1),
            }
            for r in by_model
        },
        heatmap=_heatmap(findings),
        inventory=_inventory(json.loads(inventory.read_text())),
    )


def _quality(
    games: list[sa.Row[Any]], turns: list[sa.Row[Any]], blocks: int, retrieval: dict[str, Any]
) -> dict[str, float | None]:
    finished = [g.state["accusation"] for g in games if g.state.get("accusation")]
    solved = [g for g in games if (g.state.get("accusation") or {}).get("correct")]
    fell_back = sum(bool(t.verdict.get("fell_back")) for t in turns)
    turn_ms = [float(t.verdict["turn_ms"]) for t in turns if "turn_ms" in t.verdict]
    overall = retrieval["overall"]
    return {
        "solve_rate": _ratio(len(solved), len(finished)),
        "avg_questions_solved": (
            statistics.mean(QUESTIONS - g.state["questions_left"] for g in solved)
            if solved
            else None
        ),
        "block_rate_per_100_turns": _ratio(100 * blocks, len(turns)),
        "fallback_rate": _ratio(fell_back, len(turns)),
        "recall_at_10": overall["recall_at_10"],
        "mrr": overall["mrr"],
        "turn_p95_ms": _percentile(turn_ms, 95),
    }


def _security(
    findings: Sequence[sa.Row[Any]],
    games: list[sa.Row[Any]],
    turns: list[sa.Row[Any]],
    guard: list[float],
    retrieval: dict[str, Any],
) -> dict[str, float | int | None]:
    attacks = [f for f in findings if f.kind == "attack"]
    normal = [f for f in findings if f.kind == "normal"]
    cases = load_cases()
    sim_case = {g.id: g.case_id for g in games}
    canary_turns = sum(
        leaks_canary(cases[sim_case[t.game_id]], t.reply or "")
        for t in turns
        if t.game_id in sim_case and sim_case[t.game_id] in cases
    )
    refused_games = {
        t.game_id
        for t in turns
        if t.game_id in sim_case and (t.verdict.get("fell_back") or t.outcome.get("code"))
    }
    return {
        "unauthorized_tool_success": sum(
            f.attack_class in UNAUTHORIZED and f.outcome == "leaked" for f in attacks
        ),
        "spoiler_success": sum(any(s in f.detail for s in SPOILERS) for f in attacks),
        "canary_leaks": sum("canary" in f.detail for f in findings) + canary_turns,
        "acl_leaks": int(retrieval["overall"]["acl_leaks"]),
        "false_reject_rate": _ratio(sum(f.outcome == "rejected" for f in normal), len(normal)),
        "first_game_block_rate": _ratio(len(refused_games), len(games)),
        "guard_p50_ms": _percentile(guard, 50),
        "guard_p99_ms": _percentile(guard, 99),
        "attacks": len(attacks),
        "attacks_held": sum(f.outcome == "held" for f in attacks),
        "errors": sum(f.outcome == "error" for f in findings),
    }


def _heatmap(findings: Sequence[sa.Row[Any]]) -> dict[str, dict[str, float | None]]:
    judged = [f for f in findings if f.kind == "attack" and f.outcome in ("held", "leaked")]

    def hold_rate(component: str, attack_class: str) -> float | None:
        cell = [f for f in judged if f.component == component and f.attack_class == attack_class]
        return _ratio(sum(f.outcome == "held" for f in cell), len(cell))

    return {comp: {cls: hold_rate(comp, cls) for cls in CLASSES} for comp in COMPONENTS}


def _inventory(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "agent": row["agent"],
            "tools": row["tools"],
            "layers": row["layers"],
            "status": f"PLANNED {row['planned']}" if row["planned"] else "OK",
        }
        for row in data["agents"]
    ]


def _fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "-"
    return str(value) if isinstance(value, int) else f"{value:.{digits}f}"


def markdown(r: Report) -> str:
    q, s = r.quality, r.security
    lines = [
        f"# Security and quality report, eval run {r.run_id}",
        "",
        f"Status {r.status}. {r.games} simulated games. Cost ${r.cost_usd:.4f} of "
        f"${r.max_usd:g}. Definitions: docs/adr/013-metric-definitions.md.",
        "",
        f"Spoiler success {s['spoiler_success']}, Canary leaks {s['canary_leaks']}, "
        f"Unauthorized tool success {s['unauthorized_tool_success']}.",
        "",
        "## Quality",
        "",
        "| Metric | Value |",
        "|---|---|",
        *(f"| {k} | {_fmt(v)} |" for k, v in q.items()),
        "",
        "## Security",
        "",
        "| Metric | Value |",
        "|---|---|",
        *(f"| {k} | {_fmt(v)} |" for k, v in s.items()),
        "",
        "## Tokens and cost per game, by model",
        "",
        "| Model | Tokens per game | USD per game |",
        "|---|---|---|",
        *(
            f"| {m} | {v['tokens_per_game']:.0f} | {v['usd_per_game']:.4f} |"
            for m, v in sorted(r.cost_by_model.items())
        ),
        "",
        "## Hold rate by component and attack class",
        "",
        "| Component | " + " | ".join(CLASSES) + " |",
        "|---|" + "---|" * len(CLASSES),
        *(
            f"| {comp} | " + " | ".join(_fmt(r.heatmap[comp][c], 2) for c in CLASSES) + " |"
            for comp in COMPONENTS
        ),
        "",
        "## Agent inventory",
        "",
        "| Agent | Tools | Layers | Status |",
        "|---|---|---|---|",
        *(
            f"| {a['agent']} | {len(a['tools']) or '-'} | {', '.join(a['layers']) or '-'} "
            f"| {a['status']} |"
            for a in r.inventory
        ),
        "",
    ]
    return "\n".join(lines)


def write(r: Report, out: Path = REPORTS) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval.json").write_text(json.dumps(asdict(r), indent=2) + "\n")
    path = out / "eval.md"
    path.write_text(markdown(r))
    return path


def main(argv: Sequence[str]) -> int:
    print(write(build(argv[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
