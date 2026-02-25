from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import events
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
        return AuthUser(sub="sub-user", roles=["user"])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    events.published_events.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    events.published_events.clear()


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
            "sku": "SUB-API-SKU-1",
            "name": "API Product",
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
            "unit_price": "40.00",
        },
        headers=_headers("C1"),
    )
    assert item.status_code == 200

    return {
        "product_id": product.json()["id"],
        "pricebook_item_id": item.json()["id"],
    }


def _seed_contract(client: TestClient) -> dict[str, str]:
    cat = _seed_catalog(client)

    quote = client.post(
        "/revenue/quotes",
        json={"tenant_id": "tenant-a", "company_code": "C1", "currency": "USD"},
        headers=_headers("C1"),
    )
    assert quote.status_code == 201

    line = client.post(
        f"/revenue/quotes/{quote.json()['id']}/lines",
        json={
            "product_id": cat["product_id"],
            "pricebook_item_id": cat["pricebook_item_id"],
            "quantity": "2",
        },
        headers=_headers("C1"),
    )
    assert line.status_code == 201

    assert client.post(f"/revenue/quotes/{quote.json()['id']}/send", headers=_headers("C1")).status_code == 200
    assert client.post(f"/revenue/quotes/{quote.json()['id']}/accept", headers=_headers("C1")).status_code == 200

    order = client.post(f"/revenue/quotes/{quote.json()['id']}/create-order", headers=_headers("C1"))
    assert order.status_code == 201
    assert client.post(f"/revenue/orders/{order.json()['id']}/confirm", headers=_headers("C1")).status_code == 200

    contract = client.post(f"/revenue/orders/{order.json()['id']}/create-contract", headers=_headers("C1"))
    assert contract.status_code == 201

    return {
        "contract_id": contract.json()["id"],
        "product_id": cat["product_id"],
        "pricebook_item_id": cat["pricebook_item_id"],
    }


def test_rls_blocks_subscription_plan_create(client: TestClient) -> None:
    blocked = client.post(
        "/subscriptions/plans",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C2",
            "name": "Blocked",
            "code": "BLOCKED",
            "currency": "USD",
            "billing_period": "MONTHLY",
        },
        headers=_headers("C1"),
    )
    assert blocked.status_code == 403


def test_plan_item_snapshot_and_subscription_lifecycle(client: TestClient) -> None:
    seed = _seed_contract(client)

    plan = client.post(
        "/subscriptions/plans",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "name": "Pro Monthly",
            "code": "PRO-MONTHLY",
            "currency": "USD",
            "billing_period": "MONTHLY",
        },
        headers=_headers("C1"),
    )
    assert plan.status_code == 201

    plan_item = client.post(
        f"/subscriptions/plans/{plan.json()['id']}/items",
        json={
            "product_id": seed["product_id"],
            "pricebook_item_id": seed["pricebook_item_id"],
            "quantity_default": "1",
        },
        headers=_headers("C1"),
    )
    assert plan_item.status_code == 201
    assert plan_item.json()["unit_price_snapshot"] == "40.000000"

    create_sub = client.post(
        f"/subscriptions/from-contract/{seed['contract_id']}",
        json={"plan_id": plan.json()["id"], "auto_renew": True, "renewal_term_count": 1, "renewal_billing_period": "MONTHLY"},
        headers=_headers("C1"),
    )
    assert create_sub.status_code == 201

    sub_id = create_sub.json()["id"]
    activate = client.post(f"/subscriptions/{sub_id}/activate", json={"start_date": "2026-02-01"}, headers=_headers("C1"))
    assert activate.status_code == 200
    assert activate.json()["current_period_end"] == "2026-02-28"

    renew = client.post(f"/subscriptions/{sub_id}/renew", headers=_headers("C1"))
    assert renew.status_code == 200
    assert renew.json()["current_period_end"] == "2026-03-31"

    suspend = client.post(f"/subscriptions/{sub_id}/suspend", json={"effective_date": "2026-03-15"}, headers=_headers("C1"))
    assert suspend.status_code == 200
    resume = client.post(f"/subscriptions/{sub_id}/resume", json={"effective_date": "2026-03-20"}, headers=_headers("C1"))
    assert resume.status_code == 200

    cancel = client.post(f"/subscriptions/{sub_id}/cancel", json={"effective_date": "2026-03-25", "reason": "requested"}, headers=_headers("C1"))
    assert cancel.status_code == 200

    changes = client.get(f"/subscriptions/{sub_id}/changes", headers=_headers("C1"))
    assert changes.status_code == 200
    assert any(item["change_type"] == "RENEW" for item in changes.json())
    assert any(event["event_type"] == "subscription.cancelled" for event in events.published_events)


def test_change_quantity_endpoint(client: TestClient) -> None:
    seed = _seed_contract(client)

    sub = client.post(
        f"/subscriptions/from-contract/{seed['contract_id']}",
        json={},
        headers=_headers("C1"),
    )
    assert sub.status_code == 201

    sub_id = sub.json()["id"]
    assert client.post(f"/subscriptions/{sub_id}/activate", json={}, headers=_headers("C1")).status_code == 200

    changed = client.post(
        f"/subscriptions/{sub_id}/items/{seed['product_id']}/quantity",
        json={"new_qty": "7", "effective_date": date.today().isoformat()},
        headers=_headers("C1"),
    )
    assert changed.status_code == 200
    assert changed.json()["items"][0]["quantity"] == "7.000000"
    assert any(event["event_type"] == "subscription.quantity_changed" for event in events.published_events)
