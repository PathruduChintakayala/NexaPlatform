from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.revenue.models import LegacyRevenueOrder as CRMRevOrder
from app.revenue.models import LegacyRevenueQuote as CRMRevQuote


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CRMAccount(Base):
    __tablename__ = "crm_account"

    # TODO: Switch to UUIDv7 defaults when UUIDv7 support is standardized across the codebase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Active", server_default="Active")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    primary_region_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    default_currency_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    legal_entities: Mapped[list[CRMAccountLegalEntity]] = relationship(
        "CRMAccountLegalEntity",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    contacts: Mapped[list[CRMContact]] = relationship(
        "CRMContact",
        back_populates="account",
    )
    opportunities: Mapped[list[CRMOpportunity]] = relationship(
        "CRMOpportunity",
        back_populates="account",
    )


class CRMAccountLegalEntity(Base):
    __tablename__ = "crm_account_legal_entity"

    # TODO: Switch to UUIDv7 defaults when UUIDv7 support is standardized across the codebase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    account: Mapped[CRMAccount] = relationship("CRMAccount", back_populates="legal_entities")

    __table_args__ = (
        UniqueConstraint("account_id", "legal_entity_id", name="uq_crm_account_legal_entity_pair"),
    )


class CRMContact(Base):
    __tablename__ = "crm_contact"

    # TODO: Switch to UUIDv7 defaults when UUIDv7 support is standardized across the codebase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    locale: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    account: Mapped[CRMAccount] = relationship("CRMAccount", back_populates="contacts")


class CRMLead(Base):
    __tablename__ = "crm_lead"

    # TODO: Switch to UUIDv7 defaults when UUIDv7 support is standardized across the codebase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="New", server_default="New")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    selling_legal_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    region_code: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    disqualify_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disqualify_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    converted_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    converted_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CRMIdempotencyKey(Base):
    __tablename__ = "crm_idempotency_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False, default=lambda: json.dumps({}))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("endpoint", "key", name="uq_crm_idempotency_endpoint_key"),
    )


class CRMPipeline(Base):
    __tablename__ = "crm_pipeline"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    selling_legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    stages: Mapped[list[CRMPipelineStage]] = relationship(
        "CRMPipelineStage",
        back_populates="pipeline",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CRMPipelineStage(Base):
    __tablename__ = "crm_pipeline_stage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_pipeline.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    default_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_amount: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    requires_expected_close_date: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    pipeline: Mapped[CRMPipeline] = relationship("CRMPipeline", back_populates="stages")
    opportunities: Mapped[list[CRMOpportunity]] = relationship("CRMOpportunity", back_populates="stage")

    __table_args__ = (
        UniqueConstraint("pipeline_id", "position", name="uq_crm_pipeline_stage_pipeline_position"),
        UniqueConstraint("pipeline_id", "name", name="uq_crm_pipeline_stage_pipeline_name"),
    )


class CRMOpportunity(Base):
    __tablename__ = "crm_opportunity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_pipeline_stage.id", ondelete="RESTRICT"),
        nullable=False,
    )
    selling_legal_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    region_code: Mapped[str] = mapped_column(String(32), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0, server_default="0")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    expected_close_date: Mapped[date | None] = mapped_column(nullable=True)
    probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forecast_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        default="Pipeline",
        server_default="Pipeline",
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_contact.id", ondelete="RESTRICT"),
        nullable=True,
    )
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revenue_quote_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    revenue_order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    revenue_handoff_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="NotRequested",
        server_default="NotRequested",
    )
    revenue_handoff_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revenue_handoff_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revenue_handoff_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revenue_handoff_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    account: Mapped[CRMAccount] = relationship("CRMAccount", back_populates="opportunities")
    stage: Mapped[CRMPipelineStage] = relationship("CRMPipelineStage", back_populates="opportunities")


class CRMActivity(Base):
    __tablename__ = "crm_activity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Open", server_default="Open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CRMNote(Base):
    __tablename__ = "crm_note"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(32), nullable=False, default="markdown", server_default="markdown")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CRMAttachmentLink(Base):
    __tablename__ = "crm_attachment_link"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CRMNotificationIntent(Base):
    __tablename__ = "crm_notification_intent"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    activity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Queued", server_default="Queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CRMJob(Base):
    __tablename__ = "crm_job"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Queued", server_default="Queued")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default=lambda: json.dumps({}))
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    artifacts: Mapped[list[CRMJobArtifact]] = relationship(
        "CRMJobArtifact",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CRMJobArtifact(Base):
    __tablename__ = "crm_job_artifact"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("crm_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    job: Mapped[CRMJob] = relationship("CRMJob", back_populates="artifacts")


class CRMCustomFieldDefinition(Base):
    __tablename__ = "crm_custom_field_definition"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "field_key",
            "legal_entity_id",
            name="uq_crm_custom_field_definition_scope",
        ),
    )


