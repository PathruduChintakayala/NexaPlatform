from __future__ import annotations

from datetime import date
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
from app.platform.security.context import AuthContext
from app.platform.ledger.schemas import (
    JournalEntryPostRequest,
    JournalEntryRead,
    JournalEntryReverseRequest,
    LedgerAccountCreate,
    LedgerAccountRead,
    SeedChartAccountsRequest,
)
from app.platform.ledger.service import ledger_service


router = APIRouter(prefix="/ledger", tags=["ledger"])


def _parse_str_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_ledger_auth_context(
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


@router.post("/accounts", response_model=LedgerAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: LedgerAccountCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> LedgerAccountRead:
    return ledger_service.create_account(db, ctx, payload)


@router.get("/accounts", response_model=list[LedgerAccountRead])
def list_accounts(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> list[LedgerAccountRead]:
    return ledger_service.list_accounts(db, ctx, tenant_id=tenant_id, company_code=company_code)


@router.post("/journal-entries", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
def post_journal_entry(
    payload: JournalEntryPostRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> JournalEntryRead:
    return ledger_service.post_entry(db, ctx, payload)


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryRead)
def reverse_journal_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> JournalEntryRead:
    return ledger_service.reverse_entry(db, ctx, entry_id, payload)


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> JournalEntryRead:
    return ledger_service.get_entry(db, ctx, entry_id)


@router.get("/journal-entries", response_model=list[JournalEntryRead])
def list_journal_entries(
    tenant_id: str = Query(min_length=1),
    company_code: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_module: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> list[JournalEntryRead]:
    return ledger_service.list_entries(
        db,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        start_date=start_date,
        end_date=end_date,
        source_module=source_module,
        source_type=source_type,
        source_id=source_id,
    )


@router.post("/seeds/chart-of-accounts", response_model=list[LedgerAccountRead])
def seed_chart_of_accounts(
    payload: SeedChartAccountsRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_ledger_auth_context),
) -> list[LedgerAccountRead]:
    return ledger_service.seed_chart_of_accounts(
        db,
        ctx,
        tenant_id=payload.tenant_id,
        company_code=payload.company_code,
        currency=payload.currency,
    )
