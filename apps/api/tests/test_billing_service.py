from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.billing.models import BillingInvoice
from app.business.billing.schemas import CreditNoteCreate, CreditNoteLineCreate, MarkInvoicePaidRequest
from app.business.billing.service import BillingService
from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookItemUpsert, CatalogProductCreate
from app.business.catalog.service import CatalogService
from app.business.revenue.schemas import RevenueQuoteCreate, RevenueQuoteLineCreate
from app.business.revenue.service import RevenueService
from app.business.subscription.schemas import ActivateSubscriptionRequest, CreateSubscriptionFromContractRequest
from app.business.subscription.service import SubscriptionService
from app.core.config import get_settings
from app.core.database import Base
from app.platform.ledger.models import JournalEntry
from app.platform.ledger.service import LedgerService
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
    return AuthContext(user_id="billing-user", tenant_id="tenant-a", entity_scope=[company], correlation_id="corr-billing")


def _seed_subscription(session: Session, ctx: AuthContext) -> object:
    catalog = CatalogService()
    revenue = RevenueService()
    subscription_service = SubscriptionService()

    product = catalog.create_product(
        session,
        ctx,
        CatalogProductCreate(tenant_id="tenant-a", company_code="C1", sku="BILL-SKU-1", name="Bill SKU", default_currency="USD"),
    )
    pricebook = catalog.create_pricebook(
        session,
        ctx,
        CatalogPricebookCreate(tenant_id="tenant-a", company_code="C1", name="Default USD", currency="USD", is_default=True),
    )
    item = catalog.upsert_pricebook_item(
        session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook.id,
            product_id=product.id,
            billing_period="MONTHLY",
            currency="USD",
            unit_price=Decimal("50"),
        ),
    )

    quote = revenue.create_quote(session, ctx, RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"))
    revenue.add_quote_line(session, ctx, quote.id, RevenueQuoteLineCreate(product_id=product.id, pricebook_item_id=item.id, quantity=Decimal("2")))
    revenue.send_quote(session, ctx, quote.id)
    revenue.accept_quote(session, ctx, quote.id)
    order = revenue.create_order_from_quote(session, ctx, quote.id)
    revenue.confirm_order(session, ctx, order.id)
    contract = revenue.create_contract_from_order(session, ctx, order.id)

    subscription = subscription_service.create_subscription_from_contract(
        session,
        ctx,
        contract.id,
        CreateSubscriptionFromContractRequest(auto_renew=True, renewal_term_count=1, renewal_billing_period="MONTHLY"),
    )
    subscription = subscription_service.activate_subscription(
        session,
        ctx,
        subscription.id,
        ActivateSubscriptionRequest(start_date=date(2026, 2, 1)),
    )
    return subscription


def test_rls_blocks_cross_company_invoice_generation(db_session: Session) -> None:
    service = BillingService()
    subscription = _seed_subscription(db_session, _ctx())

    with pytest.raises(HTTPException) as exc_info:
        service.generate_invoice_from_subscription(
            db_session,
            _ctx("C2"),
            subscription.id,
            date(2026, 2, 1),
            date(2026, 2, 28),
        )
    assert exc_info.value.status_code == 403


def test_invoice_totals_from_subscription_items(db_session: Session) -> None:
    service = BillingService()
    subscription = _seed_subscription(db_session, _ctx())

    invoice = service.generate_invoice_from_subscription(
        db_session,
        _ctx(),
        subscription.id,
        date(2026, 2, 1),
        date(2026, 2, 28),
    )
    assert invoice.subtotal == Decimal("100.000000")
    assert invoice.total == Decimal("100.000000")
    assert invoice.amount_due == Decimal("100.000000")


def test_issue_invoice_posts_ledger_when_enabled(db_session: Session) -> None:
    service = BillingService()
    ledger = LedgerService()
    ctx = _ctx()
    subscription = _seed_subscription(db_session, ctx)

    invoice = service.generate_invoice_from_subscription(db_session, ctx, subscription.id, date(2026, 2, 1), date(2026, 2, 28))
    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")

    settings = get_settings()
    prior = settings.billing_post_to_ledger
    settings.billing_post_to_ledger = True
    try:
        issued = service.issue_invoice(db_session, ctx, invoice.id)
    finally:
        settings.billing_post_to_ledger = prior

    assert issued.status == "ISSUED"
    assert issued.ledger_journal_entry_id is not None


def test_void_invoice_reverses_journal_entry(db_session: Session) -> None:
    service = BillingService()
    ledger = LedgerService()
    ctx = _ctx()
    subscription = _seed_subscription(db_session, ctx)

    invoice = service.generate_invoice_from_subscription(db_session, ctx, subscription.id, date(2026, 2, 1), date(2026, 2, 28))
    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")

    settings = get_settings()
    prior = settings.billing_post_to_ledger
    settings.billing_post_to_ledger = True
    try:
        issued = service.issue_invoice(db_session, ctx, invoice.id)
        voided = service.void_invoice(db_session, ctx, issued.id, reason="test")
    finally:
        settings.billing_post_to_ledger = prior

    assert voided.status == "VOID"
    original = db_session.scalar(select(JournalEntry).where(JournalEntry.id == issued.ledger_journal_entry_id))
    assert original is not None
    assert original.posting_status == "REVERSED"


def test_credit_note_reduces_amount_due_and_posts_ledger(db_session: Session) -> None:
    service = BillingService()
    ledger = LedgerService()
    ctx = _ctx()
    subscription = _seed_subscription(db_session, ctx)

    invoice = service.generate_invoice_from_subscription(db_session, ctx, subscription.id, date(2026, 2, 1), date(2026, 2, 28))
    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")

    settings = get_settings()
    prior = settings.billing_post_to_ledger
    settings.billing_post_to_ledger = True
    try:
        issued = service.issue_invoice(db_session, ctx, invoice.id)
        note = service.apply_credit_note(
            db_session,
            ctx,
            issued.id,
            CreditNoteCreate(
                lines=[CreditNoteLineCreate(description="Partial credit", quantity=Decimal("1"), unit_price_snapshot=Decimal("10"))]
            ),
        )
    finally:
        settings.billing_post_to_ledger = prior

    assert note.status == "APPLIED"
    refreshed = service.get_invoice(db_session, ctx, issued.id)
    assert refreshed.amount_due == Decimal("90.000000")
    assert note.ledger_journal_entry_id is not None


def test_fls_denies_status_edit_on_issue(db_session: Session) -> None:
    service = BillingService()
    ctx = _ctx()
    subscription = _seed_subscription(db_session, ctx)
    invoice = service.generate_invoice_from_subscription(db_session, ctx, subscription.id, date(2026, 2, 1), date(2026, 2, 28))

    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={"user": {"billing.invoice.field.edit:issue_date"}},
            default_allow=False,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        service.issue_invoice(
            db_session,
            AuthContext(user_id="billing-user", tenant_id="tenant-a", roles=["user"], permissions=["user"], entity_scope=["C1"]),
            invoice.id,
        )
    assert exc_info.value.status_code == 403


def test_overdue_transition_logic(db_session: Session) -> None:
    service = BillingService()
    ctx = _ctx()
    subscription = _seed_subscription(db_session, ctx)

    invoice = service.generate_invoice_from_subscription(db_session, ctx, subscription.id, date(2026, 1, 1), date(2026, 1, 31))
    invoice_row = db_session.scalar(select(BillingInvoice).where(BillingInvoice.id == invoice.id))
    assert invoice_row is not None
    invoice_row.status = "ISSUED"
    invoice_row.due_date = date(2026, 1, 31)
    invoice_row.amount_due = Decimal("100")
    db_session.add(invoice_row)
    db_session.commit()

    refreshed = service.refresh_overdue(db_session, ctx, invoice.id)
    assert refreshed.overdue is True
    assert refreshed.status == "OVERDUE"
