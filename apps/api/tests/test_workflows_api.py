from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMActivity, CRMLead, CRMNotificationIntent
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
    assigned_user_id = uuid.uuid4()
    notify_user_id = uuid.uuid4()
    actors = {
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[legal_entities["le1"], legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={
                "crm.workflows.read",
                "crm.workflows.manage",
                "crm.workflows.execute",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.read_all",
                "crm.leads.update",
                "crm.custom_fields.manage",
                "crm.custom_fields.read",
            },
            correlation_id="wf-admin-corr",
        ),
        "executor": ActorUser(
            user_id="executor-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={
                "crm.workflows.read",
                "crm.workflows.execute",
                "crm.leads.read",
            },
            correlation_id="wf-exec-corr",
        ),
        "viewer": ActorUser(
            user_id="viewer-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={"crm.workflows.read", "crm.leads.read"},
            correlation_id="wf-view-corr",
        ),
        "le2_user": ActorUser(
            user_id="le2-user",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={"crm.workflows.read", "crm.workflows.execute", "crm.leads.read"},
            correlation_id="wf-le2-corr",
        ),
    }
    state = {"current": "admin"}

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user() -> ActorUser:
        return actors[state["current"]]

    def set_actor(name: str) -> None:
        state["current"] = name

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        test_client.app_state = {
            "assigned_user_id": assigned_user_id,
            "notify_user_id": notify_user_id,
        }
        yield test_client, set_actor
    app.dependency_overrides.clear()


def _create_lead_payload(legal_entity_id: uuid.UUID, *, owner_user_id: uuid.UUID | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "New",
        "source": "Web",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "company_name": "Acme Corp",
        "qualification_notes": "Initial",
    }
    if owner_user_id is not None:
        payload["owner_user_id"] = str(owner_user_id)
    return payload


def _create_rule(test_client: TestClient, body: dict[str, object]) -> dict[str, object]:
    response = test_client.post("/api/crm/workflows", json=body)
    assert response.status_code == 201
    return response.json()


def _create_custom_field_definition(
    test_client: TestClient,
    *,
    entity_type: str,
    field_key: str,
    label: str,
    data_type: str,
    legal_entity_id: uuid.UUID | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "field_key": field_key,
        "label": label,
        "data_type": data_type,
    }
    if legal_entity_id is not None:
        payload["legal_entity_id"] = str(legal_entity_id)
    response = test_client.post(f"/api/crm/custom-fields/{entity_type}", json=payload)
    assert response.status_code == 201
    return response.json()


def test_workflow_rule_crud_and_rbac(
    client: tuple[TestClient, Callable[[str], None]],
) -> None:
    test_client, set_actor = client

    set_actor("viewer")
    forbidden_create = test_client.post(
        "/api/crm/workflows",
        json={
            "name": "Nope",
            "trigger_event": "crm.lead.created",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "status", "value": "Qualified"}],
        },
    )
    assert forbidden_create.status_code == 403

    set_actor("admin")
    created = _create_rule(
        test_client,
        {
            "name": "Qualify new lead",
            "trigger_event": "crm.lead.created",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "status", "value": "Qualified"}],
        },
    )

    listed = test_client.get("/api/crm/workflows")
    assert listed.status_code == 200
    assert any(row["id"] == created["id"] for row in listed.json())

    updated = test_client.patch(
        f"/api/crm/workflows/{created['id']}",
        json={"name": "Qualify New Lead", "is_active": True},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Qualify New Lead"

    deleted = test_client.delete(f"/api/crm/workflows/{created['id']}")
    assert deleted.status_code == 200

    listed_after_delete = test_client.get("/api/crm/workflows")
    assert listed_after_delete.status_code == 200
    assert not any(row["id"] == created["id"] for row in listed_after_delete.json())


def test_condition_evaluation_ops_and_custom_field_path(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    _create_custom_field_definition(
        test_client,
        entity_type="lead",
        field_key="score",
        label="Score",
        data_type="number",
    )

    lead_created = test_client.post(
        "/api/crm/leads",
        json={
            **_create_lead_payload(legal_entities["le1"], owner_user_id=uuid.uuid4()),
            "custom_fields": {"score": 42},
        },
    )
    assert lead_created.status_code == 201
    lead = lead_created.json()

    rule = _create_rule(
        test_client,
        {
            "name": "Complex evaluator",
            "trigger_event": "crm.lead.updated",
            "condition_json": {
                "all": [
                    {"path": "status", "op": "eq", "value": "New"},
                    {"path": "company_name", "op": "contains", "value": "Acme"},
                    {"path": "source", "op": "in", "value": ["Web", "Referral"]},
                    {"path": "owner_user_id", "op": "exists"},
                    {"path": "custom_fields.score", "op": "gte", "value": 40},
                    {"path": "custom_fields.score", "op": "lt", "value": 100},
                    {"path": "custom_fields.score", "op": "neq", "value": 30},
                ]
            },
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "Matched by rule"}],
        },
    )

    dry_run = test_client.post(
        f"/api/crm/workflows/{rule['id']}/dry-run",
        json={"entity_type": "lead", "entity_id": lead["id"]},
    )
    assert dry_run.status_code == 200
    body = dry_run.json()
    assert body["matched"] is True
    assert body["planned_actions"][0]["path"] == "qualification_notes"


