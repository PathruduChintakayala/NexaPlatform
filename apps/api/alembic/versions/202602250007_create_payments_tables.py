"""create payments tables

Revision ID: 202602250007
Revises: 202602250006
Create Date: 2026-02-25 23:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250007"
down_revision: str | None = "202602250006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments_payment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("payment_number", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("payment_method", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ledger_journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_code", "payment_number", name="uq_payments_payment_number_company"),
    )
    op.create_index("ix_payments_payment_scope", "payments_payment", ["tenant_id", "company_code"])

    op.create_table(
        "payments_allocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount_allocated", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoice.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments_payment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_allocation_invoice", "payments_allocation", ["invoice_id"])
    op.create_index("ix_payments_allocation_payment", "payments_allocation", ["payment_id"])

    op.create_table(
        "payments_refund",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("ledger_journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments_payment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_refund_scope", "payments_refund", ["tenant_id", "company_code"])
    op.create_index("ix_payments_refund_payment", "payments_refund", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_refund_payment", table_name="payments_refund")
    op.drop_index("ix_payments_refund_scope", table_name="payments_refund")
    op.drop_table("payments_refund")

    op.drop_index("ix_payments_allocation_payment", table_name="payments_allocation")
    op.drop_index("ix_payments_allocation_invoice", table_name="payments_allocation")
    op.drop_table("payments_allocation")

    op.drop_index("ix_payments_payment_scope", table_name="payments_payment")
    op.drop_table("payments_payment")
