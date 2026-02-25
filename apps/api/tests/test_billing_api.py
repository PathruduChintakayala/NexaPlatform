from __future__ import annotations

from collections.abc import Generator
from datetime import date

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
        return AuthUser(sub="billing-user", roles=["user"])

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


def _seed_contract_subscription(client: TestClient) -> dict[str, str]:
    product = client.post(
        "/catalog/products",
        json={"tenant_id": "tenant-a", "company_code": "C1", "sku": "BILL-API-SKU", "name": "Bill API", "default_currency": "USD"},
        headers=_headers("C1"),
    )
    assert product.status_code == 201

    pricebook = client.post(
        "/catalog/pricebooks",
        json={"tenant_id": "tenant-a", "company_code": "C1", "name": "Default USD", "currency": "USD", "is_default": True},
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

    quote = client.post(
        "/revenue/quotes",
        json={"tenant_id": "tenant-a", "company_code": "C1", "currency": "USD"},
        headers=_headers("C1"),
    )
    assert quote.status_code == 201

    line = client.post(
        f"/revenue/quotes/{quote.json()['id']}/lines",
        json={"product_id": product.json()["id"], "pricebook_item_id": item.json()["id"], "quantity": "2"},
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

    sub = client.post(
        f"/subscriptions/from-contract/{contract.json()['id']}",
        json={"auto_renew": True, "renewal_term_count": 1, "renewal_billing_period": "MONTHLY"},
        headers=_headers("C1"),
    )
    assert sub.status_code == 201
    assert client.post(f"/subscriptions/{sub.json()['id']}/activate", json={"start_date": "2026-02-01"}, headers=_headers("C1")).status_code == 200

    return {"subscription_id": sub.json()["id"]}


def test_rls_blocks_invoice_generation(client: TestClient) -> None:
    seed = _seed_contract_subscription(client)
    blocked = client.post(
        f"/billing/invoices/from-subscription/{seed['subscription_id']}",
        params={"period_start": "2026-02-01", "period_end": "2026-02-28"},
        headers=_headers("C2"),
    )
    assert blocked.status_code == 403


def test_invoice_issue_void_creditnote_flow(client: TestClient) -> None:
    seed = _seed_contract_subscription(client)

    invoice = client.post(
        f"/billing/invoices/from-subscription/{seed['subscription_id']}",
        params={"period_start": "2026-02-01", "period_end": "2026-02-28"},
        headers=_headers("C1"),
    )
    assert invoice.status_code == 201
    assert invoice.json()["total"] == "100.000000"

    issue = client.post(f"/billing/invoices/{invoice.json()['id']}/issue", headers=_headers("C1"))
    assert issue.status_code == 200

    lines = client.get(f"/billing/invoices/{invoice.json()['id']}/lines", headers=_headers("C1"))
    assert lines.status_code == 200
    assert len(lines.json()) == 1

    credit = client.post(
        f"/billing/invoices/{invoice.json()['id']}/credit-notes",
        json={"lines": [{"description": "partial", "quantity": "1", "unit_price_snapshot": "10"}]},
        headers=_headers("C1"),
    )
    assert credit.status_code == 201

    refreshed = client.get(f"/billing/invoices/{invoice.json()['id']}", headers=_headers("C1"))
    assert refreshed.status_code == 200
    assert refreshed.json()["amount_due"] == "90.000000"

    paid = client.post(
        f"/billing/invoices/{invoice.json()['id']}/mark-paid",
        json={"amount": "90", "paid_at": "2026-02-10T00:00:00Z"},
        headers=_headers("C1"),
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"

    invoice2 = client.post(
        f"/billing/invoices/from-subscription/{seed['subscription_id']}",
        params={"period_start": "2026-03-01", "period_end": "2026-03-31"},
        headers=_headers("C1"),
    )
    assert invoice2.status_code == 201
    issue2 = client.post(f"/billing/invoices/{invoice2.json()['id']}/issue", headers=_headers("C1"))
    assert issue2.status_code == 200
    voided = client.post(f"/billing/invoices/{invoice2.json()['id']}/void", params={"reason": "test"}, headers=_headers("C1"))
    assert voided.status_code == 200
    assert voided.json()["status"] == "VOID"


def test_overdue_refresh_endpoint(client: TestClient) -> None:
    seed = _seed_contract_subscription(client)
    invoice = client.post(
        f"/billing/invoices/from-subscription/{seed['subscription_id']}",
        params={"period_start": "2026-01-01", "period_end": "2026-01-31"},
        headers=_headers("C1"),
    )
    assert invoice.status_code == 201

    issue = client.post(f"/billing/invoices/{invoice.json()['id']}/issue", headers=_headers("C1"))
    assert issue.status_code == 200

    refresh = client.post(f"/billing/invoices/{invoice.json()['id']}/refresh-overdue", headers=_headers("C1"))
    assert refresh.status_code == 200
    assert "status" in refresh.json()

    list_invoices = client.get("/billing/invoices", params={"tenant_id": "tenant-a"}, headers=_headers("C1"))
    assert list_invoices.status_code == 200

    list_credit = client.get("/billing/credit-notes", params={"tenant_id": "tenant-a"}, headers=_headers("C1"))
    assert list_credit.status_code == 200
