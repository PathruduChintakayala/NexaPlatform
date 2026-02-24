"""add cooldown seconds to crm workflow rule

Revision ID: 202602240012
Revises: 202602240011
Create Date: 2026-02-24 00:12:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240012"
down_revision: str | None = "202602240011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crm_workflow_rule", sa.Column("cooldown_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_workflow_rule", "cooldown_seconds")
