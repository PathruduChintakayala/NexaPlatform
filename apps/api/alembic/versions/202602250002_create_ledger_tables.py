"""create ledger tables

Revision ID: 202602250002
Revises: 202602250001
Create Date: 2026-02-25 13:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602250002"
down_revision: str | None = "202602250001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "company_code", "code", name="uq_ledger_account_code"),
    )
    op.create_index("ix_ledger_account_scope", "ledger_account", ["tenant_id", "company_code"])

    op.create_table(
        "ledger_journal_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("company_code", sa.String(length=64), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("posting_status", sa.String(length=32), nullable=False, server_default="POSTED"),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ledger_entry_scope_date",
        "ledger_journal_entry",
        ["tenant_id", "company_code", "entry_date"],
    )
    op.create_index(
        "ix_ledger_entry_source",
        "ledger_journal_entry",
        ["source_module", "source_type", "source_id"],
    )

    op.create_table(
        "ledger_journal_line",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("debit_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("credit_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("fx_rate_to_company_base", sa.Numeric(18, 8), nullable=False, server_default="1"),
        sa.Column("amount_company_base", sa.Numeric(18, 6), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("dimensions_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["ledger_journal_entry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["ledger_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("debit_amount >= 0", name="ck_ledger_line_debit_nonnegative"),
        sa.CheckConstraint("credit_amount >= 0", name="ck_ledger_line_credit_nonnegative"),
        sa.CheckConstraint(
            "((debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0))",
            name="ck_ledger_line_single_sided",
        ),
        sa.CheckConstraint("fx_rate_to_company_base > 0", name="ck_ledger_line_fx_positive"),
    )


def downgrade() -> None:
    op.drop_table("ledger_journal_line")
    op.drop_index("ix_ledger_entry_source", table_name="ledger_journal_entry")
    op.drop_index("ix_ledger_entry_scope_date", table_name="ledger_journal_entry")
    op.drop_table("ledger_journal_entry")
    op.drop_index("ix_ledger_account_scope", table_name="ledger_account")
    op.drop_table("ledger_account")
