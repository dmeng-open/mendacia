"""create security_events and record prompt_version on llm_calls"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("trace_id", sa.Text, nullable=False),
        sa.Column("game_id", sa.Text, nullable=False),
        sa.Column("turn_id", sa.Integer, nullable=True),
        sa.Column("actor_type", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("reason_code", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Double, nullable=False),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("prompt_version", sa.Text, nullable=True),
        sa.Column("case_version", sa.Text, nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False),
        sa.Column("replay_ref", sa.Text, nullable=True),
        sa.Column("decision_trace", JSONB, nullable=False),
        sa.CheckConstraint(
            "decision in ('allow', 'deny', 'transition_required')", name="decision_known"
        ),
    )
    op.create_index("security_events_game", "security_events", ["game_id", "turn_id"])
    op.add_column("llm_calls", sa.Column("prompt_version", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("llm_calls", "prompt_version")
    op.drop_table("security_events")
