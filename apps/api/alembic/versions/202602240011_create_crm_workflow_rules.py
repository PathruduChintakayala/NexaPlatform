"""create crm workflow rules

Revision ID: 202602240011
Revises: 202602240010
Create Date: 2026-02-24 00:11:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240011"
down_revision: str | None = "202602240010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_workflow_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_event", sa.String(length=128), nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_workflow_rule_trigger_active",
        "crm_workflow_rule",
        ["trigger_event", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_crm_workflow_rule_scope_active",
        "crm_workflow_rule",
        ["legal_entity_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_workflow_rule_scope_active", table_name="crm_workflow_rule")
    op.drop_index("ix_crm_workflow_rule_trigger_active", table_name="crm_workflow_rule")
    op.drop_table("crm_workflow_rule")
