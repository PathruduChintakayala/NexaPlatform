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
        return AuthUser(sub="rev-user", roles=["user"])

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
            "sku": "REV-SKU-1",
            "name": "Rev Product",
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

    item = client.put(
        "/catalog/pricebook-items",
        json={
            "pricebook_id": pricebook.json()["id"],
            "product_id": product.json()["id"],
            "billing_period": "MONTHLY",
            "currency": "USD",
            "unit_price": "50.00",
        },
        headers=_headers("C1"),
    )
    assert item.status_code == 200

    return {
        "product_id": product.json()["id"],
        "pricebook_item_id": item.json()["id"],
    }


def test_rls_blocks_create_quote_for_forbidden_company(client: TestClient) -> None:
    response = client.post(
        "/revenue/quotes",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C2",
            "currency": "USD",
        },
        headers=_headers("C1"),
    )
    assert response.status_code == 403


def test_quote_to_order_to_contract_lifecycle(client: TestClient) -> None:
    seed = _seed_catalog(client)

    quote = client.post(
        "/revenue/quotes",
        json={"tenant_id": "tenant-a", "company_code": "C1", "currency": "USD"},
        headers=_headers("C1"),
    )
    assert quote.status_code == 201

    add_line = client.post(
        f"/revenue/quotes/{quote.json()['id']}/lines",
        json={
            "product_id": seed["product_id"],
            "pricebook_item_id": seed["pricebook_item_id"],
            "quantity": "2",
        },
        headers=_headers("C1"),
    )
    assert add_line.status_code == 201

    sent = client.post(f"/revenue/quotes/{quote.json()['id']}/send", headers=_headers("C1"))
    assert sent.status_code == 200
    accepted = client.post(f"/revenue/quotes/{quote.json()['id']}/accept", headers=_headers("C1"))
    assert accepted.status_code == 200

    order = client.post(f"/revenue/quotes/{quote.json()['id']}/create-order", headers=_headers("C1"))
    assert order.status_code == 201

    confirm = client.post(f"/revenue/orders/{order.json()['id']}/confirm", headers=_headers("C1"))
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "CONFIRMED"

    contract = client.post(f"/revenue/orders/{order.json()['id']}/create-contract", headers=_headers("C1"))
    assert contract.status_code == 201
    assert contract.json()["status"] == "ACTIVE"


def test_revenue_list_and_get_endpoints(client: TestClient) -> None:
    seed = _seed_catalog(client)

    quote = client.post(
        "/revenue/quotes",
        json={"tenant_id": "tenant-a", "company_code": "C1", "currency": "USD"},
        headers=_headers("C1"),
    )
    assert quote.status_code == 201

    line = client.post(
        f"/revenue/quotes/{quote.json()['id']}/lines",
        json={
            "product_id": seed["product_id"],
            "pricebook_item_id": seed["pricebook_item_id"],
            "quantity": "1",
        },
        headers=_headers("C1"),
    )
    assert line.status_code == 201

    list_quotes = client.get("/revenue/quotes", params={"tenant_id": "tenant-a"}, headers=_headers("C1"))
    assert list_quotes.status_code == 200
    assert len(list_quotes.json()) >= 1

    get_quote = client.get(f"/revenue/quotes/{quote.json()['id']}", headers=_headers("C1"))
    assert get_quote.status_code == 200

    client.post(f"/revenue/quotes/{quote.json()['id']}/send", headers=_headers("C1"))
    client.post(f"/revenue/quotes/{quote.json()['id']}/accept", headers=_headers("C1"))
    order = client.post(f"/revenue/quotes/{quote.json()['id']}/create-order", headers=_headers("C1"))
    assert order.status_code == 201

    list_orders = client.get("/revenue/orders", params={"tenant_id": "tenant-a"}, headers=_headers("C1"))
    assert list_orders.status_code == 200
    get_order = client.get(f"/revenue/orders/{order.json()['id']}", headers=_headers("C1"))
    assert get_order.status_code == 200

    client.post(f"/revenue/orders/{order.json()['id']}/confirm", headers=_headers("C1"))
    contract = client.post(f"/revenue/orders/{order.json()['id']}/create-contract", headers=_headers("C1"))
    assert contract.status_code == 201

    list_contracts = client.get("/revenue/contracts", params={"tenant_id": "tenant-a"}, headers=_headers("C1"))
    assert list_contracts.status_code == 200
    get_contract = client.get(f"/revenue/contracts/{contract.json()['id']}", headers=_headers("C1"))
    assert get_contract.status_code == 200
