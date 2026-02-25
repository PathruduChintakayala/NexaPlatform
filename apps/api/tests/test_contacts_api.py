from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity
from app.crm.service import ActorUser
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
def legal_entities() -> dict[str, uuid.UUID]:
    return {"le1": uuid.uuid4(), "le2": uuid.uuid4()}


@pytest.fixture()
def accounts(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    a1 = CRMAccount(name="A1", status="Active")
    a2 = CRMAccount(name="A2", status="Active")
    db_session.add_all([a1, a2])
    db_session.flush()

    db_session.add_all(
        [
            CRMAccountLegalEntity(account_id=a1.id, legal_entity_id=legal_entities["le1"], is_default=True),
            CRMAccountLegalEntity(account_id=a2.id, legal_entity_id=legal_entities["le2"], is_default=True),
        ]
    )
    db_session.commit()
    return {"a1": a1.id, "a2": a2.id}


@pytest.fixture()
def client(
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> Generator[tuple[TestClient, Callable[[str], None]], None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    actors = {
        "user1": ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={
                "crm.contacts.create",
                "crm.contacts.read",
                "crm.contacts.update",
                "crm.contacts.delete",
            },
            correlation_id="corr-contact",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={
                "crm.contacts.create",
                "crm.contacts.read",
                "crm.contacts.update",
                "crm.contacts.delete",
            },
            correlation_id="corr-contact",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={
                "crm.contacts.create",
                "crm.contacts.read",
                "crm.contacts.update",
                "crm.contacts.delete",
                "crm.contacts.read_all",
            },
            correlation_id="corr-contact",
        ),
    }
    state = {"current": "user1"}

    def override_get_current_user() -> ActorUser:
        return actors[state["current"]]

    def set_actor(name: str) -> None:
        state["current"] = name

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client, set_actor
    app.dependency_overrides.clear()


def test_create_contact_success(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    audit.audit_entries.clear()
    events.published_events.clear()

    response = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "is_primary": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["account_id"] == str(accounts["a1"])
    assert any(entry["action"] == "create" for entry in audit.audit_entries)
    assert any(event["event_type"] == "crm.contact.created" for event in events.published_events)


def test_create_contact_blocks_inactive_account(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    account = db_session.get(CRMAccount, accounts["a1"])
    assert account is not None
    account.status = "Inactive"
    db_session.add(account)
    db_session.commit()

    response = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "John",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 422


def test_primary_contact_enforced(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client

    first = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Primary",
            "last_name": "One",
            "is_primary": True,
        },
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Primary",
            "last_name": "Two",
            "is_primary": True,
        },
    )
    assert second.status_code in {201, 409}

    contacts = test_client.get(f"/api/crm/accounts/{accounts['a1']}/contacts")
    assert contacts.status_code == 200
    rows = contacts.json()
    primaries = [row for row in rows if row["is_primary"]]
    assert len(primaries) <= 1
    if second.status_code == 201:
        assert len(primaries) == 1
        assert primaries[0]["id"] != first_id


def test_primary_unique_conflict_race(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    first = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Race",
            "last_name": "One",
            "is_primary": True,
        },
    )
    assert first.status_code == 201

    second = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Race",
            "last_name": "Two",
            "is_primary": True,
        },
    )
    assert second.status_code in {201, 409}


def test_list_contacts_scoped_by_account_legal_entity(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client

    create_other = test_client.post(
        f"/api/crm/accounts/{accounts['a2']}/contacts",
        json={
            "account_id": str(accounts["a2"]),
            "first_name": "Other",
            "last_name": "Entity",
        },
    )
    assert create_other.status_code == 404

    list_other = test_client.get(f"/api/crm/accounts/{accounts['a2']}/contacts")
    assert list_other.status_code == 404


def test_update_contact_blocked_for_out_of_scope_company(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client

    set_actor("user2")
    created = test_client.post(
        f"/api/crm/accounts/{accounts['a2']}/contacts",
        json={
            "account_id": str(accounts["a2"]),
            "first_name": "Scoped",
            "last_name": "Target",
        },
    )
    assert created.status_code == 201
    contact = created.json()

    set_actor("user1")
    blocked = test_client.patch(
        f"/api/crm/contacts/{contact['id']}",
        json={"row_version": contact["row_version"], "title": "Director"},
    )
    assert blocked.status_code in {403, 404}


def test_update_contact_row_version_conflict(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    create = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Update",
            "last_name": "Me",
        },
    )
    assert create.status_code == 201
    contact = create.json()

    first_patch = test_client.patch(
        f"/api/crm/contacts/{contact['id']}",
        json={"row_version": contact["row_version"], "title": "Director"},
    )
    assert first_patch.status_code == 200

    stale_patch = test_client.patch(
        f"/api/crm/contacts/{contact['id']}",
        json={"row_version": contact["row_version"], "title": "VP"},
    )
    assert stale_patch.status_code == 409


def test_delete_contact_soft(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    create = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Soft",
            "last_name": "Delete",
        },
    )
    assert create.status_code == 201
    contact_id = create.json()["id"]

    deleted = test_client.delete(f"/api/crm/contacts/{contact_id}")
    assert deleted.status_code == 200

    listed = test_client.get(f"/api/crm/accounts/{accounts['a1']}/contacts")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert contact_id not in ids


def test_update_contact_forbidden_field_by_fls(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
) -> None:
    test_client, _set_actor = client
    created = test_client.post(
        f"/api/crm/accounts/{accounts['a1']}/contacts",
        json={
            "account_id": str(accounts["a1"]),
            "first_name": "Fls",
            "last_name": "Target",
        },
    )
    assert created.status_code == 201
    contact = created.json()

    set_policy_backend(InMemoryPolicyBackend(default_allow=False))
    try:
        response = test_client.patch(
            f"/api/crm/contacts/{contact['id']}",
            json={"row_version": contact["row_version"], "title": "Director"},
        )
    finally:
        set_policy_backend(InMemoryPolicyBackend(default_allow=True))

    assert response.status_code == 403
    body = response.json()
    detail = body.get("detail", body.get("error", body))
    assert "forbidden_fields" in str(detail)
