from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.business.catalog.schemas import (
    CatalogPriceRead,
    CatalogPricebookCreate,
    CatalogPricebookItemRead,
    CatalogPricebookItemUpsert,
    CatalogPricebookRead,
    CatalogProductCreate,
    CatalogProductRead,
)
from app.business.catalog.service import catalog_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/catalog", tags=["catalog"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_catalog_auth_context(
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


@router.post("/products", response_model=CatalogProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: CatalogProductCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> CatalogProductRead:
    return catalog_service.create_product(db, ctx, payload)


@router.get("/products", response_model=list[CatalogProductRead])
def list_products(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> list[CatalogProductRead]:
    return catalog_service.list_products(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.post("/pricebooks", response_model=CatalogPricebookRead, status_code=status.HTTP_201_CREATED)
def create_pricebook(
    payload: CatalogPricebookCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> CatalogPricebookRead:
    return catalog_service.create_pricebook(db, ctx, payload)


@router.get("/pricebooks", response_model=list[CatalogPricebookRead])
def list_pricebooks(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    currency: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> list[CatalogPricebookRead]:
    return catalog_service.list_pricebooks(db, ctx, tenant_id=tenant_id, company_code=company_code, currency=currency)


@router.put("/pricebook-items", response_model=CatalogPricebookItemRead)
def upsert_pricebook_item(
    payload: CatalogPricebookItemUpsert,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> CatalogPricebookItemRead:
    return catalog_service.upsert_pricebook_item(db, ctx, payload)


@router.get("/price", response_model=CatalogPriceRead)
def get_price(
    tenant_id: str = Query(min_length=1),
    company_code: str = Query(min_length=1),
    sku: str = Query(min_length=1),
    currency: str = Query(min_length=1),
    billing_period: str = Query(min_length=1),
    at_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_catalog_auth_context),
) -> CatalogPriceRead:
    return catalog_service.get_price(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        sku=sku,
        currency=currency,
        billing_period=billing_period,
        at_date=at_date,
    )
