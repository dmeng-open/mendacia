"""create verifier_events"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verifier_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("game_id", sa.Text, nullable=False),
        sa.Column("suspect", sa.Text, nullable=False),
        sa.Column("turn", sa.Integer, nullable=False),
        sa.Column("rule", sa.Text, nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.CheckConstraint(
            "rule in ('block_culprit', 'block_unplanned', 'input_screen')", name="rule_known"
        ),
        sa.CheckConstraint(
            "action in ('block', 'rewrite', 'fallback', 'refuse')", name="action_known"
        ),
    )
    op.create_index("verifier_events_game", "verifier_events", ["game_id", "turn"])


def downgrade() -> None:
    op.drop_table("verifier_events")
