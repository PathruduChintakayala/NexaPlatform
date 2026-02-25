from __future__ import annotations

from collections.abc import Generator
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookItemUpsert, CatalogProductCreate
from app.business.catalog.service import CatalogService
from app.business.revenue.models import RevenueQuoteLine
from app.business.revenue.schemas import RevenueQuoteCreate, RevenueQuoteLineCreate
from app.business.revenue.service import RevenueService
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
    return AuthContext(user_id="rev-user", tenant_id="tenant-a", entity_scope=[company])


def _seed_catalog(session: Session, ctx: AuthContext) -> tuple[UUID, UUID, UUID]:
    catalog = CatalogService()
    product = catalog.create_product(
        session,
        ctx,
        CatalogProductCreate(
            tenant_id="tenant-a",
            company_code="C1",
            sku="SKU-1",
            name="SKU 1",
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
            valid_from=date(2026, 1, 1),
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
            unit_price=Decimal("25"),
        ),
    )
    return product.id, item.id, pricebook.id


def test_currency_mismatch_rejected(db_session: Session) -> None:
    service = RevenueService()
    ctx = _ctx()
    product_id, pricebook_item_id, _ = _seed_catalog(db_session, ctx)

    quote = service.create_quote(
        db_session,
        ctx,
        RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="EUR"),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.add_quote_line(
            db_session,
            ctx,
            quote.id,
            RevenueQuoteLineCreate(
                product_id=product_id,
                pricebook_item_id=pricebook_item_id,
                quantity=Decimal("2"),
            ),
        )
    assert exc_info.value.status_code == 422


def test_unit_price_snapshot_preserved_after_catalog_change(db_session: Session) -> None:
    service = RevenueService()
    catalog = CatalogService()
    ctx = _ctx()
    product_id, pricebook_item_id, pricebook_id = _seed_catalog(db_session, ctx)

    quote = service.create_quote(
        db_session,
        ctx,
        RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"),
    )
    line = service.add_quote_line(
        db_session,
        ctx,
        quote.id,
        RevenueQuoteLineCreate(
            product_id=product_id,
            pricebook_item_id=pricebook_item_id,
            quantity=Decimal("2"),
        ),
    )
    assert line.unit_price == Decimal("25.000000")

    catalog.upsert_pricebook_item(
        db_session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook_id,
            product_id=product_id,
            billing_period="MONTHLY",
            currency="USD",
            unit_price=Decimal("35"),
        ),
    )

    stored = db_session.scalar(select(RevenueQuoteLine).where(RevenueQuoteLine.id == line.id))
    assert stored is not None
    assert stored.unit_price == Decimal("25.000000")


def test_totals_recompute_and_lifecycle_transitions(db_session: Session) -> None:
    service = RevenueService()
    ctx = _ctx()
    product_id, pricebook_item_id, _ = _seed_catalog(db_session, ctx)

    quote = service.create_quote(
        db_session,
        ctx,
        RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"),
    )
    service.add_quote_line(
        db_session,
        ctx,
        quote.id,
        RevenueQuoteLineCreate(
            product_id=product_id,
            pricebook_item_id=pricebook_item_id,
            quantity=Decimal("3"),
        ),
    )

    refreshed = service.get_quote(db_session, ctx, quote.id)
    assert refreshed.subtotal == Decimal("75.000000")
    assert refreshed.total == Decimal("75.000000")

    with pytest.raises(HTTPException) as exc_info:
        service.accept_quote(db_session, ctx, quote.id)
    assert exc_info.value.status_code == 409

    sent = service.send_quote(db_session, ctx, quote.id)
    assert sent.status == "SENT"
    accepted = service.accept_quote(db_session, ctx, quote.id)
    assert accepted.status == "ACCEPTED"


def test_confirm_order_posts_ledger_when_enabled(db_session: Session) -> None:
    service = RevenueService()
    catalog = CatalogService()
    ledger = LedgerService()
    ctx = _ctx()

    product = catalog.create_product(
        db_session,
        ctx,
        CatalogProductCreate(tenant_id="tenant-a", company_code="C1", sku="SKU-2", name="SKU 2", default_currency="USD"),
    )
    pricebook = catalog.create_pricebook(
        db_session,
        ctx,
        CatalogPricebookCreate(tenant_id="tenant-a", company_code="C1", name="Default USD", currency="USD", is_default=True),
    )
    item = catalog.upsert_pricebook_item(
        db_session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook.id,
            product_id=product.id,
            billing_period="MONTHLY",
            currency="USD",
            unit_price=Decimal("100"),
        ),
    )

    ledger.seed_chart_of_accounts(db_session, ctx, tenant_id="tenant-a", company_code="C1", currency="USD")

    quote = service.create_quote(
        db_session,
        ctx,
        RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"),
    )
    service.add_quote_line(
        db_session,
        ctx,
        quote.id,
        RevenueQuoteLineCreate(product_id=product.id, pricebook_item_id=item.id, quantity=Decimal("2")),
    )
    service.send_quote(db_session, ctx, quote.id)
    service.accept_quote(db_session, ctx, quote.id)
    order = service.create_order_from_quote(db_session, ctx, quote.id)

    settings = get_settings()
    prior = settings.revenue_post_to_ledger
    settings.revenue_post_to_ledger = True
    try:
        confirmed = service.confirm_order(db_session, ctx, order.id)
    finally:
        settings.revenue_post_to_ledger = prior

    assert confirmed.status == "CONFIRMED"
    journal = db_session.scalar(
        select(JournalEntry).where(
            JournalEntry.source_module == "revenue",
            JournalEntry.source_type == "order",
            JournalEntry.source_id == str(order.id),
        )
    )
    assert journal is not None


def test_fls_prevents_status_edit_on_send(db_session: Session) -> None:
    service = RevenueService()
    ctx = _ctx()
    product_id, pricebook_item_id, _ = _seed_catalog(db_session, ctx)

    quote = service.create_quote(
        db_session,
        ctx,
        RevenueQuoteCreate(tenant_id="tenant-a", company_code="C1", currency="USD"),
    )
    service.add_quote_line(
        db_session,
        ctx,
        quote.id,
        RevenueQuoteLineCreate(product_id=product_id, pricebook_item_id=pricebook_item_id, quantity=Decimal("1")),
    )

    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={
                "user": {
                    "revenue.quote.field.edit:subtotal",
                    "revenue.quote.field.edit:discount_total",
                    "revenue.quote.field.edit:tax_total",
                    "revenue.quote.field.edit:total",
                }
            },
            default_allow=False,
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        service.send_quote(db_session, AuthContext(user_id="rev-user", tenant_id="tenant-a", roles=["user"], permissions=["user"], entity_scope=["C1"]), quote.id)
    assert exc_info.value.status_code == 403
