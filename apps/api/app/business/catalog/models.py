from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CatalogProduct(Base):
    __tablename__ = "catalog_product"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    pricebook_items: Mapped[list[CatalogPricebookItem]] = relationship(
        "CatalogPricebookItem",
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_code", "sku", name="uq_catalog_product_sku"),
        Index("ix_catalog_product_scope", "tenant_id", "company_code", "is_active"),
    )


class CatalogPricebook(Base):
    __tablename__ = "catalog_pricebook"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    valid_from: Mapped[date | None] = mapped_column(Date(), nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    items: Mapped[list[CatalogPricebookItem]] = relationship(
        "CatalogPricebookItem",
        back_populates="pricebook",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_code", "name", name="uq_catalog_pricebook_name"),
        Index("ix_catalog_pricebook_scope", "tenant_id", "company_code", "currency", "is_active"),
    )


class CatalogPricebookItem(Base):
    __tablename__ = "catalog_pricebook_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pricebook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("catalog_pricebook.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("catalog_product.id", ondelete="CASCADE"),
        nullable=False,
    )
    billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    pricebook: Mapped[CatalogPricebook] = relationship("CatalogPricebook", back_populates="items")
    product: Mapped[CatalogProduct] = relationship("CatalogProduct", back_populates="pricebook_items")

    __table_args__ = (
        UniqueConstraint(
            "pricebook_id",
            "product_id",
            "billing_period",
            "currency",
            name="uq_catalog_pricebook_item_key",
        ),
        Index("ix_catalog_pricebook_item_pricebook", "pricebook_id", "product_id"),
        Index("ix_catalog_pricebook_item_lookup", "currency", "billing_period", "is_active"),
    )
