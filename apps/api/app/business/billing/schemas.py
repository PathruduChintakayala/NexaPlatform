from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


InvoiceStatus = Literal["DRAFT", "ISSUED", "PAID", "VOID", "OVERDUE"]
CreditNoteStatus = Literal["DRAFT", "ISSUED", "APPLIED", "VOID"]


class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    product_id: UUID | None
    description: str | None
    quantity: Decimal | str
    unit_price_snapshot: Decimal | str
    line_total: Decimal | str
    source_type: str
    source_id: UUID | None


class InvoiceRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    invoice_number: str
    account_id: UUID | None
    subscription_id: UUID | None
    order_id: UUID | None
    currency: str
    status: InvoiceStatus | str
    issue_date: date | None
    due_date: date | None
    period_start: date | None
    period_end: date | None
    subtotal: Decimal | str
    discount_total: Decimal | str
    tax_total: Decimal | str
    total: Decimal | str
    amount_due: Decimal | str
    ledger_journal_entry_id: UUID | None
    created_at: datetime
    updated_at: datetime
    lines: list[InvoiceLineRead] = Field(default_factory=list)


class CreditNoteLineCreate(BaseModel):
    invoice_line_id: UUID | None = None
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price_snapshot: Decimal = Field(ge=Decimal("0"))


class CreditNoteCreate(BaseModel):
    issue_date: date | None = None
    tax_total: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    lines: list[CreditNoteLineCreate] = Field(min_length=1)


class CreditNoteLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    credit_note_id: UUID
    invoice_line_id: UUID | None
    description: str | None
    quantity: Decimal | str
    unit_price_snapshot: Decimal | str
    line_total: Decimal | str


class CreditNoteRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    credit_note_number: str
    invoice_id: UUID
    currency: str
    status: CreditNoteStatus | str
    issue_date: date | None
    subtotal: Decimal | str
    tax_total: Decimal | str
    total: Decimal | str
    ledger_journal_entry_id: UUID | None
    created_at: datetime
    lines: list[CreditNoteLineRead] = Field(default_factory=list)


class VoidInvoiceRequest(BaseModel):
    reason: str = Field(min_length=1)


class MarkInvoicePaidRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    paid_at: datetime | None = None


class RefreshOverdueResponse(BaseModel):
    invoice_id: UUID
    status: str
    overdue: bool


class EventInvoicePayload(BaseModel):
    subscription_id: UUID
    period_start: date | None = None
    period_end: date | None = None


class DunningCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    invoice_id: UUID
    status: str
    stage: int
    next_action_at: datetime | None
    created_at: datetime


class BillingEventRead(BaseModel):
    event_type: str
    payload_json: dict[str, Any] | None