class CRMCustomFieldValue(Base):
    __tablename__ = "crm_custom_field_value"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_date: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "field_key",
            name="uq_crm_custom_field_value_entity_field",
        ),
    )


class CRMWorkflowRule(Base):
    __tablename__ = "crm_workflow_rule"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(128), nullable=False)
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    actions_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_crm_account_status", CRMAccount.status)
Index("ix_crm_account_owner_user_id", CRMAccount.owner_user_id)
Index("ix_crm_account_deleted_at", CRMAccount.deleted_at)
Index("ix_crm_account_legal_entity_account_id", CRMAccountLegalEntity.account_id)
Index("ix_crm_account_legal_entity_legal_entity_id", CRMAccountLegalEntity.legal_entity_id)
Index("ix_crm_contact_account_id", CRMContact.account_id)
Index("ix_crm_contact_email", CRMContact.email)
Index(
    "uq_crm_contact_primary_per_account_active",
    CRMContact.account_id,
    unique=True,
    postgresql_where=and_(CRMContact.is_primary.is_(True), CRMContact.deleted_at.is_(None)),
    sqlite_where=and_(CRMContact.is_primary.is_(True), CRMContact.deleted_at.is_(None)),
)
Index(
    "ix_crm_lead_scope_filter",
    CRMLead.selling_legal_entity_id,
    CRMLead.status,
    CRMLead.owner_user_id,
    CRMLead.created_at,
)
Index("ix_crm_lead_email", CRMLead.email)
Index("ix_crm_pipeline_selling_legal_entity_id", CRMPipeline.selling_legal_entity_id)
Index("ix_crm_pipeline_stage_pipeline_id", CRMPipelineStage.pipeline_id)
Index(
    "ix_crm_opportunity_scope_filter",
    CRMOpportunity.selling_legal_entity_id,
    CRMOpportunity.stage_id,
    CRMOpportunity.owner_user_id,
    CRMOpportunity.expected_close_date,
)
Index("ix_crm_opportunity_account_id", CRMOpportunity.account_id)
Index("ix_crm_activity_entity", CRMActivity.entity_type, CRMActivity.entity_id)
Index("ix_crm_activity_assignment", CRMActivity.assigned_to_user_id, CRMActivity.status, CRMActivity.due_at)
Index("ix_crm_note_entity", CRMNote.entity_type, CRMNote.entity_id)
Index("ix_crm_attachment_entity", CRMAttachmentLink.entity_type, CRMAttachmentLink.entity_id)
Index("ix_crm_attachment_file", CRMAttachmentLink.file_id)
Index(
    "ix_crm_notification_intent_recipient_status_created",
    CRMNotificationIntent.recipient_user_id,
    CRMNotificationIntent.status,
    CRMNotificationIntent.created_at,
)
Index("ix_crm_job_type_status_created", CRMJob.job_type, CRMJob.status, CRMJob.created_at)
Index("ix_crm_job_requested_by_created", CRMJob.requested_by_user_id, CRMJob.created_at)
Index("ix_crm_job_artifact_job_type", CRMJobArtifact.job_id, CRMJobArtifact.artifact_type)
Index(
    "ix_crm_custom_field_definition_entity_scope_active",
    CRMCustomFieldDefinition.entity_type,
    CRMCustomFieldDefinition.legal_entity_id,
    CRMCustomFieldDefinition.is_active,
)
Index("ix_crm_custom_field_value_entity", CRMCustomFieldValue.entity_type, CRMCustomFieldValue.entity_id)
Index("ix_crm_workflow_rule_trigger_active", CRMWorkflowRule.trigger_event, CRMWorkflowRule.is_active)
Index("ix_crm_workflow_rule_scope_active", CRMWorkflowRule.legal_entity_id, CRMWorkflowRule.is_active)

# NOTE: For PostgreSQL fuzzy search at scale, consider adding a GIN trigram index on crm_account.name.
