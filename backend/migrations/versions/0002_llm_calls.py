"""create llm_calls"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("game_id", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False),
        sa.Column("completion_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Double, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
