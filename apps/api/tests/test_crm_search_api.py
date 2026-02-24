from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import events
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity
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
def accounts(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    a1 = CRMAccount(name="Acme Account", status="Active")
    a2 = CRMAccount(name="Blocked Account", status="Active")
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

    base_perms = {
        "crm.search.read",
        "crm.accounts.read",
        "crm.accounts.write",
        "crm.contacts.create",
        "crm.contacts.read",
        "crm.leads.create",
        "crm.leads.read",
        "crm.opportunities.create",
        "crm.opportunities.read",
        "crm.opportunities.close_won",
    }

    actors = {
        "user1": ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions=set(base_perms),
            correlation_id="corr-search",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions=set(base_perms),
            correlation_id="corr-search",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={
                *base_perms,
                "crm.search.read",
                "crm.accounts.read_all",
                "crm.contacts.read_all",
                "crm.leads.read_all",
                "crm.leads.create_all",
                "crm.opportunities.read_all",
                "crm.pipelines.manage",
                "crm.opportunities.create_all",
            },
            correlation_id="corr-search",
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


def _setup_pipeline(test_client: TestClient, legal_entity_id: uuid.UUID) -> dict[str, str]:
    pipeline = test_client.post(
        "/api/crm/pipelines",
        json={"name": "Search Pipeline", "selling_legal_entity_id": str(legal_entity_id), "is_default": True},
    )
    assert pipeline.status_code == 201
    pipeline_id = pipeline.json()["id"]

    open_stage = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Open", "position": 1, "stage_type": "Open"},
    )
    assert open_stage.status_code == 201

    won_stage = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Won", "position": 90, "stage_type": "ClosedWon"},
    )
    assert won_stage.status_code == 201

    return {"open": open_stage.json()["id"], "won": won_stage.json()["id"]}


def test_global_search_type_filter_and_limit(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    account = test_client.post(
        "/api/crm/accounts",
        json={"name": "Acme Parent", "legal_entity_ids": [str(legal_entities["le1"])]},
    )
    assert account.status_code == 201
    account_id = account.json()["id"]

    contact = test_client.post(
        f"/api/crm/accounts/{account_id}/contacts",
        json={"account_id": account_id, "first_name": "Acme", "last_name": "Contact"},
    )
    assert contact.status_code == 201

    lead = test_client.post(
        "/api/crm/leads",
        json={
            "status": "Qualified",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entities["le1"]),
            "region_code": "US",
            "company_name": "Acme Lead",
        },
    )
    assert lead.status_code == 201

    _setup_pipeline(test_client, legal_entities["le1"])
    opportunity = test_client.post(
        "/api/crm/opportunities",
        json={
            "account_id": account_id,
            "name": "Acme Deal",
            "selling_legal_entity_id": str(legal_entities["le1"]),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 100,
        },
    )
    assert opportunity.status_code == 201

    all_types = test_client.get("/api/crm/search?q=acme&limit=20")
    assert all_types.status_code == 200
    all_result_types = {item["entity_type"] for item in all_types.json()}
    assert {"account", "contact", "lead", "opportunity"}.issubset(all_result_types)

    filtered = test_client.get("/api/crm/search?q=acme&types=lead,opportunity&limit=20")
    assert filtered.status_code == 200
    filtered_types = {item["entity_type"] for item in filtered.json()}
    assert filtered_types <= {"lead", "opportunity"}

    limited = test_client.get("/api/crm/search?q=acme&limit=2")
    assert limited.status_code == 200
    assert len(limited.json()) <= 2


def test_global_search_scoping_respects_allowed_legal_entities(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client

    set_actor("user1")
    lead_user1 = test_client.post(
        "/api/crm/leads",
        json={
            "status": "New",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entities["le1"]),
            "region_code": "US",
            "company_name": "Scoped Alpha",
        },
    )
    assert lead_user1.status_code == 201

    set_actor("user2")
    lead_user2 = test_client.post(
        "/api/crm/leads",
        json={
            "status": "New",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entities["le2"]),
            "region_code": "US",
            "company_name": "Scoped Alpha",
        },
    )
    assert lead_user2.status_code == 201

    set_actor("user1")
    scoped = test_client.get("/api/crm/search?q=scoped&types=lead")
    assert scoped.status_code == 200
    ids = {row["entity_id"] for row in scoped.json()}
    assert lead_user1.json()["id"] in ids
    assert lead_user2.json()["id"] not in ids


def test_search_index_events_and_idempotent_retry_does_not_duplicate(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")
    events.published_events.clear()

    account = test_client.post(
        "/api/crm/accounts",
        json={"name": "Search Hooks", "legal_entity_ids": [str(legal_entities["le1"])]},
    )
    assert account.status_code == 201
    account_id = account.json()["id"]

    contact = test_client.post(
        f"/api/crm/accounts/{account_id}/contacts",
        json={"account_id": account_id, "first_name": "Index", "last_name": "Contact"},
    )
    assert contact.status_code == 201

    lead = test_client.post(
        "/api/crm/leads",
        json={
            "status": "Qualified",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entities["le1"]),
            "region_code": "US",
            "company_name": "Index Lead",
        },
    )
    assert lead.status_code == 201

    _setup_pipeline(test_client, legal_entities["le1"])
    opportunity = test_client.post(
        "/api/crm/opportunities",
        json={
            "account_id": account_id,
            "name": "Index Deal",
            "selling_legal_entity_id": str(legal_entities["le1"]),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 300,
        },
    )
    assert opportunity.status_code == 201

    search_events = [event for event in events.published_events if event["event_type"] == "crm.search.index_requested"]
    entity_types = {event["payload"]["entity_type"] for event in search_events}
    assert {"account", "contact", "lead", "opportunity"}.issubset(entity_types)

    close_payload = {
        "row_version": opportunity.json()["row_version"],
        "revenue_handoff_mode": "manual",
        "revenue_handoff_requested": False,
    }
    first_close = test_client.post(
        f"/api/crm/opportunities/{opportunity.json()['id']}/close-won",
        json=close_payload,
        headers={"Idempotency-Key": "close-key-1"},
    )
    assert first_close.status_code == 200

    before_retry_count = len(
        [event for event in events.published_events if event["event_type"] == "crm.search.index_requested"]
    )

    second_close = test_client.post(
        f"/api/crm/opportunities/{opportunity.json()['id']}/close-won",
        json=close_payload,
        headers={"Idempotency-Key": "close-key-1"},
    )
    assert second_close.status_code == 200

    after_retry_count = len(
        [event for event in events.published_events if event["event_type"] == "crm.search.index_requested"]
    )
    assert after_retry_count == before_retry_count
