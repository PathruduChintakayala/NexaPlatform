from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PaymentStatus = Literal["INITIATED", "CONFIRMED", "FAILED", "REFUNDED"]
RefundStatus = Literal["INITIATED", "CONFIRMED"]
PaymentMethod = Literal["MANUAL", "BANK_TRANSFER", "CARD"]


class PaymentAllocationCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=Decimal("0"))


class PaymentCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    region_code: str | None = None
    account_id: UUID | None = None
    currency: str = Field(min_length=1)
    amount: Decimal = Field(gt=Decimal("0"))
    payment_method: PaymentMethod
    received_at: datetime | None = None
    fx_rate_to_company_base: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    allocations: list[PaymentAllocationCreate] = Field(default_factory=list)


class AllocatePaymentRequest(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=Decimal("0"))


class RefundCreate(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str = Field(min_length=1)
    fx_rate_to_company_base: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))


class PaymentAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    invoice_id: UUID
    amount_allocated: Decimal | str
    created_at: datetime


class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    payment_id: UUID
    amount: Decimal | str
    reason: str
    status: RefundStatus | str
    ledger_journal_entry_id: UUID | None
    created_at: datetime


class PaymentRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    payment_number: str
    account_id: UUID | None
    currency: str
    amount: Decimal | str
    status: PaymentStatus | str
    payment_method: PaymentMethod | str
    received_at: datetime | None
    ledger_journal_entry_id: UUID | None
    created_at: datetime
    allocations: list[PaymentAllocationRead] = Field(default_factory=list)
    refunds: list[RefundRead] = Field(default_factory=list)
