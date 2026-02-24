"""create crm pipelines and opportunities

Revision ID: 202602240004
Revises: 202602240003
Create Date: 2026-02-24 00:04:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240004"
down_revision: str | None = "202602240003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_pipeline",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("selling_legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_pipeline_selling_legal_entity_id",
        "crm_pipeline",
        ["selling_legal_entity_id"],
        unique=False,
    )

    op.create_table(
        "crm_pipeline_stage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage_type", sa.String(length=32), nullable=False),
        sa.Column("default_probability", sa.Integer(), nullable=True),
        sa.Column("requires_amount", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("requires_expected_close_date", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["pipeline_id"], ["crm_pipeline.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_id", "position", name="uq_crm_pipeline_stage_pipeline_position"),
        sa.UniqueConstraint("pipeline_id", "name", name="uq_crm_pipeline_stage_pipeline_name"),
    )
    op.create_index("ix_crm_pipeline_stage_pipeline_id", "crm_pipeline_stage", ["pipeline_id"], unique=False)

    op.create_table(
        "crm_opportunity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("selling_legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("forecast_category", sa.String(length=32), nullable=True, server_default="Pipeline"),
        sa.Column("primary_contact_id", sa.Uuid(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("revenue_quote_id", sa.Uuid(), nullable=True),
        sa.Column("revenue_order_id", sa.Uuid(), nullable=True),
        sa.Column("closed_won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["account_id"], ["crm_account.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["stage_id"], ["crm_pipeline_stage.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_contact_id"], ["crm_contact.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_opportunity_scope_filter",
        "crm_opportunity",
        ["selling_legal_entity_id", "stage_id", "owner_user_id", "expected_close_date"],
        unique=False,
    )
    op.create_index("ix_crm_opportunity_account_id", "crm_opportunity", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_crm_opportunity_account_id", table_name="crm_opportunity")
    op.drop_index("ix_crm_opportunity_scope_filter", table_name="crm_opportunity")
    op.drop_table("crm_opportunity")

    op.drop_index("ix_crm_pipeline_stage_pipeline_id", table_name="crm_pipeline_stage")
    op.drop_table("crm_pipeline_stage")

    op.drop_index("ix_crm_pipeline_selling_legal_entity_id", table_name="crm_pipeline")
    op.drop_table("crm_pipeline")
