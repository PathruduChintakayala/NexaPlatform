from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthUser, get_current_user
from app.core.database import Base, get_db
from app.main import app
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
        return AuthUser(sub="catalog-user", roles=["user"])

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


def _seed_catalog(client: TestClient) -> dict[str, str]:
    product = client.post(
        "/catalog/products",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "sku": "PRO-1",
            "name": "Product 1",
            "default_currency": "USD",
        },
        headers=_headers("C1"),
    )
    assert product.status_code == 201

    pricebook = client.post(
        "/catalog/pricebooks",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "name": "Default USD",
            "currency": "USD",
            "is_default": True,
        },
        headers=_headers("C1"),
    )
    assert pricebook.status_code == 201

    upsert = client.put(
        "/catalog/pricebook-items",
        json={
            "pricebook_id": pricebook.json()["id"],
            "product_id": product.json()["id"],
            "billing_period": "MONTHLY",
            "currency": "USD",
            "unit_price": "49.99",
        },
        headers=_headers("C1"),
    )
    assert upsert.status_code == 200

    return {
        "product_id": product.json()["id"],
        "pricebook_id": pricebook.json()["id"],
    }


def test_price_lookup_success(client: TestClient) -> None:
    _seed_catalog(client)

    response = client.get(
        "/catalog/price",
        params={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "sku": "PRO-1",
            "currency": "USD",
            "billing_period": "MONTHLY",
        },
        headers=_headers("C1"),
    )
    assert response.status_code == 200
    assert response.json()["unit_price"] == "49.990000"


def test_catalog_rls_blocks_out_of_scope_create(client: TestClient) -> None:
    blocked = client.post(
        "/catalog/products",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C2",
            "sku": "PRO-2",
            "name": "Product 2",
            "default_currency": "USD",
        },
        headers=_headers("C1"),
    )
    assert blocked.status_code == 403


def test_price_lookup_masks_unit_price_with_fls_policy(client: TestClient) -> None:
    _seed_catalog(client)
    set_policy_backend(
        InMemoryPolicyBackend(
            role_permissions={
                "user": {
                    "catalog.pricebook_item.field.read:*",
                    "catalog.pricebook_item.field.mask:unit_price",
                }
            },
            default_allow=False,
        )
    )
    try:
        response = client.get(
            "/catalog/price",
            params={
                "tenant_id": "tenant-a",
                "company_code": "C1",
                "sku": "PRO-1",
                "currency": "USD",
                "billing_period": "MONTHLY",
            },
            headers=_headers("C1"),
        )
    finally:
        set_policy_backend(InMemoryPolicyBackend(default_allow=True))

    assert response.status_code == 200
    assert response.json()["unit_price"] == "***"
