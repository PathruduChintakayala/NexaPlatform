from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PlanStatus = Literal["ACTIVE", "INACTIVE"]
BillingPeriod = Literal["MONTHLY", "YEARLY"]
SubscriptionStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "CANCELLED", "EXPIRED"]
SubscriptionChangeType = Literal["UPGRADE", "DOWNGRADE", "QUANTITY_CHANGE", "CANCEL", "SUSPEND", "RESUME", "RENEW"]


class PlanCreate(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str = Field(min_length=1)
    region_code: str | None = None
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    status: PlanStatus = "ACTIVE"
    billing_period: BillingPeriod
    default_pricebook_id: UUID | None = None


class PlanItemCreate(BaseModel):
    product_id: UUID
    pricebook_item_id: UUID
    quantity_default: Decimal = Field(gt=Decimal("0"))


class PlanItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    product_id: UUID
    pricebook_item_id: UUID
    quantity_default: Decimal | str
    unit_price_snapshot: Decimal | str
    created_at: datetime


class PlanRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    name: str
    code: str
    currency: str
    status: PlanStatus | str
    billing_period: BillingPeriod | str
    default_pricebook_id: UUID | None
    created_at: datetime
    items: list[PlanItemRead] = Field(default_factory=list)


class CreateSubscriptionFromContractRequest(BaseModel):
    plan_id: UUID | None = None
    account_id: UUID | None = None
    auto_renew: bool = True
    renewal_term_count: int = Field(default=1, ge=1)
    renewal_billing_period: BillingPeriod | None = None
    start_date: date | None = None


class SubscriptionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    product_id: UUID
    pricebook_item_id: UUID
    quantity: Decimal | str
    unit_price_snapshot: Decimal | str
    created_at: datetime


class SubscriptionRead(BaseModel):
    id: UUID
    tenant_id: str
    company_code: str
    region_code: str | None
    subscription_number: str
    contract_id: UUID
    account_id: UUID | None
    currency: str
    status: SubscriptionStatus | str
    start_date: date | None
    current_period_start: date | None
    current_period_end: date | None
    auto_renew: bool
    renewal_term_count: int
    renewal_billing_period: BillingPeriod | str
    created_at: datetime
    updated_at: datetime
    items: list[SubscriptionItemRead] = Field(default_factory=list)


class SubscriptionChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    change_type: SubscriptionChangeType | str
    effective_date: date
    payload_json: dict[str, Any] | None
    created_at: datetime


class ActivateSubscriptionRequest(BaseModel):
    start_date: date | None = None


class SuspendSubscriptionRequest(BaseModel):
    effective_date: date


class ResumeSubscriptionRequest(BaseModel):
    effective_date: date


class CancelSubscriptionRequest(BaseModel):
    effective_date: date
    reason: str | None = None


class ChangeQuantityRequest(BaseModel):
    new_qty: Decimal = Field(gt=Decimal("0"))
    effective_date: date
