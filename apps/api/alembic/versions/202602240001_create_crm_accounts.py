"""create crm accounts

Revision ID: 202602240001
Revises: 202602230001
Create Date: 2026-02-24 00:01:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240001"
down_revision: str | None = "202602230001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Active"),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("primary_region_code", sa.String(length=16), nullable=True),
        sa.Column("default_currency_code", sa.String(length=16), nullable=True),
        sa.Column("external_reference", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_account_status", "crm_account", ["status"], unique=False)
    op.create_index("ix_crm_account_owner_user_id", "crm_account", ["owner_user_id"], unique=False)
    op.create_index("ix_crm_account_deleted_at", "crm_account", ["deleted_at"], unique=False)

    op.create_table(
        "crm_account_legal_entity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["account_id"], ["crm_account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "legal_entity_id", name="uq_crm_account_legal_entity_pair"),
    )
    op.create_index(
        "ix_crm_account_legal_entity_account_id",
        "crm_account_legal_entity",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_crm_account_legal_entity_legal_entity_id",
        "crm_account_legal_entity",
        ["legal_entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_account_legal_entity_legal_entity_id", table_name="crm_account_legal_entity")
    op.drop_index("ix_crm_account_legal_entity_account_id", table_name="crm_account_legal_entity")
    op.drop_table("crm_account_legal_entity")

    op.drop_index("ix_crm_account_deleted_at", table_name="crm_account")
    op.drop_index("ix_crm_account_owner_user_id", table_name="crm_account")
    op.drop_index("ix_crm_account_status", table_name="crm_account")
    op.drop_table("crm_account")
