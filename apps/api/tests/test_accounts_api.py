from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.service import ActorUser
from app.main import app


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

    legal_entity_id = uuid.uuid4()

    def override_get_current_user() -> ActorUser:
        return ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entity_id],
            current_legal_entity_id=legal_entity_id,
            permissions={
                "crm.accounts.read",
                "crm.accounts.write",
                "crm.accounts.delete",
                "crm.accounts.delete_force",
            },
            correlation_id="corr-test",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        test_client.headers.update({"x-request-id": "corr-test"})
        yield test_client
    app.dependency_overrides.clear()


def test_create_account_success(client: TestClient) -> None:
    audit.audit_entries.clear()
    events.published_events.clear()
    legal_entity_id = uuid.uuid4()

    response = client.post(
        "/api/crm/accounts",
        json={
            "name": "Acme Inc",
            "legal_entity_ids": [str(legal_entity_id)],
            "default_currency_code": "USD",
        },
        headers={"Idempotency-Key": "idem-1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Inc"
    assert str(legal_entity_id) in body["legal_entity_ids"]
    assert any(entry["action"] == "create" for entry in audit.audit_entries)
    assert any(event["event_type"] == "crm.account.created" for event in events.published_events)


def test_create_account_missing_name(client: TestClient) -> None:
    response = client.post(
        "/api/crm/accounts",
        json={"legal_entity_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 422


def test_list_accounts_scoped(db_session: Session, client: TestClient) -> None:
    allowed_legal_entity = uuid.uuid4()
    blocked_legal_entity = uuid.uuid4()

    response_allowed = client.post(
        "/api/crm/accounts",
        json={"name": "Visible Account", "legal_entity_ids": [str(allowed_legal_entity)]},
    )
    assert response_allowed.status_code == 201

    response_blocked = client.post(
        "/api/crm/accounts",
        json={"name": "Hidden Account", "legal_entity_ids": [str(blocked_legal_entity)]},
    )
    assert response_blocked.status_code == 201

    def scoped_user() -> ActorUser:
        return ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[allowed_legal_entity],
            current_legal_entity_id=allowed_legal_entity,
            permissions={"crm.accounts.read", "crm.accounts.write", "crm.accounts.delete"},
            correlation_id="corr-test",
        )

    app.dependency_overrides[get_current_user] = scoped_user
    response = client.get("/api/crm/accounts")
    assert response.status_code == 200
    names = [account["name"] for account in response.json()]
    assert "Visible Account" in names
    assert "Hidden Account" not in names


def test_update_account_row_version_conflict(client: TestClient) -> None:
    create_response = client.post(
        "/api/crm/accounts",
        json={"name": "Conflict Account"},
    )
    assert create_response.status_code == 201
    account = create_response.json()

    first_patch = client.patch(
        f"/api/crm/accounts/{account['id']}",
        json={"row_version": account["row_version"], "name": "Updated Once"},
    )
    assert first_patch.status_code == 200

    second_patch = client.patch(
        f"/api/crm/accounts/{account['id']}",
        json={"row_version": account["row_version"], "name": "Stale Update"},
    )
    assert second_patch.status_code == 409


def test_soft_delete_prevent_if_dependent(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    create_response = client.post(
        "/api/crm/accounts",
        json={"name": "Delete Account"},
    )
    assert create_response.status_code == 201
    account_id = create_response.json()["id"]

    from app.crm.api import service

    monkeypatch.setattr(
        service,
        "_count_dependencies",
        lambda _session, _account_id: {"contacts": 1, "opportunities": 0},
    )

    blocked_delete = client.delete(f"/api/crm/accounts/{account_id}")
    assert blocked_delete.status_code == 422

    forced_delete = client.delete(f"/api/crm/accounts/{account_id}?force=true")
    assert forced_delete.status_code == 200
