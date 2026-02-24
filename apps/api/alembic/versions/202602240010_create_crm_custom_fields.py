"""create crm custom fields

Revision ID: 202602240010
Revises: 202602240009
Create Date: 2026-02-24 00:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240010"
down_revision: str | None = "202602240009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_custom_field_definition",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("allowed_values", sa.JSON(), nullable=True),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "field_key",
            "legal_entity_id",
            name="uq_crm_custom_field_definition_scope",
        ),
    )
    op.create_index(
        "ix_crm_custom_field_definition_entity_scope_active",
        "crm_custom_field_definition",
        ["entity_type", "legal_entity_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "crm_custom_field_value",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "field_key",
            name="uq_crm_custom_field_value_entity_field",
        ),
    )
    op.create_index(
        "ix_crm_custom_field_value_entity",
        "crm_custom_field_value",
        ["entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_custom_field_value_entity", table_name="crm_custom_field_value")
    op.drop_table("crm_custom_field_value")

    op.drop_index(
        "ix_crm_custom_field_definition_entity_scope_active",
        table_name="crm_custom_field_definition",
    )
    op.drop_table("crm_custom_field_definition")
