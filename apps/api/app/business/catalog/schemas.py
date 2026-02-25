from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


BillingPeriod = Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "ANNUAL"]


class CatalogProductCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    region_code: str | None = None
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    default_currency: str = Field(min_length=1)
    is_active: bool = True


class CatalogProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    sku: str
    name: str
    description: str | None
    default_currency: str
    is_active: bool
    created_at: datetime


class CatalogPricebookCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    region_code: str | None = None
    name: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    is_default: bool = False
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool = True


class CatalogPricebookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    name: str
    currency: str
    is_default: bool
    valid_from: date | None
    valid_to: date | None
    is_active: bool
    created_at: datetime


class CatalogPricebookItemUpsert(BaseModel):
    pricebook_id: UUID
    product_id: UUID
    billing_period: BillingPeriod
    currency: str = Field(min_length=1)
    unit_price: Decimal = Field(gt=Decimal("0"))
    is_active: bool = True


class CatalogPricebookItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pricebook_id: UUID
    product_id: UUID
    billing_period: BillingPeriod
    currency: str
    unit_price: Decimal
    is_active: bool
    created_at: datetime


class CatalogPriceRead(BaseModel):
    tenant_id: str
    company_code: str
    sku: str
    product_id: UUID
    pricebook_id: UUID
    currency: str
    billing_period: BillingPeriod
    unit_price: Decimal | str
    valid_from: date | None
    valid_to: date | None
