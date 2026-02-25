from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.business.subscription.schemas import (
    ActivateSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeQuantityRequest,
    CreateSubscriptionFromContractRequest,
    PlanCreate,
    PlanItemCreate,
    PlanItemRead,
    PlanRead,
    ResumeSubscriptionRequest,
    SubscriptionChangeRead,
    SubscriptionRead,
    SuspendSubscriptionRequest,
)
from app.business.subscription.service import subscription_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_subscription_auth_context(
    request: Request,
    auth_user: AuthUser = Depends(get_auth_user),
    tenant_id_header: str | None = Header(default=None, alias="x-tenant-id"),
    company_scope_header: str | None = Header(default=None, alias="x-allowed-company-codes"),
    region_scope_header: str | None = Header(default=None, alias="x-allowed-regions"),
) -> AuthContext:
    correlation_id = get_correlation_id() or getattr(getattr(request.state, "context", None), "request_id", None)
    roles = [str(item) for item in auth_user.roles]
    normalized = {item.lower() for item in roles}

    return AuthContext(
        user_id=auth_user.sub,
        tenant_id=tenant_id_header,
        correlation_id=correlation_id,
        is_super_admin=("admin" in normalized or "system.admin" in normalized),
        roles=roles,
        permissions=roles,
        entity_scope=_parse_str_list(company_scope_header),
        region_scope=_parse_str_list(region_scope_header),
    )


@router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> PlanRead:
    return subscription_service.create_plan(db, ctx, payload)


@router.post("/plans/{plan_id}/items", response_model=PlanItemRead, status_code=status.HTTP_201_CREATED)
def add_plan_item(
    plan_id: uuid.UUID,
    payload: PlanItemCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> PlanItemRead:
    return subscription_service.add_plan_item(db, ctx, plan_id, payload)


@router.get("/plans", response_model=list[PlanRead])
def list_plans(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> list[PlanRead]:
    return subscription_service.list_plans(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/plans/{plan_id}", response_model=PlanRead)
def get_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> PlanRead:
    return subscription_service.get_plan(db, ctx, plan_id)


@router.post("/from-contract/{contract_id}", response_model=SubscriptionRead, status_code=status.HTTP_201_CREATED)
def create_subscription_from_contract(
    contract_id: uuid.UUID,
    payload: CreateSubscriptionFromContractRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.create_subscription_from_contract(db, ctx, contract_id, payload)


@router.post("/{subscription_id}/activate", response_model=SubscriptionRead)
def activate_subscription(
    subscription_id: uuid.UUID,
    payload: ActivateSubscriptionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.activate_subscription(db, ctx, subscription_id, payload)


@router.post("/{subscription_id}/suspend", response_model=SubscriptionRead)
def suspend_subscription(
    subscription_id: uuid.UUID,
    payload: SuspendSubscriptionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.suspend_subscription(db, ctx, subscription_id, payload)


@router.post("/{subscription_id}/resume", response_model=SubscriptionRead)
def resume_subscription(
    subscription_id: uuid.UUID,
    payload: ResumeSubscriptionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.resume_subscription(db, ctx, subscription_id, payload)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionRead)
def cancel_subscription(
    subscription_id: uuid.UUID,
    payload: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.cancel_subscription(db, ctx, subscription_id, payload)


@router.post("/{subscription_id}/renew", response_model=SubscriptionRead)
def renew_subscription(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.renew_subscription(db, ctx, subscription_id)


@router.post("/{subscription_id}/items/{product_id}/quantity", response_model=SubscriptionRead)
def change_quantity(
    subscription_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ChangeQuantityRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.change_quantity(db, ctx, subscription_id, product_id, payload)


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> list[SubscriptionRead]:
    return subscription_service.list_subscriptions(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/{subscription_id}", response_model=SubscriptionRead)
def get_subscription(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> SubscriptionRead:
    return subscription_service.get_subscription(db, ctx, subscription_id)


@router.get("/{subscription_id}/changes", response_model=list[SubscriptionChangeRead])
def list_changes(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_subscription_auth_context),
) -> list[SubscriptionChangeRead]:
    return subscription_service.list_subscription_changes(db, ctx, subscription_id)
