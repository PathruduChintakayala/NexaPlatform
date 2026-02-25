"""create business revenue tables

Revision ID: 202602250004
Revises: 202602250003
Create Date: 2026-02-25 18:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250004"
down_revision: str | None = "202602250003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revenue_quote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("quote_number", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "quote_number", name="uq_revenue_quote_number_company"),
    )
    op.create_index(
        "ix_revenue_quote_scope_date",
        "revenue_quote",
        ["tenant_id", "company_code", "created_at"],
    )

    op.create_table(
        "revenue_quote_line",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("pricebook_item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["revenue_quote.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_revenue_quote_line_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_revenue_quote_line_unit_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_revenue_quote_line_total_nonnegative"),
    )
    op.create_index("ix_revenue_quote_line_quote_id", "revenue_quote_line", ["quote_id"])

    op.create_table(
        "revenue_order",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("order_number", sa.String(length=64), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "order_number", name="uq_revenue_order_number_company"),
    )
    op.create_index(
        "ix_revenue_order_scope_date",
        "revenue_order",
        ["tenant_id", "company_code", "created_at"],
    )

    op.create_table(
        "revenue_order_line",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("pricebook_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("service_start", sa.Date(), nullable=True),
        sa.Column("service_end", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["revenue_order.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_revenue_order_line_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_revenue_order_line_unit_price_nonnegative"),
        sa.CheckConstraint("line_total >= 0", name="ck_revenue_order_line_total_nonnegative"),
    )
    op.create_index("ix_revenue_order_line_order_id", "revenue_order_line", ["order_id"])

    op.create_table(
        "revenue_contract",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("contract_number", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "contract_number", name="uq_revenue_contract_number_company"),
    )
    op.create_index(
        "ix_revenue_contract_scope_date",
        "revenue_contract",
        ["tenant_id", "company_code", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_revenue_contract_scope_date", table_name="revenue_contract")
    op.drop_table("revenue_contract")
    op.drop_index("ix_revenue_order_line_order_id", table_name="revenue_order_line")
    op.drop_table("revenue_order_line")
    op.drop_index("ix_revenue_order_scope_date", table_name="revenue_order")
    op.drop_table("revenue_order")
    op.drop_index("ix_revenue_quote_line_quote_id", table_name="revenue_quote_line")
    op.drop_table("revenue_quote_line")
    op.drop_index("ix_revenue_quote_scope_date", table_name="revenue_quote")
    op.drop_table("revenue_quote")
