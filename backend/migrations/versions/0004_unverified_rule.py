"""allow the unverified rule in verifier_events"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("rule_known", "verifier_events", type_="check")
    op.create_check_constraint(
        "rule_known",
        "verifier_events",
        "rule in ('block_culprit', 'block_unplanned', 'unverified', 'input_screen')",
    )


def downgrade() -> None:
    op.drop_constraint("rule_known", "verifier_events", type_="check")
    op.create_check_constraint(
        "rule_known",
        "verifier_events",
        "rule in ('block_culprit', 'block_unplanned', 'input_screen')",
    )
