"""create games, turns, and outbox: one transaction commits each game turn"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _created() -> sa.Column[datetime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("case_id", sa.Text, nullable=False),
        sa.Column("case_version", sa.Text, nullable=False),
        sa.Column("actor_type", sa.Text, nullable=False, server_default="player"),
        sa.Column("session_digest", sa.Text, nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False, server_default="0"),
        _created(),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abuse_flag", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("game_id", sa.Text, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("args_hash", sa.Text, nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("tool", sa.Text, nullable=False),
        sa.Column("suspect", sa.Text, nullable=True),
        sa.Column("reply", sa.Text, nullable=True),
        sa.Column("verdict", JSONB, nullable=False),
        sa.Column("outcome", JSONB, nullable=False),
        sa.Column("cost_usd", sa.Double, nullable=False, server_default="0"),
        _created(),
        sa.UniqueConstraint("game_id", "idempotency_key", name="turns_game_key"),
        sa.UniqueConstraint("game_id", "state_version", name="turns_game_version"),
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("game_id", sa.Text, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        _created(),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("game_id", "state_version", name="outbox_game_version"),
    )
    op.create_index("security_events_game_time", "security_events", ["game_id", "created_at"])
    op.create_index("llm_calls_game", "llm_calls", ["game_id"])


def downgrade() -> None:
    op.drop_index("llm_calls_game", "llm_calls")
    op.drop_index("security_events_game_time", "security_events")
    op.drop_table("outbox")
    op.drop_table("turns")
    op.drop_table("games")
