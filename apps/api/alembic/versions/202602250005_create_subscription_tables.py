"""create subscription tables

Revision ID: 202602250005
Revises: 202602250004
Create Date: 2026-02-25 20:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250005"
down_revision: str | None = "202602250004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_plan",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("billing_period", sa.String(length=32), nullable=False),
        sa.Column("default_pricebook_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "code", name="uq_subscription_plan_code_company"),
    )
    op.create_index(
        "ix_subscription_plan_scope_date",
        "subscription_plan",
        ["tenant_id", "company_code", "created_at"],
    )

    op.create_table(
        "subscription_plan_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("pricebook_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_default", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "product_id", name="uq_subscription_plan_item_product"),
        sa.CheckConstraint("quantity_default > 0", name="ck_subscription_plan_item_quantity_positive"),
        sa.CheckConstraint("unit_price_snapshot >= 0", name="ck_subscription_plan_item_price_nonnegative"),
    )
    op.create_index("ix_subscription_plan_item_plan", "subscription_plan_item", ["plan_id"])

    op.create_table(
        "subscription",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("subscription_number", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("current_period_start", sa.Date(), nullable=True),
        sa.Column("current_period_end", sa.Date(), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("renewal_term_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("renewal_billing_period", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "subscription_number", name="uq_subscription_number_company"),
    )
    op.create_index("ix_subscription_scope_date", "subscription", ["tenant_id", "company_code", "created_at"])

    op.create_table(
        "subscription_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("pricebook_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "product_id", name="uq_subscription_item_product"),
        sa.CheckConstraint("quantity > 0", name="ck_subscription_item_quantity_positive"),
        sa.CheckConstraint("unit_price_snapshot >= 0", name="ck_subscription_item_price_nonnegative"),
    )
    op.create_index("ix_subscription_item_subscription", "subscription_item", ["subscription_id"])

    op.create_table(
        "subscription_change",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("change_type", sa.String(length=64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscription_change_subscription",
        "subscription_change",
        ["subscription_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_change_subscription", table_name="subscription_change")
    op.drop_table("subscription_change")
    op.drop_index("ix_subscription_item_subscription", table_name="subscription_item")
    op.drop_table("subscription_item")
    op.drop_index("ix_subscription_scope_date", table_name="subscription")
    op.drop_table("subscription")
    op.drop_index("ix_subscription_plan_item_plan", table_name="subscription_plan_item")
    op.drop_table("subscription_plan_item")
    op.drop_index("ix_subscription_plan_scope_date", table_name="subscription_plan")
    op.drop_table("subscription_plan")
