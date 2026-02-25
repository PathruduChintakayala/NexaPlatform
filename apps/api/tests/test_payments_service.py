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
from app.business.billing.service import BillingService
from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookItemUpsert, CatalogProductCreate
from app.business.catalog.service import CatalogService
from app.business.payments.schemas import AllocatePaymentRequest, PaymentCreate, RefundCreate
from app.business.payments.service import PaymentsService
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
    return AuthContext(user_id="payments-user", tenant_id="tenant-a", entity_scope=[company], correlation_id="corr-payments")


def _seed_issued_invoice(session: Session, ctx: AuthContext) -> BillingInvoice:
    catalog = CatalogService()
    revenue = RevenueService()
    subscription_service = SubscriptionService()
    billing = BillingService()

    product = catalog.create_product(
        session,
        ctx,
        CatalogProductCreate(tenant_id="tenant-a", company_code="C1", sku="PAY-SVC-SKU-1", name="Pay SKU", default_currency="USD"),
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

    invoice = billing.generate_invoice_from_subscription(session, ctx, subscription.id, date(2026, 2, 1), date(2026, 2, 28))
    settings = get_settings()
    prior = settings.billing_post_to_ledger
    settings.billing_post_to_ledger = False
    try:
        issued = billing.issue_invoice(session, ctx, invoice.id)
    finally:
        settings.billing_post_to_ledger = prior

    row = session.scalar(select(BillingInvoice).where(BillingInvoice.id == issued.id))
    assert row is not None
    return row


def test_create_payment_posts_journal_entry(db_session: Session) -> None:
    service = PaymentsService()
    ledger = LedgerService()
    ctx = _ctx()

    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")
    payment = service.create_payment(
        db_session,
        ctx,
        PaymentCreate(
            tenant_id="tenant-a",
            company_code="C1",
            region_code="NA",
            account_id=None,
            currency="USD",
            amount=Decimal("100"),
            payment_method="MANUAL",
        ),
    )

    assert payment.status == "CONFIRMED"
    assert payment.ledger_journal_entry_id is not None
    entry = db_session.scalar(select(JournalEntry).where(JournalEntry.id == payment.ledger_journal_entry_id))
    assert entry is not None
    assert entry.posting_status == "POSTED"


def test_allocate_payment_partial_and_full_updates_invoice_state(db_session: Session) -> None:
    service = PaymentsService()
    ledger = LedgerService()
    ctx = _ctx()

    invoice = _seed_issued_invoice(db_session, ctx)
    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")
    payment = service.create_payment(
        db_session,
        ctx,
        PaymentCreate(
            tenant_id="tenant-a",
            company_code="C1",
            currency="USD",
            amount=Decimal("100"),
            payment_method="BANK_TRANSFER",
        ),
    )

    first = service.allocate_payment(
        db_session,
        ctx,
        payment.id,
        AllocatePaymentRequest(invoice_id=invoice.id, amount=Decimal("40")),
    )
    refreshed_invoice = db_session.scalar(select(BillingInvoice).where(BillingInvoice.id == invoice.id))
    assert refreshed_invoice is not None
    assert refreshed_invoice.amount_due == Decimal("60.000000")
    assert refreshed_invoice.status == "ISSUED"

    second = service.allocate_payment(
        db_session,
        ctx,
        payment.id,
        AllocatePaymentRequest(invoice_id=invoice.id, amount=Decimal("60")),
    )
    refreshed_invoice = db_session.scalar(select(BillingInvoice).where(BillingInvoice.id == invoice.id))
    assert refreshed_invoice is not None
    assert refreshed_invoice.amount_due == Decimal("0.000000")
    assert refreshed_invoice.status == "PAID"
    assert len(first.allocations) == 1
    assert len(second.allocations) == 2


def test_refund_posts_reverse_journal_and_marks_refunded(db_session: Session) -> None:
    service = PaymentsService()
    ledger = LedgerService()
    ctx = _ctx()

    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")
    payment = service.create_payment(
        db_session,
        ctx,
        PaymentCreate(
            tenant_id="tenant-a",
            company_code="C1",
            currency="USD",
            amount=Decimal("80"),
            payment_method="CARD",
        ),
    )

    refund = service.refund_payment(
        db_session,
        ctx,
        payment.id,
        RefundCreate(amount=Decimal("80"), reason="customer request"),
    )

    assert refund.status == "CONFIRMED"
    assert refund.ledger_journal_entry_id is not None
    payment_after = service.get_payment(db_session, ctx, payment.id)
    assert payment_after.status == "REFUNDED"


def test_rls_blocks_cross_company_create(db_session: Session) -> None:
    service = PaymentsService()
    ledger = LedgerService()
    ledger.seed_chart_of_accounts(db_session, _ctx(), tenant_id="tenant-a", company_code="C1", currency="USD")

    with pytest.raises(HTTPException) as exc_info:
        service.create_payment(
            db_session,
            _ctx("C2"),
            PaymentCreate(
                tenant_id="tenant-a",
                company_code="C1",
                currency="USD",
                amount=Decimal("10"),
                payment_method="MANUAL",
            ),
        )
    assert exc_info.value.status_code == 403


def test_fls_denies_payment_create_fields(db_session: Session) -> None:
    service = PaymentsService()
    ledger = LedgerService()
    ledger.seed_chart_of_accounts(db_session, _ctx(), tenant_id="tenant-a", company_code="C1", currency="USD")

    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={"user": {"payments.payment.create"}},
            default_allow=False,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        service.create_payment(
            db_session,
            AuthContext(user_id="payments-user", tenant_id="tenant-a", roles=["user"], permissions=["user"], entity_scope=["C1"]),
            PaymentCreate(
                tenant_id="tenant-a",
                company_code="C1",
                currency="USD",
                amount=Decimal("10"),
                payment_method="MANUAL",
            ),
        )
    assert exc_info.value.status_code == 403
