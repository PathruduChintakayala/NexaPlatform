from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact, CRMLead
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


@pytest.fixture(autouse=True)
def clear_audit_entries() -> Generator[None, None, None]:
    audit.audit_entries.clear()
    try:
        yield
    finally:
        audit.audit_entries.clear()


@pytest.fixture()
def legal_entities() -> dict[str, uuid.UUID]:
    return {"le1": uuid.uuid4(), "le2": uuid.uuid4()}


@pytest.fixture()
def seeded_entities(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    account_le1 = CRMAccount(name="Account LE1", status="Active")
    account_le2 = CRMAccount(name="Account LE2", status="Active")
    db_session.add_all([account_le1, account_le2])
    db_session.flush()

    db_session.add_all(
        [
            CRMAccountLegalEntity(account_id=account_le1.id, legal_entity_id=legal_entities["le1"], is_default=True),
            CRMAccountLegalEntity(account_id=account_le2.id, legal_entity_id=legal_entities["le2"], is_default=True),
        ]
    )

    contact_le1 = CRMContact(account_id=account_le1.id, first_name="Le", last_name="One", email="le1@example.com")
    contact_le2 = CRMContact(account_id=account_le2.id, first_name="Le", last_name="Two", email="le2@example.com")

    lead_le1 = CRMLead(status="Qualified", source="Web", selling_legal_entity_id=legal_entities["le1"], region_code="US")
    lead_le2 = CRMLead(status="Qualified", source="Web", selling_legal_entity_id=legal_entities["le2"], region_code="US")

    db_session.add_all([contact_le1, contact_le2, lead_le1, lead_le2])
    db_session.commit()

    return {
        "account_le1": account_le1.id,
        "account_le2": account_le2.id,
        "contact_le1": contact_le1.id,
        "contact_le2": contact_le2.id,
        "lead_le1": lead_le1.id,
        "lead_le2": lead_le2.id,
    }


@pytest.fixture()
def seeded_audit(seeded_entities: dict[str, uuid.UUID]) -> dict[str, str]:
    base_time = datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)

    def add(
        *,
        actor: str,
        entity_type: str,
        entity_id: uuid.UUID,
        action: str,
        correlation_id: str,
        time_offset_hours: int,
    ) -> str:
        audit.record(
            actor_user_id=actor,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            before={"old": True},
            after={"new": True},
            correlation_id=correlation_id,
        )
        entry = audit.audit_entries[-1]
        entry["occurred_at"] = (base_time + timedelta(hours=time_offset_hours)).isoformat()
        return str(entry["id"])

    return {
        "e1": add(
            actor="user-1",
            entity_type="crm.account",
            entity_id=seeded_entities["account_le1"],
            action="create",
            correlation_id="corr-a",
            time_offset_hours=0,
        ),
        "e2": add(
            actor="user-2",
            entity_type="crm.account",
            entity_id=seeded_entities["account_le2"],
            action="update",
            correlation_id="corr-b",
            time_offset_hours=1,
        ),
        "e3": add(
            actor="user-1",
            entity_type="crm.contact",
            entity_id=seeded_entities["contact_le1"],
            action="update",
            correlation_id="corr-a",
            time_offset_hours=2,
        ),
        "e4": add(
            actor="user-1",
            entity_type="crm.lead",
            entity_id=seeded_entities["lead_le1"],
            action="disqualify",
            correlation_id="corr-c",
            time_offset_hours=3,
        ),
        "e5": add(
            actor="user-2",
            entity_type="crm.lead",
            entity_id=seeded_entities["lead_le2"],
            action="convert",
            correlation_id="corr-z",
            time_offset_hours=4,
        ),
    }


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
            permissions={"crm.audit.read"},
            correlation_id="corr-audit",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={"crm.audit.read"},
            correlation_id="corr-audit",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={"crm.audit.read", "crm.audit.read_all"},
            correlation_id="corr-audit",
        ),
        "noaudit": ActorUser(
            user_id="no-audit",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions=set(),
            correlation_id="corr-audit",
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


def test_entity_scoped_visibility(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("user1")

    response = test_client.get("/api/crm/audit")
    assert response.status_code == 200

    rows = response.json()
    ids = {row["id"] for row in rows}
    assert seeded_audit["e1"] in ids
    assert seeded_audit["e3"] in ids
    assert seeded_audit["e4"] in ids
    assert seeded_audit["e2"] not in ids
    assert seeded_audit["e5"] not in ids


def test_cross_entity_blocking(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_entities: dict[str, uuid.UUID],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("user1")

    blocked = test_client.get(f"/api/crm/entities/account/{seeded_entities['account_le2']}/audit")
    assert blocked.status_code == 404


def test_actor_filter(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    response = test_client.get("/api/crm/audit?actor_user_id=user-2")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert all(row["actor_user_id"] == "user-2" for row in rows)


def test_date_range_filter(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    response = test_client.get("/api/crm/audit", params={"date_from": "2026-02-24T12:30:00Z", "date_to": "2026-02-24T13:30:00Z"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == seeded_audit["e4"]


def test_correlation_id_filter(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    response = test_client.get("/api/crm/audit?correlation_id=corr-a")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {row["id"] for row in rows} == {seeded_audit["e1"], seeded_audit["e3"]}


def test_permission_enforcement(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("noaudit")

    response = test_client.get("/api/crm/audit")
    assert response.status_code == 403


def test_pagination_ordering(
    client: tuple[TestClient, Callable[[str], None]],
    seeded_audit: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    first_page = test_client.get("/api/crm/audit?limit=2")
    assert first_page.status_code == 200
    first_rows = first_page.json()
    assert [row["id"] for row in first_rows] == [seeded_audit["e5"], seeded_audit["e4"]]

    second_page = test_client.get("/api/crm/audit?limit=2&cursor=2")
    assert second_page.status_code == 200
    second_rows = second_page.json()
    assert [row["id"] for row in second_rows] == [seeded_audit["e3"], seeded_audit["e2"]]
