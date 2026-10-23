from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

ABUSE_WINDOW = timedelta(minutes=10)
ABUSE_STRIKES = 8
COOLDOWN = timedelta(seconds=60)
TOKEN_CAP = 200_000
STRIKE_REASONS = frozenset(
    {"screened", "bad_args", "actor_not_allowed", "unknown_tool", "honeypot"}
)

USAGE_SQL = sa.text("""
select
  (select coalesce(json_object_agg(action, n), '{}'::json) from (
      select action, count(*) as n from security_events
      where game_id = :g and decision = 'allow' and action = any(CAST(:tools AS text[]))
        and reason_code <> 'replayed'
      group by action) c) as calls,
  (select coalesce(array_agg(created_at order by created_at), '{}') from security_events
      where game_id = :g and decision = 'deny'
        and reason_code = any(CAST(:strikes AS text[]))
        and created_at > now() - make_interval(secs => :window)) as strikes,
  (select coalesce(sum(prompt_tokens + completion_tokens), 0) from llm_calls
      where game_id = :g) as tokens,
  now() as now
""")


@dataclass(frozen=True)
class Usage:
    calls: Mapping[str, int]
    strikes: tuple[datetime, ...]
    tokens: int
    now: datetime


@dataclass(frozen=True)
class Refusal:
    code: Literal["budget_exhausted", "cooldown"]
    retry_after_s: int | None = None


async def usage(conn: AsyncConnection, game_id: str, tools: Collection[str]) -> Usage:
    params = {
        "g": game_id,
        "tools": sorted(tools),
        "strikes": sorted(STRIKE_REASONS),
        "window": ABUSE_WINDOW.total_seconds(),
    }
    row = (await conn.execute(USAGE_SQL, params)).one()
    return Usage(dict(row.calls), tuple(row.strikes), int(row.tokens), row.now)


def decide(tool: str, budget: int, calls_model: bool, use: Usage) -> Refusal | None:
    if use.calls.get(tool, 0) >= budget:
        return Refusal("budget_exhausted")
    if not calls_model:
        return None
    if use.tokens >= TOKEN_CAP:
        return Refusal("cooldown")
    recent = use.strikes[-ABUSE_STRIKES:]
    if len(recent) == ABUSE_STRIKES and use.now < recent[-1] + COOLDOWN:
        return Refusal("cooldown", int((recent[-1] + COOLDOWN - use.now).total_seconds()) + 1)
    return None
