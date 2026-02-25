from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


LedgerAccountType = Literal["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"]
PostingStatus = Literal["POSTED", "REVERSED"]


class LedgerAccountCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    type: LedgerAccountType
    currency: str = Field(min_length=1)
    is_active: bool = True


class LedgerAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    company_code: str
    name: str
    code: str
    type: str
    currency: str
    is_active: bool
    created_at: datetime


class JournalLineInput(BaseModel):
    account_id: UUID
    debit_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    currency: str = Field(min_length=1)
    fx_rate_to_company_base: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    memo: str | None = None
    dimensions_json: dict[str, Any] | None = None


class JournalEntryPostRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    entry_date: date
    description: str = Field(min_length=1)
    source_module: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    created_by: str = Field(min_length=1)
    lines: list[JournalLineInput] = Field(min_length=2)


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    journal_entry_id: UUID
    account_id: UUID
    debit_amount: Decimal
    credit_amount: Decimal
    currency: str
    fx_rate_to_company_base: Decimal
    amount_company_base: Decimal
    memo: str | None
    dimensions_json: dict[str, Any] | None
    created_at: datetime


class JournalEntryRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    entry_date: date
    description: str
    source_module: str
    source_type: str
    source_id: str
    posting_status: PostingStatus
    created_by: str
    created_at: datetime
    lines: list[JournalLineRead] = Field(default_factory=list)


class JournalEntryReverseRequest(BaseModel):
    reason: str = Field(min_length=1)
    created_by: str = Field(min_length=1)


class SeedChartAccountsRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    currency: str = Field(min_length=1)
