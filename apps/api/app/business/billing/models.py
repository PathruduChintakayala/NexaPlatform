from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BillingInvoice(Base):
    __tablename__ = "billing_invoice"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    issue_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date(), nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date(), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    ledger_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    lines: Mapped[list[BillingInvoiceLine]] = relationship(
        "app.business.billing.models.BillingInvoiceLine",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "invoice_number", name="uq_billing_invoice_number_company"),
        Index("ix_billing_invoice_scope_date", "tenant_id", "company_code", "created_at"),
    )


class BillingInvoiceLine(Base):
    __tablename__ = "billing_invoice_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    invoice: Mapped[BillingInvoice] = relationship("app.business.billing.models.BillingInvoice", back_populates="lines")

    __table_args__ = (
        Index("ix_billing_invoice_line_invoice", "invoice_id"),
        Index("ix_billing_invoice_line_product", "product_id"),
    )


class BillingCreditNote(Base):
    __tablename__ = "billing_credit_note"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_note_number: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_invoice.id", ondelete="RESTRICT"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    issue_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    ledger_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    lines: Mapped[list[BillingCreditNoteLine]] = relationship(
        "app.business.billing.models.BillingCreditNoteLine",
        back_populates="credit_note",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "credit_note_number", name="uq_billing_credit_note_number_company"),
        Index("ix_billing_credit_note_scope_date", "tenant_id", "company_code", "created_at"),
    )


class BillingCreditNoteLine(Base):
    __tablename__ = "billing_credit_note_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_credit_note.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_invoice_line.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    credit_note: Mapped[BillingCreditNote] = relationship("app.business.billing.models.BillingCreditNote", back_populates="lines")


class BillingDunningCase(Base):
    __tablename__ = "billing_dunning_case"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("billing_invoice.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", server_default="OPEN")
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_billing_dunning_scope", "tenant_id", "company_code", "created_at"),
    )
