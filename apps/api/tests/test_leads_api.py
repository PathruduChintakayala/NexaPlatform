from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMContact, CRMLead
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
def legal_entities() -> dict[str, uuid.UUID]:
    return {"le1": uuid.uuid4(), "le2": uuid.uuid4()}


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
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
                "crm.leads.disqualify",
                "crm.leads.convert",
                "crm.contacts.create",
            },
            correlation_id="corr-lead",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
                "crm.leads.disqualify",
                "crm.leads.convert",
                "crm.contacts.create",
            },
            correlation_id="corr-lead",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.read_all",
                "crm.leads.update",
                "crm.leads.disqualify",
                "crm.leads.convert",
                "crm.leads.convert_disqualified",
                "crm.contacts.create",
            },
            correlation_id="corr-lead",
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


def _create_lead_payload(legal_entity_id: uuid.UUID, status: str = "Qualified") -> dict[str, str]:
    return {
        "status": status,
        "source": "Web",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "company_name": "Acme Lead",
        "contact_first_name": "Jamie",
        "contact_last_name": "Smith",
        "email": "jamie@example.com",
        "phone": "+1-555-0100",
    }


def test_create_lead_requires_selling_legal_entity_and_region(
    client: tuple[TestClient, Callable[[str], None]],
) -> None:
    test_client, _ = client
    response = test_client.post(
        "/api/crm/leads",
        json={"status": "New", "source": "Web"},
    )
    assert response.status_code == 422


def test_list_leads_scoped_by_selling_legal_entity(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    create1 = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert create1.status_code == 201

    set_actor("user2")
    create2 = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le2"]))
    assert create2.status_code == 201

    set_actor("user1")
    listed = test_client.get("/api/crm/leads")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["selling_legal_entity_id"] == str(legal_entities["le1"])


def test_disqualify_lead_sets_status_and_reason(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    audit.audit_entries.clear()
    create = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"], status="Working"))
    assert create.status_code == 201
    lead = create.json()

    response = test_client.post(
        f"/api/crm/leads/{lead['id']}/disqualify",
        json={"reason_code": "NO_BUDGET", "notes": "No budget this quarter", "row_version": lead["row_version"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Disqualified"
    assert body["disqualify_reason_code"] == "NO_BUDGET"
    assert any(entry["action"] == "disqualify" for entry in audit.audit_entries)


def test_convert_lead_atomic_creates_account_contact_and_sets_converted_fields(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
) -> None:
    test_client, _ = client
    audit.audit_entries.clear()
    events.published_events.clear()

    create = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"], status="Qualified"))
    assert create.status_code == 201
    lead = create.json()

    convert = test_client.post(
        f"/api/crm/leads/{lead['id']}/convert",
        json={
            "row_version": lead["row_version"],
            "account": {"mode": "new", "name": "Converted Co", "legal_entity_ids": [str(legal_entities["le1"])]},
            "contact": {"mode": "new", "first_name": "Jamie", "last_name": "Smith", "is_primary": True},
            "create_opportunity": False,
        },
        headers={"Idempotency-Key": "conv-key-1"},
    )
    assert convert.status_code == 200
    body = convert.json()
    assert body["status"] == "Converted"
    assert body["converted_account_id"] is not None
    assert body["converted_contact_id"] is not None
    assert body["converted_at"] is not None
    assert any(entry["action"] == "convert" for entry in audit.audit_entries)
    assert any(event["event_type"] == "crm.lead.converted" for event in events.published_events)

    account_count = db_session.scalar(select(func.count()).select_from(CRMAccount))
    contact_count = db_session.scalar(select(func.count()).select_from(CRMContact))
    assert int(account_count or 0) == 1
    assert int(contact_count or 0) == 1


def test_convert_lead_idempotent_with_idempotency_key(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
) -> None:
    test_client, _ = client
    create = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"], status="Qualified"))
    assert create.status_code == 201
    lead = create.json()

    payload = {
        "row_version": lead["row_version"],
        "account": {"mode": "new", "name": "Idempotent Co", "legal_entity_ids": [str(legal_entities["le1"])]},
        "contact": {"mode": "new", "first_name": "Ida", "last_name": "Potent", "is_primary": True},
        "create_opportunity": False,
    }

    first = test_client.post(
        f"/api/crm/leads/{lead['id']}/convert",
        json=payload,
        headers={"Idempotency-Key": "conv-key-2"},
    )
    assert first.status_code == 200

    second = test_client.post(
        f"/api/crm/leads/{lead['id']}/convert",
        json=payload,
        headers={"Idempotency-Key": "conv-key-2"},
    )
    assert second.status_code == 200
    assert first.json()["converted_account_id"] == second.json()["converted_account_id"]
    assert first.json()["converted_contact_id"] == second.json()["converted_contact_id"]

    account_count = db_session.scalar(select(func.count()).select_from(CRMAccount))
    contact_count = db_session.scalar(select(func.count()).select_from(CRMContact))
    lead_count = db_session.scalar(select(func.count()).select_from(CRMLead))
    assert int(account_count or 0) == 1
    assert int(contact_count or 0) == 1
    assert int(lead_count or 0) == 1


def test_convert_disqualified_blocked(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    create = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"], status="Working"))
    assert create.status_code == 201
    lead = create.json()

    dq = test_client.post(
        f"/api/crm/leads/{lead['id']}/disqualify",
        json={"reason_code": "NOT_A_FIT", "row_version": lead["row_version"]},
    )
    assert dq.status_code == 200
    disqualified = dq.json()

    convert = test_client.post(
        f"/api/crm/leads/{lead['id']}/convert",
        json={
            "row_version": disqualified["row_version"],
            "account": {"mode": "new", "name": "Blocked Co", "legal_entity_ids": [str(legal_entities["le1"])]},
            "contact": {"mode": "new", "first_name": "Blocked", "last_name": "Lead"},
            "create_opportunity": False,
        },
    )
    assert convert.status_code == 422


def test_update_lead_row_version_conflict(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    create = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"], status="Working"))
    assert create.status_code == 201
    lead = create.json()

    first = test_client.patch(
        f"/api/crm/leads/{lead['id']}",
        json={"row_version": lead["row_version"], "qualification_notes": "Updated once"},
    )
    assert first.status_code == 200

    stale = test_client.patch(
        f"/api/crm/leads/{lead['id']}",
        json={"row_version": lead["row_version"], "qualification_notes": "Updated stale"},
    )
    assert stale.status_code == 409
