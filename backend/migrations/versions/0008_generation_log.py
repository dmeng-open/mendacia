"""create generation_log and tag llm_calls with the run that made them"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("run_id", sa.Text, nullable=True))
    op.create_index("llm_calls_run", "llm_calls", ["run_id"])
    op.create_table(
        "generation_log",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brief", JSONB, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False, server_default="running"),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("rounds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("round_log", JSONB, nullable=False, server_default="[]"),
        sa.Column("cost_usd", sa.Double, nullable=True),
        sa.Column("models", JSONB, nullable=True),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("case_id", sa.Text, nullable=True),
        sa.Column("case_version", sa.Text, nullable=True),
        sa.CheckConstraint(
            "outcome in ('running', 'accepted', 'discarded', 'crashed')", name="outcome_known"
        ),
        sa.CheckConstraint(
            "(outcome = 'accepted') = (case_version is not null)", name="accepted_has_version"
        ),
    )


def downgrade() -> None:
    op.drop_table("generation_log")
    op.drop_index("llm_calls_run", "llm_calls")
    op.drop_column("llm_calls", "run_id")
