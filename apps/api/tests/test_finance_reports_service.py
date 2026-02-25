from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.billing.models import BillingCreditNote, BillingInvoice
from app.business.payments.models import Payment, PaymentAllocation
from app.business.reporting.finance.service import finance_reporting_service
from app.core.database import Base
from app.platform.ledger.models import JournalEntry, JournalLine, LedgerAccount
from app.platform.security.context import AuthContext
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


@pytest.fixture(autouse=True)
def reset_policy_backend() -> Generator[None, None, None]:
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    yield
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))


def _ctx(company: str = "C1") -> AuthContext:
    return AuthContext(user_id="report-user", tenant_id="tenant-a", entity_scope=[company], roles=["user"], permissions=["user"])


def _seed_report_data(session: Session) -> dict[str, uuid.UUID]:
    ar = LedgerAccount(
        tenant_id="tenant-a",
        company_code="C1",
        name="Accounts Receivable",
        code="1100",
        type="ASSET",
        currency="USD",
        is_active=True,
    )
    rev = LedgerAccount(
        tenant_id="tenant-a",
        company_code="C1",
        name="Revenue",
        code="4000",
        type="REVENUE",
        currency="USD",
        is_active=True,
    )
    cash = LedgerAccount(
        tenant_id="tenant-a",
        company_code="C1",
        name="Cash",
        code="1000",
        type="ASSET",
        currency="USD",
        is_active=True,
    )
    session.add_all([ar, rev, cash])
    session.flush()

    je = JournalEntry(
        tenant_id="tenant-a",
        company_code="C1",
        entry_date=date(2026, 2, 1),
        description="invoice",
        source_module="billing",
        source_type="invoice",
        source_id="seed-invoice",
        posting_status="POSTED",
        created_by="seed",
    )
    session.add(je)
    session.flush()
    session.add_all(
        [
            JournalLine(
                journal_entry_id=je.id,
                account_id=ar.id,
                debit_amount=Decimal("100"),
                credit_amount=Decimal("0"),
                currency="USD",
                fx_rate_to_company_base=Decimal("1"),
                amount_company_base=Decimal("100"),
            ),
            JournalLine(
                journal_entry_id=je.id,
                account_id=rev.id,
                debit_amount=Decimal("0"),
                credit_amount=Decimal("100"),
                currency="USD",
                fx_rate_to_company_base=Decimal("1"),
                amount_company_base=Decimal("100"),
            ),
        ]
    )

    invoice = BillingInvoice(
        tenant_id="tenant-a",
        company_code="C1",
        region_code="NA",
        invoice_number="INV-C1-00001",
        account_id=None,
        subscription_id=None,
        order_id=None,
        currency="USD",
        status="ISSUED",
        issue_date=date(2026, 2, 1),
        due_date=date(2026, 2, 10),
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        subtotal=Decimal("100"),
        discount_total=Decimal("0"),
        tax_total=Decimal("0"),
        total=Decimal("100"),
        amount_due=Decimal("30"),
        ledger_journal_entry_id=je.id,
    )
    session.add(invoice)
    session.flush()

    session.add(
        Payment(
            tenant_id="tenant-a",
            company_code="C1",
            region_code="NA",
            payment_number="PAY-C1-00001",
            account_id=None,
            currency="USD",
            amount=Decimal("50"),
            status="CONFIRMED",
            payment_method="MANUAL",
            received_at=datetime(2026, 2, 5, tzinfo=timezone.utc),
            ledger_journal_entry_id=je.id,
        )
    )
    session.flush()
    payment = session.query(Payment).filter_by(payment_number="PAY-C1-00001").one()
    session.add(PaymentAllocation(payment_id=payment.id, invoice_id=invoice.id, amount_allocated=Decimal("50")))

    session.add(
        BillingCreditNote(
            tenant_id="tenant-a",
            company_code="C1",
            region_code="NA",
            credit_note_number="CN-C1-00001",
            invoice_id=invoice.id,
            currency="USD",
            status="APPLIED",
            issue_date=date(2026, 2, 7),
            subtotal=Decimal("20"),
            tax_total=Decimal("0"),
            total=Decimal("20"),
            ledger_journal_entry_id=je.id,
        )
    )

    mismatch_invoice = BillingInvoice(
        tenant_id="tenant-a",
        company_code="C1",
        region_code="NA",
        invoice_number="INV-C1-00002",
        account_id=None,
        subscription_id=None,
        order_id=None,
        currency="USD",
        status="ISSUED",
        issue_date=date(2026, 2, 12),
        due_date=date(2026, 2, 20),
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        subtotal=Decimal("70"),
        discount_total=Decimal("0"),
        tax_total=Decimal("0"),
        total=Decimal("70"),
        amount_due=Decimal("70"),
        ledger_journal_entry_id=None,
    )
    session.add(mismatch_invoice)
    session.commit()

    return {"invoice_id": invoice.id, "payment_id": payment.id, "journal_entry_id": je.id}


def test_ar_aging_and_trial_balance(db_session: Session) -> None:
    _seed_report_data(db_session)
    ctx = _ctx()

    aging = finance_reporting_service.ar_aging(
        db_session,
        ctx,
        tenant_id="tenant-a",
        company_code="C1",
        as_of_date=date(2026, 2, 25),
    )
    assert aging.total_amount_due == Decimal("100.000000")
    assert any(row.invoice_number == "INV-C1-00001" for row in aging.rows)

    trial = finance_reporting_service.trial_balance(
        db_session,
        ctx,
        tenant_id="tenant-a",
        company_code="C1",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )
    assert trial.total_debits == trial.total_credits
    assert any(row.account_code == "1100" for row in trial.rows)


def test_revenue_summary_and_reconciliation_mismatches(db_session: Session) -> None:
    _seed_report_data(db_session)
    ctx = _ctx()

    revenue = finance_reporting_service.revenue_summary(
        db_session,
        ctx,
        tenant_id="tenant-a",
        company_code="C1",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )
    assert revenue.invoiced_total == Decimal("170.000000")
    assert revenue.credit_note_total == Decimal("20.000000")
    assert revenue.net_revenue_total == Decimal("150.000000")

    reconciliation = finance_reporting_service.reconciliation(
        db_session,
        ctx,
        tenant_id="tenant-a",
        company_code="C1",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )
    assert len(reconciliation.ledger_link_mismatches) >= 1
    assert any(item.entity_type == "invoice" for item in reconciliation.ledger_link_mismatches)
