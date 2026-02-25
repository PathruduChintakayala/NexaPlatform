from __future__ import annotations

from decimal import Decimal
import uuid
from collections.abc import Generator

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.platform.ledger.models import JournalEntry, LedgerAccount
from app.platform.ledger.schemas import JournalEntryPostRequest, JournalEntryReverseRequest
from app.platform.ledger.service import LedgerService
from app.platform.security.context import AuthContext


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _create_account(session: Session, tenant_id: str, company_code: str, code: str, account_type: str, currency: str) -> LedgerAccount:
    account = LedgerAccount(
        tenant_id=tenant_id,
        company_code=company_code,
        name=code,
        code=code,
        type=account_type,
        currency=currency,
        is_active=True,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def test_balanced_entry_validation_rejects_unbalanced(db_session: Session) -> None:
    cash = _create_account(db_session, "tenant-a", "C1", "1000", "ASSET", "USD")
    rev = _create_account(db_session, "tenant-a", "C1", "4000", "REVENUE", "USD")

    service = LedgerService()
    ctx = AuthContext(user_id="u1", tenant_id="tenant-a", entity_scope=["C1"])

    request = JournalEntryPostRequest.model_validate(
        {
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "entry_date": "2026-02-25",
            "description": "Unbalanced",
            "source_module": "crm",
            "source_type": "invoice",
            "source_id": "inv-1",
            "created_by": "u1",
            "lines": [
                {"account_id": str(cash.id), "debit_amount": "100", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                {"account_id": str(rev.id), "debit_amount": "0", "credit_amount": "90", "currency": "USD", "fx_rate_to_company_base": "1"},
            ],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        service.post_entry(db_session, ctx, request)
    assert exc_info.value.status_code == 422


def test_fx_conversion_to_company_base(db_session: Session) -> None:
    cash = _create_account(db_session, "tenant-a", "C1", "1000", "ASSET", "USD")
    rev = _create_account(db_session, "tenant-a", "C1", "4000", "REVENUE", "USD")

    service = LedgerService()
    ctx = AuthContext(user_id="u1", tenant_id="tenant-a", entity_scope=["C1"])

    request = JournalEntryPostRequest.model_validate(
        {
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "entry_date": "2026-02-25",
            "description": "FX Entry",
            "source_module": "crm",
            "source_type": "invoice",
            "source_id": "inv-2",
            "created_by": "u1",
            "lines": [
                {"account_id": str(cash.id), "debit_amount": "100", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                {"account_id": str(rev.id), "debit_amount": "0", "credit_amount": "80", "currency": "EUR", "fx_rate_to_company_base": "1.25"},
            ],
        }
    )

    posted = service.post_entry(db_session, ctx, request)
    assert len(posted.lines) == 2
    eur_line = next(line for line in posted.lines if line.currency == "EUR")
    assert eur_line.amount_company_base == Decimal("100.000000")


def test_reverse_entry_swaps_debit_credit_and_marks_original(db_session: Session) -> None:
    cash = _create_account(db_session, "tenant-a", "C1", "1000", "ASSET", "USD")
    rev = _create_account(db_session, "tenant-a", "C1", "4000", "REVENUE", "USD")

    service = LedgerService()
    ctx = AuthContext(user_id="u1", tenant_id="tenant-a", entity_scope=["C1"])

    posted = service.post_entry(
        db_session,
        ctx,
        JournalEntryPostRequest.model_validate(
            {
                "tenant_id": "tenant-a",
                "company_code": "C1",
                "entry_date": "2026-02-25",
                "description": "Reverse Me",
                "source_module": "crm",
                "source_type": "invoice",
                "source_id": "inv-3",
                "created_by": "u1",
                "lines": [
                    {"account_id": str(cash.id), "debit_amount": "50", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                    {"account_id": str(rev.id), "debit_amount": "0", "credit_amount": "50", "currency": "USD", "fx_rate_to_company_base": "1"},
                ],
            }
        ),
    )

    reversed_entry = service.reverse_entry(
        db_session,
        ctx,
        posted.id,
        JournalEntryReverseRequest(reason="cancel", created_by="u1"),
    )

    original = db_session.scalar(select(JournalEntry).where(JournalEntry.id == posted.id))
    assert original is not None
    assert original.posting_status == "REVERSED"

    reverse_debits = sum(line.debit_amount for line in reversed_entry.lines)
    reverse_credits = sum(line.credit_amount for line in reversed_entry.lines)
    assert reverse_debits == Decimal("50.000000")
    assert reverse_credits == Decimal("50.000000")
