"""record each security and quality eval run and one finding per corpus entry"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_eval_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column("games", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_usd", sa.Double, nullable=False),
        sa.Column("cost_usd", sa.Double, nullable=True),
        sa.Column("sim_run_id", sa.Text, nullable=True),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("case_versions", JSONB, nullable=False, server_default="{}"),
        sa.Column("model_versions", JSONB, nullable=False, server_default="[]"),
        sa.Column("prompt_versions", JSONB, nullable=False, server_default="[]"),
    )
    op.create_check_constraint(
        "run_status_known",
        "security_eval_runs",
        "status in ('running', 'finished', 'budget_exceeded', 'failed')",
    )
    op.create_table(
        "security_findings",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text,
            sa.ForeignKey("security_eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("case_id", sa.Text, nullable=False),
        sa.Column("case_version", sa.Text, nullable=False),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("prompt_version", sa.Text, nullable=True),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("attack_class", sa.Text, nullable=False),
        sa.Column("owasp_id", sa.Text, nullable=True),
        sa.Column("component", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("replay_ref", sa.Text, nullable=True),
        sa.Column("detail", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_check_constraint(
        "finding_outcome_known",
        "security_findings",
        "outcome in ('held', 'leaked', 'passed', 'rejected', 'error')",
    )
    op.create_check_constraint(
        "finding_severity_known",
        "security_findings",
        "severity in ('critical', 'high', 'medium', 'low', 'none')",
    )
    op.create_index("security_findings_run", "security_findings", ["run_id"])


def downgrade() -> None:
    op.drop_index("security_findings_run", "security_findings")
    op.drop_table("security_findings")
    op.drop_table("security_eval_runs")
