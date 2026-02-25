from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import events
from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookItemUpsert, CatalogProductCreate
from app.business.catalog.service import CatalogService
from app.business.revenue.schemas import RevenueQuoteCreate, RevenueQuoteLineCreate
from app.business.revenue.service import RevenueService
from app.business.subscription.schemas import (
    ActivateSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeQuantityRequest,
    CreateSubscriptionFromContractRequest,
    PlanCreate,
    PlanItemCreate,
    ResumeSubscriptionRequest,
    SuspendSubscriptionRequest,
)
from app.business.subscription.service import SubscriptionService
from app.core.database import Base
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
def reset_globals() -> Generator[None, None, None]:
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    events.published_events.clear()
    yield
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    events.published_events.clear()


def _ctx(company: str = "C1") -> AuthContext:
    return AuthContext(user_id="sub-user", tenant_id="tenant-a", entity_scope=[company], correlation_id="corr-sub")


def _seed_catalog(session: Session, ctx: AuthContext) -> tuple[object, object, object]:
    catalog = CatalogService()
    product = catalog.create_product(
        session,
        ctx,
        CatalogProductCreate(
            tenant_id="tenant-a",
            company_code="C1",
            sku="SUB-SKU-1",
            name="Subscription Product",
            default_currency="USD",
        ),
    )
    pricebook = catalog.create_pricebook(
        session,
        ctx,
        CatalogPricebookCreate(
            tenant_id="tenant-a",
            company_code="C1",
            name="Default USD",
            currency="USD",
            is_default=True,
        ),
    )
    item = catalog.upsert_pricebook_item(
        session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook.id,
            product_id=product.id,
            billing_period="MONTHLY",
            currency="USD",
            unit_price=Decimal("30"),
        ),
    )
    return product.id, pricebook.id, item.id


