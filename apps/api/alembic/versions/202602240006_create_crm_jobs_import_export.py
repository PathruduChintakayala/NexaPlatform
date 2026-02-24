"""create crm jobs import export

Revision ID: 202602240006
Revises: 202602240005
Create Date: 2026-02-24 00:06:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202602240006"
down_revision: str | None = "202602240005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Queued"),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_job_type_status_created",
        "crm_job",
        ["job_type", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_crm_job_requested_by_created",
        "crm_job",
        ["requested_by_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "crm_job_artifact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["crm_job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_job_artifact_job_type",
        "crm_job_artifact",
        ["job_id", "artifact_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_job_artifact_job_type", table_name="crm_job_artifact")
    op.drop_table("crm_job_artifact")

    op.drop_index("ix_crm_job_requested_by_created", table_name="crm_job")
    op.drop_index("ix_crm_job_type_status_created", table_name="crm_job")
    op.drop_table("crm_job")
