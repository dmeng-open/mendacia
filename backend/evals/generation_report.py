import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import sqlalchemy as sa

from app.config import Settings
from app.db import sync_engine
from app.llm import LLM_CALLS
from engine.generator import GENERATION_LOG

REPORTS = Path(__file__).resolve().parents[2] / "reports"


@dataclass(frozen=True)
class GenerationReport:
    batch_id: str
    attempts: int
    first_pass: int
    final: int
    security_rejected: int
    discarded: int
    cost_usd: float
    rows: tuple[dict[str, object], ...]

    @property
    def summary(self) -> str:
        return (
            f"first-pass {self.first_pass}/{self.attempts}, final {self.final}/{self.attempts}, "
            f"security-rejected {self.security_rejected}"
        )


def latest_batch() -> str | None:
    with sync_engine(Settings().database_url).connect() as conn:
        return conn.scalar(
            sa.select(GENERATION_LOG.c.batch_id)
            .where(GENERATION_LOG.c.batch_id.is_not(None))
            .order_by(GENERATION_LOG.c.started_at.desc())
            .limit(1)
        )


def gate_prefix(batch_id: str) -> str:
    return f"gate-{batch_id}-"


def batch_spend(batch_id: str) -> float:
    with sync_engine(Settings().database_url).connect() as conn:
        total = conn.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(LLM_CALLS.c.cost_usd), 0.0)).where(
                sa.or_(
                    LLM_CALLS.c.run_id.in_(
                        sa.select(GENERATION_LOG.c.id).where(GENERATION_LOG.c.batch_id == batch_id)
                    ),
                    LLM_CALLS.c.game_id.startswith(gate_prefix(batch_id)),
                )
            )
        )
    return float(total or 0.0)


def build(batch_id: str) -> GenerationReport:
    log = GENERATION_LOG.c
    with sync_engine(Settings().database_url).connect() as conn:
        rows = conn.execute(
            sa.select(
                log.id,
                log.outcome,
                log.rounds,
                log.failure_reason,
                log.cost_usd,
                log.case_id,
                log.gate,
                log.gate_detail,
                (sa.func.extract("epoch", log.finished_at - log.started_at)).label("seconds"),
            )
            .where(log.batch_id == batch_id)
            .order_by(log.started_at)
        ).all()
    passed = [r for r in rows if r.gate == "passed"]
    return GenerationReport(
        batch_id=batch_id,
        attempts=len(rows),
        first_pass=sum(r.rounds == 1 for r in passed),
        final=len(passed),
        security_rejected=sum(r.gate == "security_rejected" for r in rows),
        discarded=sum(r.outcome != "accepted" for r in rows),
        cost_usd=round(batch_spend(batch_id), 4),
        rows=tuple(
            {
                "generation_id": r.id,
                "outcome": r.outcome,
                "rounds": r.rounds,
                "case_id": r.case_id,
                "gate": r.gate,
                "detail": r.gate_detail or r.failure_reason,
                "cost_usd": round(r.cost_usd or 0.0, 4),
                "seconds": round(float(r.seconds or 0), 1),
            }
            for r in rows
        ),
    )


def write(report: GenerationReport, out: Path | None = None) -> Path:
    out = out or REPORTS
    out.mkdir(exist_ok=True)
    (out / "generation.json").write_text(json.dumps(asdict(report), indent=2) + "\n")
    lines = [
        f"# Generation report, batch {report.batch_id}",
        "",
        report.summary,
        "",
        f"- Attempts: {report.attempts}",
        f"- First-pass rate: {report.first_pass}/{report.attempts} accepted in round 1 "
        "and passed the security gate",
        f"- Final pass rate: {report.final}/{report.attempts} accepted "
        "and passed the security gate",
        f"- Security-gate rejections: {report.security_rejected}",
        f"- Discarded by the repair loop: {report.discarded}",
        f"- Cost: ${report.cost_usd:.4f}, generation plus security gate",
        "",
        "| generation | outcome | rounds | case | gate | detail | cost | seconds |",
        "|---|---|---|---|---|---|---|---|",
        *(
            f"| {r['generation_id']} | {r['outcome']} | {r['rounds']} | {r['case_id'] or '-'} "
            f"| {r['gate'] or '-'} | {r['detail'] or '-'} | ${r['cost_usd']} | {r['seconds']} |"
            for r in report.rows
        ),
    ]
    path = out / "generation.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main(argv: Sequence[str]) -> int:
    batch_id = argv[0] if argv else latest_batch()
    if batch_id is None:
        print("no generation batch recorded")
        return 1
    report = build(batch_id)
    print(f"wrote {write(report)}")
    print(report.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
