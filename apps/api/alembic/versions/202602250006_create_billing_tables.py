"""create billing tables

Revision ID: 202602250006
Revises: 202602250005
Create Date: 2026-02-25 22:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250006"
down_revision: str | None = "202602250005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_invoice",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("amount_due", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("ledger_journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "invoice_number", name="uq_billing_invoice_number_company"),
    )
    op.create_index("ix_billing_invoice_scope_date", "billing_invoice", ["tenant_id", "company_code", "created_at"])

    op.create_table(
        "billing_invoice_line",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 6), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoice.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_invoice_line_invoice", "billing_invoice_line", ["invoice_id"])
    op.create_index("ix_billing_invoice_line_product", "billing_invoice_line", ["product_id"])

    op.create_table(
        "billing_credit_note",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("credit_note_number", sa.String(length=64), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("ledger_journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoice.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "credit_note_number", name="uq_billing_credit_note_number_company"),
    )
    op.create_index("ix_billing_credit_note_scope_date", "billing_credit_note", ["tenant_id", "company_code", "created_at"])

    op.create_table(
        "billing_credit_note_line",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("credit_note_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_line_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(["credit_note_id"], ["billing_credit_note.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_line_id"], ["billing_invoice_line.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "billing_dunning_case",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("stage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoice.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_dunning_scope", "billing_dunning_case", ["tenant_id", "company_code", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_billing_dunning_scope", table_name="billing_dunning_case")
    op.drop_table("billing_dunning_case")
    op.drop_table("billing_credit_note_line")
    op.drop_index("ix_billing_credit_note_scope_date", table_name="billing_credit_note")
    op.drop_table("billing_credit_note")
    op.drop_index("ix_billing_invoice_line_product", table_name="billing_invoice_line")
    op.drop_index("ix_billing_invoice_line_invoice", table_name="billing_invoice_line")
    op.drop_table("billing_invoice_line")
    op.drop_index("ix_billing_invoice_scope_date", table_name="billing_invoice")
    op.drop_table("billing_invoice")
