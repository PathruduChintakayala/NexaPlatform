from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.business.revenue.schemas import (
    RevenueContractRead,
    RevenueOrderRead,
    RevenueQuoteCreate,
    RevenueQuoteLineCreate,
    RevenueQuoteLineRead,
    RevenueQuoteRead,
)
from app.business.revenue.service import revenue_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/revenue", tags=["revenue"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_revenue_auth_context(
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


@router.post("/quotes", response_model=RevenueQuoteRead, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: RevenueQuoteCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueQuoteRead:
    return revenue_service.create_quote(db, ctx, payload)


@router.post("/quotes/{quote_id}/lines", response_model=RevenueQuoteLineRead, status_code=status.HTTP_201_CREATED)
def add_quote_line(
    quote_id: uuid.UUID,
    payload: RevenueQuoteLineCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueQuoteLineRead:
    return revenue_service.add_quote_line(db, ctx, quote_id, payload)


@router.post("/quotes/{quote_id}/send", response_model=RevenueQuoteRead)
def send_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueQuoteRead:
    return revenue_service.send_quote(db, ctx, quote_id)


@router.post("/quotes/{quote_id}/accept", response_model=RevenueQuoteRead)
def accept_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueQuoteRead:
    return revenue_service.accept_quote(db, ctx, quote_id)


@router.post("/quotes/{quote_id}/create-order", response_model=RevenueOrderRead, status_code=status.HTTP_201_CREATED)
def create_order_from_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueOrderRead:
    return revenue_service.create_order_from_quote(db, ctx, quote_id)


@router.post("/orders/{order_id}/confirm", response_model=RevenueOrderRead)
def confirm_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueOrderRead:
    return revenue_service.confirm_order(db, ctx, order_id)


@router.post("/orders/{order_id}/create-contract", response_model=RevenueContractRead, status_code=status.HTTP_201_CREATED)
def create_contract_from_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueContractRead:
    return revenue_service.create_contract_from_order(db, ctx, order_id)


@router.get("/quotes", response_model=list[RevenueQuoteRead])
def list_quotes(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> list[RevenueQuoteRead]:
    return revenue_service.list_quotes(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/quotes/{quote_id}", response_model=RevenueQuoteRead)
def get_quote(
    quote_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueQuoteRead:
    return revenue_service.get_quote(db, ctx, quote_id)


@router.get("/orders", response_model=list[RevenueOrderRead])
def list_orders(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> list[RevenueOrderRead]:
    return revenue_service.list_orders(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/orders/{order_id}", response_model=RevenueOrderRead)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueOrderRead:
    return revenue_service.get_order(db, ctx, order_id)


@router.get("/contracts", response_model=list[RevenueContractRead])
def list_contracts(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> list[RevenueContractRead]:
    return revenue_service.list_contracts(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/contracts/{contract_id}", response_model=RevenueContractRead)
def get_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_revenue_auth_context),
) -> RevenueContractRead:
    return revenue_service.get_contract(db, ctx, contract_id)
