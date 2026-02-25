from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RevenueQuote(Base):
    __tablename__ = "revenue_quote"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quote_number: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    valid_until: Mapped[date | None] = mapped_column(Date(), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    lines: Mapped[list[RevenueQuoteLine]] = relationship(
        "app.business.revenue.models.RevenueQuoteLine",
        back_populates="quote",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "quote_number", name="uq_revenue_quote_number_company"),
        Index("ix_revenue_quote_scope_date", "tenant_id", "company_code", "created_at"),
    )


class RevenueQuoteLine(Base):
    __tablename__ = "revenue_quote_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("revenue_quote.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pricebook_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    quote: Mapped[RevenueQuote] = relationship("app.business.revenue.models.RevenueQuote", back_populates="lines")

    __table_args__ = (
        Index("ix_revenue_quote_line_quote_id", "quote_id"),
    )


class RevenueOrder(Base):
    __tablename__ = "revenue_order"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_number: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    lines: Mapped[list[RevenueOrderLine]] = relationship(
        "app.business.revenue.models.RevenueOrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "order_number", name="uq_revenue_order_number_company"),
        Index("ix_revenue_order_scope_date", "tenant_id", "company_code", "created_at"),
    )


class RevenueOrderLine(Base):
    __tablename__ = "revenue_order_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("revenue_order.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pricebook_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    service_start: Mapped[date | None] = mapped_column(Date(), nullable=True)
    service_end: Mapped[date | None] = mapped_column(Date(), nullable=True)

    order: Mapped[RevenueOrder] = relationship("app.business.revenue.models.RevenueOrder", back_populates="lines")

    __table_args__ = (
        Index("ix_revenue_order_line_order_id", "order_id"),
    )


class RevenueContract(Base):
    __tablename__ = "revenue_contract"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_number: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("company_code", "contract_number", name="uq_revenue_contract_number_company"),
        Index("ix_revenue_contract_scope_date", "tenant_id", "company_code", "created_at"),
    )
