from collections.abc import Sequence
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
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


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TraceStep(_Frozen):
    step: Step
    outcome: str
    ms: float


class AuditRow(_Frozen):
    trace_id: str
    game_id: str
    turn_id: int | None
    actor_type: str
    action: str
    resource_type: str
    policy_version: str
    decision: str
    reason_code: str
    latency_ms: float
    model_version: str | None
    prompt_version: str | None
    case_version: str
    state_version: int
    replay_ref: str | None
    decision_trace: tuple[TraceStep, ...]


class CanaryInRow(ValueError):
    pass


def audit_row(
    subject: AuthContext,
    *,
    trace_id: str,
    turn_id: int | None,
    action: str,
    resource_type: str,
    decision: Decision,
    trace: Sequence[TraceStep],
    model_version: str | None = None,
    prompt_version: str | None = None,
    replay_ref: str | None = None,
) -> AuditRow:
    return AuditRow(
        trace_id=trace_id,
        game_id=subject.game_id,
        turn_id=turn_id,
        actor_type=subject.actor_type,
        action=action,
        resource_type=resource_type,
        policy_version=decision.policy_version,
        decision=decision.effect,
        reason_code=decision.reason_code,
        latency_ms=round(sum(s.ms for s in trace), 3),
        model_version=model_version,
        prompt_version=prompt_version,
        case_version=subject.case_version,
        state_version=subject.state_version,
        replay_ref=replay_ref,
        decision_trace=tuple(trace),
    )


def log_decisions(rows: Sequence[AuditRow]) -> None:
    if any(CANARY_PREFIX.lower() in r.model_dump_json().lower() for r in rows):
        raise CanaryInRow("security_events rows never hold the canary")
    if rows:
        with sync_engine(Settings().database_url).begin() as conn:
            conn.execute(sa.insert(SECURITY_EVENTS), [r.model_dump(mode="json") for r in rows])
