from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.service import ActorUser
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter


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
def setup_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "true")
    get_settings.cache_clear()
    reset_rate_limiter()
    audit.audit_entries.clear()
    events.published_events.clear()
    yield
    get_settings.cache_clear()
    reset_rate_limiter()
    audit.audit_entries.clear()
    events.published_events.clear()


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
                "crm.custom_fields.read",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
            },
            correlation_id="cf-corr-1",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={
                "crm.custom_fields.read",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
            },
            correlation_id="cf-corr-2",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[legal_entities["le1"], legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={
                "crm.custom_fields.read",
                "crm.custom_fields.manage",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
                "crm.leads.create_all",
                "crm.leads.read_all",
            },
            correlation_id="cf-corr-admin",
        ),
    }
    state = {"current": "admin"}

    def override_get_current_user() -> ActorUser:
        return actors[state["current"]]

    def set_actor(name: str) -> None:
        state["current"] = name

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client, set_actor
    app.dependency_overrides.clear()


def _create_lead_payload(legal_entity_id: uuid.UUID, custom_fields: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "New",
        "source": "Web",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "company_name": "CF Lead",
    }
    if custom_fields is not None:
        payload["custom_fields"] = custom_fields
    return payload


def _create_definition(
    test_client: TestClient,
    entity_type: str,
    *,
    field_key: str,
    label: str,
    data_type: str,
    legal_entity_id: uuid.UUID | None = None,
    is_required: bool = False,
    allowed_values: list[str] | None = None,
    is_active: bool = True,
) -> dict:
    body: dict[str, object] = {
        "field_key": field_key,
        "label": label,
        "data_type": data_type,
        "is_required": is_required,
        "is_active": is_active,
    }
    if legal_entity_id is not None:
        body["legal_entity_id"] = str(legal_entity_id)
    if allowed_values is not None:
        body["allowed_values"] = allowed_values

    response = test_client.post(f"/api/crm/custom-fields/{entity_type}", json=body)
    assert response.status_code == 201
    return response.json()


