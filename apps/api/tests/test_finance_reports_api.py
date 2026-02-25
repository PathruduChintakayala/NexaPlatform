from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.billing.models import BillingInvoice
from app.business.payments.models import Payment
from app.core.auth import AuthUser, get_current_user
from app.core.database import Base, get_db
from app.main import app
from app.platform.ledger.models import JournalEntry, JournalLine, LedgerAccount
from app.platform.security.policies import InMemoryPolicyBackend, set_policy_backend


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


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user() -> AuthUser:
        return AuthUser(sub="report-api-user", roles=["user"])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))


def _headers(company_codes: str) -> dict[str, str]:
    return {
        "x-tenant-id": "tenant-a",
        "x-allowed-company-codes": company_codes,
    }


def _seed_data(session: Session) -> dict[str, str]:
    ar = LedgerAccount(
        tenant_id="tenant-a",
        company_code="C1",
        name="Accounts Receivable",
        code="1100",
        type="ASSET",
        currency="USD",
        is_active=True,
    )
    revenue = LedgerAccount(
        tenant_id="tenant-a",
        company_code="C1",
        name="Revenue",
        code="4000",
        type="REVENUE",
        currency="USD",
        is_active=True,
    )
    session.add_all([ar, revenue])
    session.flush()

    entry = JournalEntry(
        tenant_id="tenant-a",
        company_code="C1",
        entry_date=date(2026, 2, 15),
        description="Seed journal",
        source_module="billing",
        source_type="invoice",
        source_id="seed",
        posting_status="POSTED",
        created_by="seed",
    )
    session.add(entry)
    session.flush()
    session.add_all(
        [
            JournalLine(
                journal_entry_id=entry.id,
                account_id=ar.id,
                debit_amount=Decimal("60"),
                credit_amount=Decimal("0"),
                currency="USD",
                fx_rate_to_company_base=Decimal("1"),
                amount_company_base=Decimal("60"),
            ),
            JournalLine(
                journal_entry_id=entry.id,
                account_id=revenue.id,
                debit_amount=Decimal("0"),
                credit_amount=Decimal("60"),
                currency="USD",
                fx_rate_to_company_base=Decimal("1"),
                amount_company_base=Decimal("60"),
            ),
        ]
    )

    invoice = BillingInvoice(
        tenant_id="tenant-a",
        company_code="C1",
        region_code="NA",
        invoice_number="INV-C1-90001",
        account_id=None,
        subscription_id=None,
        order_id=None,
        currency="USD",
        status="ISSUED",
        issue_date=date(2026, 2, 15),
        due_date=date(2026, 2, 20),
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        subtotal=Decimal("60"),
        discount_total=Decimal("0"),
        tax_total=Decimal("0"),
        total=Decimal("60"),
        amount_due=Decimal("60"),
        ledger_journal_entry_id=entry.id,
    )
    payment = Payment(
        tenant_id="tenant-a",
        company_code="C1",
        region_code="NA",
        payment_number="PAY-C1-90001",
        account_id=None,
        currency="USD",
        amount=Decimal("60"),
        status="CONFIRMED",
        payment_method="MANUAL",
        received_at=datetime(2026, 2, 16, tzinfo=timezone.utc),
        ledger_journal_entry_id=entry.id,
    )
    session.add_all([invoice, payment])
    session.commit()

    return {
        "invoice_id": str(invoice.id),
        "payment_id": str(payment.id),
        "entry_id": str(entry.id),
    }


def test_finance_report_endpoints_and_drilldowns(client: TestClient, db_session: Session) -> None:
    ids = _seed_data(db_session)

    aging = client.get(
        "/reports/finance/ar-aging",
        params={"tenant_id": "tenant-a", "company_code": "C1", "as_of_date": "2026-02-25"},
        headers=_headers("C1"),
    )
    assert aging.status_code == 200
    assert aging.json()["total_amount_due"] == "60.000000"

    trial = client.get(
        "/reports/finance/trial-balance",
        params={"tenant_id": "tenant-a", "company_code": "C1", "start_date": "2026-02-01", "end_date": "2026-02-28"},
        headers=_headers("C1"),
    )
    assert trial.status_code == 200

    reconciliation = client.get(
        "/reports/finance/reconciliation",
        params={"tenant_id": "tenant-a", "company_code": "C1", "start_date": "2026-02-01", "end_date": "2026-02-28"},
        headers=_headers("C1"),
    )
    assert reconciliation.status_code == 200

    invoice_drill = client.get(f"/reports/finance/drilldowns/invoices/{ids['invoice_id']}", headers=_headers("C1"))
    assert invoice_drill.status_code == 200

    payment_drill = client.get(f"/reports/finance/drilldowns/payments/{ids['payment_id']}", headers=_headers("C1"))
    assert payment_drill.status_code == 200

    journal_drill = client.get(f"/reports/finance/drilldowns/journal-entries/{ids['entry_id']}", headers=_headers("C1"))
    assert journal_drill.status_code == 200

    journal_get = client.get(f"/ledger/journal-entries/{ids['entry_id']}", headers=_headers("C1"))
    assert journal_get.status_code == 200


def test_finance_report_fls_masks_total(client: TestClient, db_session: Session) -> None:
    _seed_data(db_session)
    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={
                "user": {
                    "reports.finance.summary.field.read:*",
                    "reports.finance.summary.field.mask:total_amount_due",
                }
            },
            default_allow=False,
        )
    )

    response = client.get(
        "/reports/finance/ar-aging",
        params={"tenant_id": "tenant-a", "company_code": "C1", "as_of_date": "2026-02-25"},
        headers=_headers("C1"),
    )
    assert response.status_code == 200
    assert response.json()["total_amount_due"] == "***"
