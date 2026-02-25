from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plan"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    default_pricebook_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    items: Mapped[list[SubscriptionPlanItem]] = relationship(
        "app.business.subscription.models.SubscriptionPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "code", name="uq_subscription_plan_code_company"),
        Index("ix_subscription_plan_scope_date", "tenant_id", "company_code", "created_at"),
    )


class SubscriptionPlanItem(Base):
    __tablename__ = "subscription_plan_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("subscription_plan.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pricebook_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity_default: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    plan: Mapped[SubscriptionPlan] = relationship("app.business.subscription.models.SubscriptionPlan", back_populates="items")

    __table_args__ = (
        UniqueConstraint("plan_id", "product_id", name="uq_subscription_plan_item_product"),
        Index("ix_subscription_plan_item_plan", "plan_id"),
    )


class Subscription(Base):
    __tablename__ = "subscription"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_number: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    current_period_start: Mapped[date | None] = mapped_column(Date(), nullable=True)
    current_period_end: Mapped[date | None] = mapped_column(Date(), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    renewal_term_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    renewal_billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    items: Mapped[list[SubscriptionItem]] = relationship(
        "app.business.subscription.models.SubscriptionItem",
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    changes: Mapped[list[SubscriptionChange]] = relationship(
        "app.business.subscription.models.SubscriptionChange",
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("company_code", "subscription_number", name="uq_subscription_number_company"),
        Index("ix_subscription_scope_date", "tenant_id", "company_code", "created_at"),
    )


class SubscriptionItem(Base):
    __tablename__ = "subscription_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("subscription.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    pricebook_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    subscription: Mapped[Subscription] = relationship("app.business.subscription.models.Subscription", back_populates="items")

    __table_args__ = (
        UniqueConstraint("subscription_id", "product_id", name="uq_subscription_item_product"),
        Index("ix_subscription_item_subscription", "subscription_id"),
    )


class SubscriptionChange(Base):
    __tablename__ = "subscription_change"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("subscription.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date(), nullable=False)
    payload_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    subscription: Mapped[Subscription] = relationship("app.business.subscription.models.Subscription", back_populates="changes")

    __table_args__ = (
        Index("ix_subscription_change_subscription", "subscription_id", "created_at"),
    )