def test_scoped_rule_enforcement_blocks_mismatched_scope(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    lead_created = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_created.status_code == 201
    lead = lead_created.json()

    scoped_rule = _create_rule(
        test_client,
        {
            "name": "LE2 only",
            "trigger_event": "crm.lead.updated",
            "legal_entity_id": str(legal_entities["le2"]),
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "status", "value": "Qualified"}],
        },
    )

    set_actor("executor")
    blocked = test_client.post(
        f"/api/crm/workflows/{scoped_rule['id']}/execute",
        json={"entity_type": "lead", "entity_id": lead["id"]},
    )
    assert blocked.status_code == 403


def test_dry_run_plans_mutations_without_persisting(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    lead_created = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_created.status_code == 201
    lead = lead_created.json()

    rule = _create_rule(
        test_client,
        {
            "name": "Dry run qualifier",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "status", "value": "Qualified"}],
        },
    )

    dry_run = test_client.post(
        f"/api/crm/workflows/{rule['id']}/dry-run",
        json={"entity_type": "lead", "entity_id": lead["id"]},
    )
    assert dry_run.status_code == 200
    body = dry_run.json()
    assert body["matched"] is True
    assert body["planned_mutations"]["set_field"][0]["after"] == "Qualified"

    persisted_lead = db_session.scalar(select(CRMLead).where(CRMLead.id == uuid.UUID(lead["id"])))
    assert persisted_lead is not None
    assert persisted_lead.status == "New"
    assert any(entry["action"] == "workflow.dry_run" for entry in audit.audit_entries)


def test_execute_persists_setfield_customfield_task_notify_and_audit(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    assigned_user_id = test_client.app_state["assigned_user_id"]
    notify_user_id = test_client.app_state["notify_user_id"]

    set_actor("admin")

    _create_custom_field_definition(
        test_client,
        entity_type="lead",
        field_key="workflow_note",
        label="Workflow Note",
        data_type="text",
    )

    lead_created = test_client.post(
        "/api/crm/leads",
        json={
            **_create_lead_payload(legal_entities["le1"], owner_user_id=notify_user_id),
            "custom_fields": {},
        },
    )
    assert lead_created.status_code == 201
    lead = lead_created.json()

    rule = _create_rule(
        test_client,
        {
            "name": "Full execute",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [
                {"type": "SET_FIELD", "path": "status", "value": "Qualified"},
                {"type": "SET_FIELD", "path": "custom_fields.workflow_note", "value": "created-by-workflow"},
                {
                    "type": "CREATE_TASK",
                    "title": "Follow up call",
                    "due_in_days": 3,
                    "assigned_to_user_id": str(assigned_user_id),
                    "entity_ref": {"type": "lead", "id": lead["id"]},
                },
                {
                    "type": "NOTIFY",
                    "notification_type": "WORKFLOW_ALERT",
                    "payload": {
                        "recipient_user_id": str(notify_user_id),
                        "message": "Workflow fired",
                    },
                },
            ],
        },
    )

    executed = test_client.post(
        f"/api/crm/workflows/{rule['id']}/execute",
        json={"entity_type": "lead", "entity_id": lead["id"]},
    )
    assert executed.status_code == 200
    execute_body = executed.json()
    assert execute_body["matched"] is True
    assert len(execute_body["planned_actions"]) == 4

    refreshed = test_client.get(f"/api/crm/leads/{lead['id']}")
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["status"] == "Qualified"
    assert refreshed_body["custom_fields"]["workflow_note"] == "created-by-workflow"

    task = db_session.scalar(
        select(CRMActivity).where(
            CRMActivity.entity_type == "lead",
            CRMActivity.entity_id == uuid.UUID(lead["id"]),
            CRMActivity.activity_type == "Task",
        )
    )
    assert task is not None
    assert task.assigned_to_user_id == assigned_user_id

    notification = db_session.scalar(
        select(CRMNotificationIntent).where(
            CRMNotificationIntent.entity_type == "lead",
            CRMNotificationIntent.entity_id == uuid.UUID(lead["id"]),
            CRMNotificationIntent.intent_type == "WORKFLOW_ALERT",
        )
    )
    assert notification is not None
    assert notification.recipient_user_id == notify_user_id

    assert any(entry["action"] == "workflow.executed" for entry in audit.audit_entries)
