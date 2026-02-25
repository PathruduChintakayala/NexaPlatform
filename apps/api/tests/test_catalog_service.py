from __future__ import annotations

from datetime import date
from decimal import Decimal
from collections.abc import Generator

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookItemUpsert, CatalogProductCreate
from app.business.catalog.service import CatalogService
from app.core.database import Base
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


def test_default_pricebook_uniqueness(db_session: Session) -> None:
    service = CatalogService()
    ctx = AuthContext(user_id="catalog-user", tenant_id="tenant-a", entity_scope=["C1"])

    created = service.create_pricebook(
        db_session,
        ctx,
        CatalogPricebookCreate(
            tenant_id="tenant-a",
            company_code="C1",
            name="Default USD",
            currency="USD",
            is_default=True,
        ),
    )
    assert created.is_default is True

    with pytest.raises(HTTPException) as exc_info:
        service.create_pricebook(
            db_session,
            ctx,
            CatalogPricebookCreate(
                tenant_id="tenant-a",
                company_code="C1",
                name="Another Default USD",
                currency="USD",
                is_default=True,
            ),
        )
    assert exc_info.value.status_code == 409


def test_get_price_by_currency_and_billing_period(db_session: Session) -> None:
    service = CatalogService()
    ctx = AuthContext(user_id="catalog-user", tenant_id="tenant-a", entity_scope=["C1"])

    product = service.create_product(
        db_session,
        ctx,
        CatalogProductCreate(
            tenant_id="tenant-a",
            company_code="C1",
            sku="PRO-1",
            name="Product 1",
            default_currency="USD",
        ),
    )
    pricebook = service.create_pricebook(
        db_session,
        ctx,
        CatalogPricebookCreate(
            tenant_id="tenant-a",
            company_code="C1",
            name="US Annual",
            currency="USD",
            is_default=True,
            valid_from=date(2026, 1, 1),
        ),
    )
    service.upsert_pricebook_item(
        db_session,
        ctx,
        CatalogPricebookItemUpsert(
            pricebook_id=pricebook.id,
            product_id=product.id,
            billing_period="ANNUAL",
            currency="USD",
            unit_price=Decimal("1200"),
        ),
    )

    price = service.get_price(
        db_session,
        ctx,
        tenant_id="tenant-a",
        company_code="C1",
        sku="PRO-1",
        currency="USD",
        billing_period="ANNUAL",
        at_date=date(2026, 2, 1),
    )
    assert price.unit_price == Decimal("1200")


def test_create_product_out_of_scope_company_blocked(db_session: Session) -> None:
    service = CatalogService()
    ctx = AuthContext(user_id="catalog-user", tenant_id="tenant-a", entity_scope=["C1"])

    with pytest.raises(HTTPException) as exc_info:
        service.create_product(
            db_session,
            ctx,
            CatalogProductCreate(
                tenant_id="tenant-a",
                company_code="C2",
                sku="PRO-2",
                name="Product 2",
                default_currency="USD",
            ),
        )

    assert exc_info.value.status_code == 403
