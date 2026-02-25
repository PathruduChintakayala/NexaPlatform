from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.business.billing.schemas import (
    CreditNoteCreate,
    CreditNoteRead,
    InvoiceLineRead,
    InvoiceRead,
    MarkInvoicePaidRequest,
    RefreshOverdueResponse,
)
from app.business.billing.service import billing_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/billing", tags=["billing"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_billing_auth_context(
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


@router.post("/invoices/from-subscription/{subscription_id}", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice_from_subscription(
    subscription_id: uuid.UUID,
    period_start: date = Query(),
    period_end: date = Query(),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> InvoiceRead:
    return billing_service.generate_invoice_from_subscription(db, ctx, subscription_id, period_start, period_end)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceRead)
def issue_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> InvoiceRead:
    return billing_service.issue_invoice(db, ctx, invoice_id)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceRead)
def void_invoice(
    invoice_id: uuid.UUID,
    reason: str = Query(min_length=1),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> InvoiceRead:
    return billing_service.void_invoice(db, ctx, invoice_id, reason)


@router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceRead)
def mark_invoice_paid(
    invoice_id: uuid.UUID,
    payload: MarkInvoicePaidRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> InvoiceRead:
    return billing_service.mark_invoice_paid(db, ctx, invoice_id, payload)


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> list[InvoiceRead]:
    return billing_service.list_invoices(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> InvoiceRead:
    return billing_service.get_invoice(db, ctx, invoice_id)


@router.get("/invoices/{invoice_id}/lines", response_model=list[InvoiceLineRead])
def list_invoice_lines(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> list[InvoiceLineRead]:
    return billing_service.list_invoice_lines(db, ctx, invoice_id)


@router.post("/invoices/{invoice_id}/credit-notes", response_model=CreditNoteRead, status_code=status.HTTP_201_CREATED)
def create_credit_note(
    invoice_id: uuid.UUID,
    payload: CreditNoteCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> CreditNoteRead:
    return billing_service.apply_credit_note(db, ctx, invoice_id, payload)


@router.get("/credit-notes", response_model=list[CreditNoteRead])
def list_credit_notes(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> list[CreditNoteRead]:
    return billing_service.list_credit_notes(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.get("/credit-notes/{credit_note_id}", response_model=CreditNoteRead)
def get_credit_note(
    credit_note_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> CreditNoteRead:
    return billing_service.get_credit_note(db, ctx, credit_note_id)


@router.post("/invoices/{invoice_id}/refresh-overdue", response_model=RefreshOverdueResponse)
def refresh_overdue(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_billing_auth_context),
) -> RefreshOverdueResponse:
    return billing_service.refresh_overdue(db, ctx, invoice_id)
