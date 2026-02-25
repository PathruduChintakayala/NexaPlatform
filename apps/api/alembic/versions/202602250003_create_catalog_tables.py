"""create catalog tables

Revision ID: 202602250003
Revises: 202602250002
Create Date: 2026-02-25 17:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250003"
down_revision: str | None = "202602250002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_product",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_currency", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "company_code", "sku", name="uq_catalog_product_sku"),
    )
    op.create_index(
        "ix_catalog_product_scope",
        "catalog_product",
        ["tenant_id", "company_code", "is_active"],
    )

    op.create_table(
        "catalog_pricebook",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "company_code", "name", name="uq_catalog_pricebook_name"),
        sa.CheckConstraint("(valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)", name="ck_catalog_pricebook_valid_range"),
    )
    op.create_index(
        "ix_catalog_pricebook_scope",
        "catalog_pricebook",
        ["tenant_id", "company_code", "currency", "is_active"],
    )

    op.create_table(
        "catalog_pricebook_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pricebook_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("billing_period", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pricebook_id"], ["catalog_pricebook.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "pricebook_id",
            "product_id",
            "billing_period",
            "currency",
            name="uq_catalog_pricebook_item_key",
        ),
        sa.CheckConstraint("unit_price > 0", name="ck_catalog_pricebook_item_unit_price_positive"),
    )
    op.create_index(
        "ix_catalog_pricebook_item_pricebook",
        "catalog_pricebook_item",
        ["pricebook_id", "product_id"],
    )
    op.create_index(
        "ix_catalog_pricebook_item_lookup",
        "catalog_pricebook_item",
        ["currency", "billing_period", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_pricebook_item_lookup", table_name="catalog_pricebook_item")
    op.drop_index("ix_catalog_pricebook_item_pricebook", table_name="catalog_pricebook_item")
    op.drop_table("catalog_pricebook_item")
    op.drop_index("ix_catalog_pricebook_scope", table_name="catalog_pricebook")
    op.drop_table("catalog_pricebook")
    op.drop_index("ix_catalog_product_scope", table_name="catalog_product")
    op.drop_table("catalog_product")
