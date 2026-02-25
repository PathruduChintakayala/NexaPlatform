from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


QuoteStatus = Literal["DRAFT", "SENT", "ACCEPTED", "REJECTED", "EXPIRED"]
OrderStatus = Literal["DRAFT", "CONFIRMED", "FULFILLED", "CANCELLED"]
ContractStatus = Literal["ACTIVE", "SUSPENDED", "TERMINATED", "EXPIRED"]


class RevenueQuoteCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    region_code: str | None = None
    account_id: UUID | None = None
    currency: str = Field(min_length=1)
    valid_until: date | None = None
    discount_total: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    tax_total: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class RevenueQuoteLineCreate(BaseModel):
    product_id: UUID
    pricebook_item_id: UUID
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))


class RevenueQuoteLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_id: UUID
    product_id: UUID
    pricebook_item_id: UUID
    description: str | None
    quantity: Decimal
    unit_price: Decimal | str
    line_total: Decimal | str


class RevenueQuoteRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    quote_number: str
    account_id: UUID | None
    currency: str
    status: QuoteStatus | str
    valid_until: date | None
    subtotal: Decimal | str
    discount_total: Decimal | str
    tax_total: Decimal | str
    total: Decimal | str
    created_by: str
    created_at: datetime
    updated_at: datetime
    lines: list[RevenueQuoteLineRead] = Field(default_factory=list)


class RevenueOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    pricebook_item_id: UUID
    quantity: Decimal
    unit_price: Decimal | str
    line_total: Decimal | str
    service_start: date | None
    service_end: date | None


class RevenueOrderRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    order_number: str
    quote_id: UUID | None
    currency: str
    status: OrderStatus | str
    subtotal: Decimal | str
    discount_total: Decimal | str
    tax_total: Decimal | str
    total: Decimal | str
    created_by: str
    created_at: datetime
    updated_at: datetime
    lines: list[RevenueOrderLineRead] = Field(default_factory=list)


class RevenueContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    contract_number: str
    order_id: UUID
    status: ContractStatus | str
    start_date: date | None
    end_date: date | None
    created_at: datetime
