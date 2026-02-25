from __future__ import annotations

import uuid
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
        return AuthUser(sub="ledger-user", roles=["user"])

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


def _seed_accounts(test_client: TestClient, company_code: str) -> list[dict[str, object]]:
    seeded = test_client.post(
        "/ledger/seeds/chart-of-accounts",
        json={"tenant_id": "tenant-a", "company_code": company_code, "currency": "USD"},
        headers=_headers(company_code),
    )
    assert seeded.status_code == 200

    listed = test_client.get(
        "/ledger/accounts",
        params={"tenant_id": "tenant-a", "company_code": company_code},
        headers=_headers(company_code),
    )
    assert listed.status_code == 200
    return listed.json()


def test_posting_entry_allowed_company_succeeds(client: TestClient) -> None:
    accounts = _seed_accounts(client, "C1")
    cash = next(item for item in accounts if item["code"] == "1000")
    revenue = next(item for item in accounts if item["code"] == "4000")

    response = client.post(
        "/ledger/journal-entries",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C1",
            "entry_date": "2026-02-25",
            "description": "Ledger Post",
            "source_module": "crm",
            "source_type": "invoice",
            "source_id": "inv-100",
            "created_by": "ledger-user",
            "lines": [
                {"account_id": cash["id"], "debit_amount": "100", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                {"account_id": revenue["id"], "debit_amount": "0", "credit_amount": "100", "currency": "USD", "fx_rate_to_company_base": "1"},
            ],
        },
        headers=_headers("C1"),
    )
    assert response.status_code == 201


def test_posting_entry_forbidden_company_blocked_by_rls(client: TestClient) -> None:
    accounts = _seed_accounts(client, "C2")
    cash = next(item for item in accounts if item["code"] == "1000")
    revenue = next(item for item in accounts if item["code"] == "4000")

    blocked = client.post(
        "/ledger/journal-entries",
        json={
            "tenant_id": "tenant-a",
            "company_code": "C2",
            "entry_date": "2026-02-25",
            "description": "Blocked",
            "source_module": "crm",
            "source_type": "invoice",
            "source_id": "inv-200",
            "created_by": "ledger-user",
            "lines": [
                {"account_id": cash["id"], "debit_amount": "100", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                {"account_id": revenue["id"], "debit_amount": "0", "credit_amount": "100", "currency": "USD", "fx_rate_to_company_base": "1"},
            ],
        },
        headers=_headers("C1"),
    )
    assert blocked.status_code == 403


def test_posting_entry_blocked_by_fls_policy(client: TestClient) -> None:
    accounts = _seed_accounts(client, "C1")
    cash = next(item for item in accounts if item["code"] == "1000")
    revenue = next(item for item in accounts if item["code"] == "4000")

    set_policy_backend(InMemoryPolicyBackend(default_allow=False))
    try:
        denied = client.post(
            "/ledger/journal-entries",
            json={
                "tenant_id": "tenant-a",
                "company_code": "C1",
                "entry_date": "2026-02-25",
                "description": "FLS Denied",
                "source_module": "crm",
                "source_type": "invoice",
                "source_id": "inv-300",
                "created_by": "ledger-user",
                "lines": [
                    {"account_id": cash["id"], "debit_amount": "100", "credit_amount": "0", "currency": "USD", "fx_rate_to_company_base": "1"},
                    {"account_id": revenue["id"], "debit_amount": "0", "credit_amount": "100", "currency": "USD", "fx_rate_to_company_base": "1"},
                ],
            },
            headers=_headers("C1"),
        )
    finally:
        set_policy_backend(InMemoryPolicyBackend(default_allow=True))

    assert denied.status_code == 403
