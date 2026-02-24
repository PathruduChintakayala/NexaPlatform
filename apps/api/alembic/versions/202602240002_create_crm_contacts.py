"""create crm contacts

Revision ID: 202602240002
Revises: 202602240001
Create Date: 2026-02-24 00:02:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240002"
down_revision: str | None = "202602240001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_contact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("locale", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["account_id"], ["crm_account.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_contact_account_id", "crm_contact", ["account_id"], unique=False)
    op.create_index("ix_crm_contact_email", "crm_contact", ["email"], unique=False)
    op.create_index(
        "uq_crm_contact_primary_per_account_active",
        "crm_contact",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true AND deleted_at IS NULL"),
        sqlite_where=sa.text("is_primary = 1 AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_crm_contact_primary_per_account_active", table_name="crm_contact")
    op.drop_index("ix_crm_contact_email", table_name="crm_contact")
    op.drop_index("ix_crm_contact_account_id", table_name="crm_contact")
    op.drop_table("crm_contact")
