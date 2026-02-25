from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.business.reporting.finance.schemas import (
    ARAgingReportRead,
    CashSummaryReportRead,
    InvoiceDrilldownRead,
    JournalDrilldownRead,
    PaymentDrilldownRead,
    ReconciliationReportRead,
    RevenueSummaryReportRead,
    TrialBalanceReportRead,
)
from app.business.reporting.finance.service import finance_reporting_service
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext


router = APIRouter(prefix="/reports/finance", tags=["reports", "finance"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_reporting_auth_context(
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


@router.get("/ar-aging", response_model=ARAgingReportRead)
def ar_aging(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    as_of_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> ARAgingReportRead:
    return finance_reporting_service.ar_aging(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        as_of_date=as_of_date,
    )


@router.get("/trial-balance", response_model=TrialBalanceReportRead)
def trial_balance(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> TrialBalanceReportRead:
    return finance_reporting_service.trial_balance(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/cash-summary", response_model=CashSummaryReportRead)
def cash_summary(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> CashSummaryReportRead:
    return finance_reporting_service.cash_summary(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/revenue-summary", response_model=RevenueSummaryReportRead)
def revenue_summary(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> RevenueSummaryReportRead:
    return finance_reporting_service.revenue_summary(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/reconciliation", response_model=ReconciliationReportRead)
def reconciliation(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> ReconciliationReportRead:
    return finance_reporting_service.reconciliation(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/drilldowns/invoices/{invoice_id}", response_model=InvoiceDrilldownRead)
def invoice_drilldown(
    invoice_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> InvoiceDrilldownRead:
    return finance_reporting_service.invoice_drilldown(db, ctx, invoice_id)


@router.get("/drilldowns/payments/{payment_id}", response_model=PaymentDrilldownRead)
def payment_drilldown(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> PaymentDrilldownRead:
    return finance_reporting_service.payment_drilldown(db, ctx, payment_id)


@router.get("/drilldowns/journal-entries/{entry_id}", response_model=JournalDrilldownRead)
def journal_drilldown(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_reporting_auth_context),
) -> JournalDrilldownRead:
    return finance_reporting_service.journal_drilldown(db, ctx, entry_id)
