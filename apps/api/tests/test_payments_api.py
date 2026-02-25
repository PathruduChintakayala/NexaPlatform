from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
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
        return AuthUser(sub="payments-user", roles=["user"])

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


def _seed_issued_invoice(client: TestClient) -> dict[str, str]:
    product = client.post(
        "/catalog/products",
        json={"tenant_id": "tenant-a", "company_code": "C1", "sku": "PAY-API-SKU", "name": "Pay API", "default_currency": "USD"},
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

    invoice = client.post(
        f"/billing/invoices/from-subscription/{sub.json()['id']}",
        params={"period_start": "2026-02-01", "period_end": "2026-02-28"},
        headers=_headers("C1"),
    )
    assert invoice.status_code == 201

    settings = get_settings()
    prior = settings.billing_post_to_ledger
    settings.billing_post_to_ledger = False
    try:
        issue = client.post(f"/billing/invoices/{invoice.json()['id']}/issue", headers=_headers("C1"))
        assert issue.status_code == 200
    finally:
        settings.billing_post_to_ledger = prior

    return {"invoice_id": invoice.json()["id"]}


def _seed_ledger_accounts(client: TestClient) -> None:
    seeded = client.post(
        "/ledger/seeds/chart-of-accounts",
        json={"tenant_id": "tenant-a", "company_code": "C1", "currency": "USD"},
        headers=_headers("C1"),
    )
    assert seeded.status_code == 200


def test_create_allocate_refund_and_list_flow(client: TestClient) -> None:
    seed = _seed_issued_invoice(client)
    _seed_ledger_accounts(client)

    created = client.post(
        "/payments",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "currency": "USD",
            "amount": "100",
            "payment_method": "BANK_TRANSFER",
        },
        headers=_headers("C1"),
    )
    assert created.status_code == 201
    payment_id = created.json()["id"]

    allocated = client.post(
        f"/payments/{payment_id}/allocate",
        json={"invoice_id": seed["invoice_id"], "amount": "100"},
        headers=_headers("C1"),
    )
    assert allocated.status_code == 200
    assert len(allocated.json()["allocations"]) == 1

    allocations = client.get(f"/payments/{payment_id}/allocations", headers=_headers("C1"))
    assert allocations.status_code == 200
    assert len(allocations.json()) == 1

    refund = client.post(
        f"/payments/{payment_id}/refund",
        json={"amount": "40", "reason": "partial return"},
        headers=_headers("C1"),
    )
    assert refund.status_code == 201

    detail = client.get(f"/payments/{payment_id}", headers=_headers("C1"))
    assert detail.status_code == 200
    assert len(detail.json()["refunds"]) == 1

    listing = client.get("/payments", params={"tenant_id": "tenant-a", "company_code": "C1"}, headers=_headers("C1"))
    assert listing.status_code == 200
    assert len(listing.json()) >= 1


def test_rls_blocks_cross_company_payment_access(client: TestClient) -> None:
    _seed_ledger_accounts(client)

    created = client.post(
        "/payments",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "currency": "USD",
            "amount": "25",
            "payment_method": "MANUAL",
        },
        headers=_headers("C1"),
    )
    assert created.status_code == 201
    payment_id = created.json()["id"]

    blocked_create = client.post(
        "/payments",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "currency": "USD",
            "amount": "10",
            "payment_method": "MANUAL",
        },
        headers=_headers("C2"),
    )
    assert blocked_create.status_code == 403

    blocked_get = client.get(f"/payments/{payment_id}", headers=_headers("C2"))
    assert blocked_get.status_code == 404
