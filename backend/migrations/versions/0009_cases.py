"""store published cases and record each generation's batch and security gate"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("case_version", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("body", JSONB, nullable=False),
        sa.Column("generation_id", sa.Text, nullable=True),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column("generation_log", sa.Column("batch_id", sa.Text, nullable=True))
    op.add_column("generation_log", sa.Column("gate", sa.Text, nullable=True))
    op.add_column("generation_log", sa.Column("gate_detail", sa.Text, nullable=True))
    op.create_check_constraint(
        "gate_known", "generation_log", "gate in ('passed', 'security_rejected')"
    )
    op.create_index("generation_log_batch", "generation_log", ["batch_id"])


def downgrade() -> None:
    op.drop_index("generation_log_batch", "generation_log")
    op.drop_constraint("gate_known", "generation_log")
    op.drop_column("generation_log", "gate_detail")
    op.drop_column("generation_log", "gate")
    op.drop_column("generation_log", "batch_id")
    op.drop_table("cases")
