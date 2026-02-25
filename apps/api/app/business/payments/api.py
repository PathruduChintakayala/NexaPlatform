from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.business.payments.schemas import (
    AllocatePaymentRequest,
    PaymentCreate,
    PaymentRead,
    PaymentAllocationRead,
    RefundCreate,
    RefundRead,
)
from app.business.payments.service import payments_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/payments", tags=["payments"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_payments_auth_context(
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


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> PaymentRead:
    return payments_service.create_payment(db, ctx, payload)


@router.post("/{payment_id}/allocate", response_model=PaymentRead)
def allocate_payment(
    payment_id: uuid.UUID,
    payload: AllocatePaymentRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> PaymentRead:
    return payments_service.allocate_payment(db, ctx, payment_id, payload)


@router.post("/{payment_id}/refund", response_model=RefundRead, status_code=status.HTTP_201_CREATED)
def refund_payment(
    payment_id: uuid.UUID,
    payload: RefundCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> RefundRead:
    return payments_service.refund_payment(db, ctx, payment_id, payload)


@router.get("", response_model=list[PaymentRead])
def list_payments(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> list[PaymentRead]:
    return payments_service.list_payments(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> PaymentRead:
    return payments_service.get_payment(db, ctx, payment_id)


@router.get("/{payment_id}/allocations", response_model=list[PaymentAllocationRead])
def list_allocations(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_payments_auth_context),
) -> list[PaymentAllocationRead]:
    return payments_service.list_allocations(db, ctx, payment_id)
