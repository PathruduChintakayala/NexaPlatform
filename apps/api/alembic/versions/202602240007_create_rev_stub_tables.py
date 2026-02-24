"""create revenue stub tables

Revision ID: 202602240007
Revises: 202602240006
Create Date: 2026-02-24 00:07:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240007"
down_revision: str | None = "202602240006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rev_quote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["crm_opportunity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rev_quote_opportunity_id", "rev_quote", ["opportunity_id"], unique=False)
    op.create_index("ix_rev_quote_status", "rev_quote", ["status"], unique=False)

    op.create_table(
        "rev_order",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["crm_opportunity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rev_order_opportunity_id", "rev_order", ["opportunity_id"], unique=False)
    op.create_index("ix_rev_order_status", "rev_order", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rev_order_status", table_name="rev_order")
    op.drop_index("ix_rev_order_opportunity_id", table_name="rev_order")
    op.drop_table("rev_order")

    op.drop_index("ix_rev_quote_status", table_name="rev_quote")
    op.drop_index("ix_rev_quote_opportunity_id", table_name="rev_quote")
    op.drop_table("rev_quote")
