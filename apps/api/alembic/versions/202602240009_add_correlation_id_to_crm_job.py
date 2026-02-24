"""add correlation id to crm job

Revision ID: 202602240009
Revises: 202602240008
Create Date: 2026-02-24 00:09:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240009"
down_revision: str | None = "202602240008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crm_job", sa.Column("correlation_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_job", "correlation_id")
