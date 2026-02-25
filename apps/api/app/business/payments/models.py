from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    __tablename__ = "payments_payment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_number: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CONFIRMED", server_default="CONFIRMED")
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ledger_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    allocations: Mapped[list[PaymentAllocation]] = relationship(
        "app.business.payments.models.PaymentAllocation",
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    refunds: Mapped[list[Refund]] = relationship(
        "app.business.payments.models.Refund",
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "payment_number", name="uq_payments_payment_number_company"),
        Index("ix_payments_payment_scope", "tenant_id", "company_code"),
    )


class PaymentAllocation(Base):
    __tablename__ = "payments_allocation"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments_payment.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    amount_allocated: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    payment: Mapped[Payment] = relationship("app.business.payments.models.Payment", back_populates="allocations")

    __table_args__ = (
        Index("ix_payments_allocation_invoice", "invoice_id"),
        Index("ix_payments_allocation_payment", "payment_id"),
    )


class Refund(Base):
    __tablename__ = "payments_refund"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments_payment.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CONFIRMED", server_default="CONFIRMED")
    ledger_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    payment: Mapped[Payment] = relationship("app.business.payments.models.Payment", back_populates="refunds")

    __table_args__ = (
        Index("ix_payments_refund_scope", "tenant_id", "company_code"),
        Index("ix_payments_refund_payment", "payment_id"),
    )
