"""create crm leads

Revision ID: 202602240003
Revises: 202602240002
Create Date: 2026-02-24 00:03:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240003"
down_revision: str | None = "202602240002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_lead",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="New"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("selling_legal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("contact_first_name", sa.Text(), nullable=True),
        sa.Column("contact_last_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("qualification_notes", sa.Text(), nullable=True),
        sa.Column("disqualify_reason_code", sa.String(length=64), nullable=True),
        sa.Column("disqualify_notes", sa.Text(), nullable=True),
        sa.Column("converted_account_id", sa.Uuid(), nullable=True),
        sa.Column("converted_contact_id", sa.Uuid(), nullable=True),
        sa.Column("converted_opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_lead_scope_filter",
        "crm_lead",
        ["selling_legal_entity_id", "status", "owner_user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_crm_lead_email", "crm_lead", ["email"], unique=False)

    op.create_table(
        "crm_idempotency_key",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("endpoint", "key", name="uq_crm_idempotency_endpoint_key"),
    )


def downgrade() -> None:
    op.drop_table("crm_idempotency_key")
    op.drop_index("ix_crm_lead_email", table_name="crm_lead")
    op.drop_index("ix_crm_lead_scope_filter", table_name="crm_lead")
    op.drop_table("crm_lead")
