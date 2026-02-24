"""create crm activities notes attachments

Revision ID: 202602240005
Revises: 202602240004
Create Date: 2026-02-24 00:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240005"
down_revision: str | None = "202602240004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Open"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_activity_entity", "crm_activity", ["entity_type", "entity_id"], unique=False)
    op.create_index(
        "ix_crm_activity_assignment",
        "crm_activity",
        ["assigned_to_user_id", "status", "due_at"],
        unique=False,
    )

    op.create_table(
        "crm_note",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(length=32), nullable=False, server_default="markdown"),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_note_entity", "crm_note", ["entity_type", "entity_id"], unique=False)

    op.create_table(
        "crm_attachment_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_attachment_entity", "crm_attachment_link", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_crm_attachment_file", "crm_attachment_link", ["file_id"], unique=False)

    op.create_table(
        "crm_notification_intent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("intent_type", sa.String(length=64), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_notification_intent_recipient_status_created",
        "crm_notification_intent",
        ["recipient_user_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_notification_intent_recipient_status_created", table_name="crm_notification_intent")
    op.drop_table("crm_notification_intent")

    op.drop_index("ix_crm_attachment_file", table_name="crm_attachment_link")
    op.drop_index("ix_crm_attachment_entity", table_name="crm_attachment_link")
    op.drop_table("crm_attachment_link")

    op.drop_index("ix_crm_note_entity", table_name="crm_note")
    op.drop_table("crm_note")

    op.drop_index("ix_crm_activity_assignment", table_name="crm_activity")
    op.drop_index("ix_crm_activity_entity", table_name="crm_activity")
    op.drop_table("crm_activity")
