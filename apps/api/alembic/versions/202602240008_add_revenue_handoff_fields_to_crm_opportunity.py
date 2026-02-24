"""add revenue handoff fields to crm opportunity

Revision ID: 202602240008
Revises: 202602240007
Create Date: 2026-02-24 00:08:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240008"
down_revision: str | None = "202602240007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crm_opportunity",
        sa.Column("revenue_handoff_status", sa.String(length=32), nullable=False, server_default="NotRequested"),
    )
    op.add_column("crm_opportunity", sa.Column("revenue_handoff_mode", sa.String(length=64), nullable=True))
    op.add_column("crm_opportunity", sa.Column("revenue_handoff_last_error", sa.Text(), nullable=True))
    op.add_column("crm_opportunity", sa.Column("revenue_handoff_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crm_opportunity", sa.Column("revenue_handoff_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_opportunity", "revenue_handoff_completed_at")
    op.drop_column("crm_opportunity", "revenue_handoff_requested_at")
    op.drop_column("crm_opportunity", "revenue_handoff_last_error")
    op.drop_column("crm_opportunity", "revenue_handoff_mode")
    op.drop_column("crm_opportunity", "revenue_handoff_status")