def _seed_contract(session: Session, ctx: AuthContext) -> tuple[object, object]:
    revenue = RevenueService()
    product_id, _, pricebook_item_id = _seed_catalog(session, ctx)

    quote = revenue.create_quote(session, ctx, RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"))
    revenue.add_quote_line(
        session,
        ctx,
        quote.id,
        RevenueQuoteLineCreate(product_id=product_id, pricebook_item_id=pricebook_item_id, quantity=Decimal("2")),
    )
    revenue.send_quote(session, ctx, quote.id)
    revenue.accept_quote(session, ctx, quote.id)
    order = revenue.create_order_from_quote(session, ctx, quote.id)
    revenue.confirm_order(session, ctx, order.id)
    contract = revenue.create_contract_from_order(session, ctx, order.id)
    return contract.id, product_id


def test_rls_blocks_create_plan_for_forbidden_company(db_session: Session) -> None:
    service = SubscriptionService()

    with pytest.raises(HTTPException) as exc_info:
        service.create_plan(
            db_session,
            _ctx("C1"),
            PlanCreate(
                tenant_id="tenant-a",
                company_code="C2",
                name="Plan C2",
                code="C2-PLAN",
                currency="USD",
                billing_period="MONTHLY",
            ),
        )
    assert exc_info.value.status_code == 403


def test_plan_item_snapshot_and_currency_mismatch(db_session: Session) -> None:
    service = SubscriptionService()
    catalog = CatalogService()
    ctx = _ctx()
    product_id, pricebook_id, pricebook_item_id = _seed_catalog(db_session, ctx)

    plan = service.create_plan(
        db_session,
        ctx,
        PlanCreate(
            tenant_id="tenant-a",
            company_code="C1",
            name="Monthly Plan",
            code="MONTHLY-1",
            currency="EUR",
            billing_period="MONTHLY",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.add_plan_item(
            db_session,
            ctx,
            plan.id,
            PlanItemCreate(product_id=product_id, pricebook_item_id=pricebook_item_id, quantity_default=Decimal("1")),
        )
    assert exc_info.value.status_code == 422

    plan_usd = service.create_plan(
        db_session,
        ctx,
        PlanCreate(
            tenant_id="tenant-a",
            company_code="C1",
            name="USD Plan",
            code="USD-PLAN",
            currency="USD",
            billing_period="MONTHLY",
        ),
    )
    item = service.add_plan_item(
        db_session,
        ctx,
        plan_usd.id,
        PlanItemCreate(product_id=product_id, pricebook_item_id=pricebook_item_id, quantity_default=Decimal("2")),
    )
    assert item.unit_price_snapshot == Decimal("30.000000")

    catalog.upsert_pricebook_item(
        db_session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook_id,
            product_id=product_id,
            billing_period="MONTHLY",
            currency="USD",
            unit_price=Decimal("99"),
        ),
    )
    reread = service.get_plan(db_session, ctx, plan_usd.id)
    assert reread.items[0].unit_price_snapshot == Decimal("30.000000")


def test_create_subscription_from_contract_and_lifecycle(db_session: Session) -> None:
    service = SubscriptionService()
    ctx = _ctx()
    contract_id, product_id = _seed_contract(db_session, ctx)

    subscription = service.create_subscription_from_contract(
        db_session,
        ctx,
        contract_id,
        CreateSubscriptionFromContractRequest(auto_renew=True, renewal_term_count=1, renewal_billing_period="MONTHLY"),
    )
    assert subscription.status == "DRAFT"
    assert len(subscription.items) == 1
    assert subscription.items[0].product_id == product_id
    assert subscription.items[0].unit_price_snapshot == Decimal("30.000000")

    activated = service.activate_subscription(
        db_session,
        ctx,
        subscription.id,
        ActivateSubscriptionRequest(start_date=date(2026, 2, 1)),
    )
    assert activated.status == "ACTIVE"
    assert activated.current_period_start == date(2026, 2, 1)
    assert activated.current_period_end == date(2026, 2, 28)

    renewed = service.renew_subscription(db_session, ctx, subscription.id)
    assert renewed.current_period_start == date(2026, 3, 1)
    assert renewed.current_period_end == date(2026, 3, 31)

    suspended = service.suspend_subscription(
        db_session,
        ctx,
        subscription.id,
        SuspendSubscriptionRequest(effective_date=date(2026, 3, 10)),
    )
    assert suspended.status == "SUSPENDED"

    resumed = service.resume_subscription(
        db_session,
        ctx,
        subscription.id,
        ResumeSubscriptionRequest(effective_date=date(2026, 3, 12)),
    )
    assert resumed.status == "ACTIVE"

    cancelled = service.cancel_subscription(
        db_session,
        ctx,
        subscription.id,
        CancelSubscriptionRequest(effective_date=date(2026, 3, 20), reason="customer request"),
    )
    assert cancelled.status == "CANCELLED"

    changes = service.list_subscription_changes(db_session, ctx, subscription.id)
    assert any(change.change_type == "RENEW" for change in changes)


def test_change_quantity_emits_event_and_applies_immediate(db_session: Session) -> None:
    service = SubscriptionService()
    ctx = _ctx()
    contract_id, product_id = _seed_contract(db_session, ctx)

    sub = service.create_subscription_from_contract(
        db_session,
        ctx,
        contract_id,
        CreateSubscriptionFromContractRequest(),
    )
    service.activate_subscription(db_session, ctx, sub.id, ActivateSubscriptionRequest(start_date=date.today()))

    updated = service.change_quantity(
        db_session,
        ctx,
        sub.id,
        product_id,
        ChangeQuantityRequest(new_qty=Decimal("5"), effective_date=date.today()),
    )
    assert updated.items[0].quantity == Decimal("5.000000")
    assert any(event["event_type"] == "subscription.quantity_changed" for event in events.published_events)


def test_fls_denies_status_edit_on_activate(db_session: Session) -> None:
    service = SubscriptionService()
    ctx = _ctx()
    contract_id, _ = _seed_contract(db_session, ctx)

    sub = service.create_subscription_from_contract(
        db_session,
        ctx,
        contract_id,
        CreateSubscriptionFromContractRequest(),
    )

    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={
                "user": {
                    "subscription.subscription.field.edit:start_date",
                    "subscription.subscription.field.edit:current_period_start",
                    "subscription.subscription.field.edit:current_period_end",
                }
            },
            default_allow=False,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        service.activate_subscription(
            db_session,
            AuthContext(user_id="sub-user", tenant_id="tenant-a", roles=["user"], permissions=["user"], entity_scope=["C1"]),
            sub.id,
            ActivateSubscriptionRequest(start_date=date.today()),
        )
    assert exc_info.value.status_code == 403