def test_create_definition_global_and_legal_entity_override(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    global_def = _create_definition(
        test_client,
        "lead",
        field_key="priority",
        label="Priority",
        data_type="select",
        allowed_values=["low", "high"],
    )
    le_override = _create_definition(
        test_client,
        "lead",
        field_key="priority",
        label="Priority LE1",
        data_type="select",
        legal_entity_id=legal_entities["le1"],
        allowed_values=["low", "high", "urgent"],
    )

    listed = test_client.get(f"/api/crm/custom-fields/lead?legal_entity_id={legal_entities['le1']}")
    assert listed.status_code == 200
    rows = listed.json()
    priority_rows = [row for row in rows if row["field_key"] == "priority"]
    assert len(priority_rows) == 1
    assert priority_rows[0]["id"] == le_override["id"]
    assert priority_rows[0]["label"] == "Priority LE1"
    assert global_def["field_key"] == "priority"


def test_list_definitions_respects_scope_and_active_flag(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    _create_definition(test_client, "lead", field_key="global_text", label="Global", data_type="text")
    _create_definition(
        test_client,
        "lead",
        field_key="le_only",
        label="LE Only",
        data_type="text",
        legal_entity_id=legal_entities["le1"],
        is_active=False,
    )

    active = test_client.get(f"/api/crm/custom-fields/lead?legal_entity_id={legal_entities['le1']}")
    assert active.status_code == 200
    active_keys = {row["field_key"] for row in active.json()}
    assert "global_text" in active_keys
    assert "le_only" not in active_keys

    with_inactive = test_client.get(
        f"/api/crm/custom-fields/lead?legal_entity_id={legal_entities['le1']}&include_inactive=true"
    )
    assert with_inactive.status_code == 200
    all_keys = {row["field_key"] for row in with_inactive.json()}
    assert "le_only" in all_keys


def test_set_get_custom_fields_on_lead_create_and_update_valid_types(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    _create_definition(test_client, "lead", field_key="notes", label="Notes", data_type="text")
    _create_definition(test_client, "lead", field_key="score", label="Score", data_type="number")
    _create_definition(test_client, "lead", field_key="vip", label="VIP", data_type="bool")
    _create_definition(test_client, "lead", field_key="go_live", label="Go Live", data_type="date")
    _create_definition(
        test_client,
        "lead",
        field_key="segment",
        label="Segment",
        data_type="select",
        allowed_values=["mid", "enterprise"],
    )

    set_actor("user1")
    created = test_client.post(
        "/api/crm/leads",
        json=_create_lead_payload(
            legal_entities["le1"],
            {
                "notes": "hello",
                "score": 42,
                "vip": True,
                "go_live": "2026-12-31",
                "segment": "enterprise",
            },
        ),
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["custom_fields"]["notes"] == "hello"
    assert created_body["custom_fields"]["score"] == 42.0
    assert created_body["custom_fields"]["vip"] is True
    assert created_body["custom_fields"]["go_live"] == "2026-12-31"
    assert created_body["custom_fields"]["segment"] == "enterprise"

    updated = test_client.patch(
        f"/api/crm/leads/{created_body['id']}",
        json={"row_version": created_body["row_version"], "custom_fields": {"notes": "updated", "score": 77}},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["custom_fields"]["notes"] == "updated"
    assert updated_body["custom_fields"]["score"] == 77.0


def test_invalid_custom_field_type_and_select_value_rejected(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    _create_definition(test_client, "lead", field_key="score", label="Score", data_type="number")
    _create_definition(
        test_client,
        "lead",
        field_key="segment",
        label="Segment",
        data_type="select",
        allowed_values=["mid", "enterprise"],
    )

    set_actor("user1")
    invalid_type = test_client.post(
        "/api/crm/leads",
        json=_create_lead_payload(legal_entities["le1"], {"score": "bad"}),
    )
    assert invalid_type.status_code == 422

    invalid_select = test_client.post(
        "/api/crm/leads",
        json=_create_lead_payload(legal_entities["le1"], {"segment": "other"}),
    )
    assert invalid_select.status_code == 422


def test_required_custom_field_enforced_on_create(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    _create_definition(
        test_client,
        "lead",
        field_key="required_code",
        label="Required Code",
        data_type="text",
        is_required=True,
    )

    set_actor("user1")
    missing_required = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert missing_required.status_code == 422


def test_scoping_blocks_using_other_legal_entity_definition(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    _create_definition(
        test_client,
        "lead",
        field_key="le2_only",
        label="LE2 Only",
        data_type="text",
        legal_entity_id=legal_entities["le2"],
    )

    set_actor("user1")
    blocked = test_client.post(
        "/api/crm/leads",
        json=_create_lead_payload(legal_entities["le1"], {"le2_only": "x"}),
    )
    assert blocked.status_code == 422


def test_audit_and_search_event_include_custom_fields(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    _create_definition(test_client, "lead", field_key="notes", label="Notes", data_type="text")

    set_actor("user1")
    created = test_client.post(
        "/api/crm/leads",
        json=_create_lead_payload(legal_entities["le1"], {"notes": "from-audit"}),
        headers={"X-Correlation-Id": "abc-123"},
    )
    assert created.status_code == 201
    body = created.json()

    updated = test_client.patch(
        f"/api/crm/leads/{body['id']}",
        json={"row_version": body["row_version"], "custom_fields": {"notes": "changed"}},
        headers={"X-Correlation-Id": "abc-123"},
    )
    assert updated.status_code == 200

    lead_audits = [item for item in audit.audit_entries if item["entity_type"] == "crm.lead"]
    assert lead_audits
    assert any((entry.get("after") or {}).get("custom_fields", {}).get("notes") for entry in lead_audits)

    search_events = [event for event in events.published_events if event.get("event_type") == "crm.search.index_requested"]
    assert search_events
    lead_search_events = [event for event in search_events if event.get("payload", {}).get("entity_type") == "lead"]
    assert lead_search_events
    assert any(
        (event.get("payload", {}).get("fields", {}).get("custom_fields", {}) or {}).get("notes") in {"from-audit", "changed"}
        for event in lead_search_events
    )
