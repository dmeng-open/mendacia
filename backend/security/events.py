import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.config import Settings
from app.db import sync_engine
from security.context import CANARY_PREFIX, AuthContext
from security.policy import Decision

Step = Literal["auth", "identity", "policy", "tool", "verify", "commit"]

SECURITY_EVENTS = sa.Table(
    "security_events",
    sa.MetaData(),
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("trace_id", sa.Text),
    sa.Column("game_id", sa.Text),
    sa.Column("turn_id", sa.Integer),
    sa.Column("actor_type", sa.Text),
    sa.Column("action", sa.Text),
    sa.Column("resource_type", sa.Text),
    sa.Column("policy_version", sa.Text),
    sa.Column("decision", sa.Text),
    sa.Column("reason_code", sa.Text),
    sa.Column("latency_ms", sa.Double),
    sa.Column("model_version", sa.Text),
    sa.Column("prompt_version", sa.Text),
    sa.Column("case_version", sa.Text),
    sa.Column("state_version", sa.Integer),
    sa.Column("replay_ref", sa.Text),
    sa.Column("decision_trace", JSONB),
)


@dataclass(frozen=True)
class TraceStep:
    step: Step
    outcome: str
    ms: float


class CanaryInRow(ValueError):
    pass


def log_decision(
    subject: AuthContext,
    *,
    trace_id: str,
    turn_id: int | None,
    action: str,
    resource_type: str,
    decision: Decision,
    latency_ms: float,
    trace: Sequence[TraceStep],
    model_version: str | None = None,
    prompt_version: str | None = None,
    replay_ref: str | None = None,
) -> None:
    values = {
        "trace_id": trace_id,
        "game_id": subject.game_id,
        "turn_id": turn_id,
        "actor_type": subject.actor_type,
        "action": action,
        "resource_type": resource_type,
        "policy_version": decision.policy_version,
        "decision": decision.effect,
        "reason_code": decision.reason_code,
        "latency_ms": round(latency_ms, 3),
        "model_version": model_version,
        "prompt_version": prompt_version,
        "case_version": subject.case_version,
        "state_version": subject.state_version,
        "replay_ref": replay_ref,
        "decision_trace": [asdict(s) for s in trace],
    }
    if CANARY_PREFIX.lower() in json.dumps(values).lower():
        raise CanaryInRow("security_events rows never hold the canary")
    with sync_engine(Settings().database_url).begin() as conn:
        conn.execute(sa.insert(SECURITY_EVENTS).values(**values))
