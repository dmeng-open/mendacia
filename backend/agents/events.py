from typing import Literal

import sqlalchemy as sa

from app.config import Settings
from app.db import sync_engine

Rule = Literal["block_culprit", "block_unplanned", "input_screen"]

Action = Literal["block", "rewrite", "fallback", "refuse"]

VERIFIER_EVENTS = sa.Table(
    "verifier_events",
    sa.MetaData(),
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("game_id", sa.Text),
    sa.Column("suspect", sa.Text),
    sa.Column("turn", sa.Integer),
    sa.Column("rule", sa.Text),
    sa.Column("claim", sa.Text),
    sa.Column("action", sa.Text),
)


def log_event(
    *, game_id: str, suspect: str, turn: int, rule: Rule, claim: str, action: Action
) -> None:
    with sync_engine(Settings().database_url).begin() as conn:
        conn.execute(
            sa.insert(VERIFIER_EVENTS).values(
                game_id=game_id, suspect=suspect, turn=turn, rule=rule, claim=claim, action=action
            )
        )
