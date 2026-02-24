from __future__ import annotations

import json
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
from app.crm.models import CRMActivity, CRMJob, CRMLead
from app.crm.service import ActorUser, WorkflowExecutionJobRunner
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
    monkeypatch.setenv("AUTO_RUN_WORKFLOW_JOBS", "false")
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
    assignee_id = uuid.uuid4()
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
                "crm.jobs.read",
                "crm.jobs.read_all",
            },
            correlation_id="wf-auto-admin",
        ),
        "le1_user": ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={"crm.leads.create", "crm.leads.read", "crm.workflows.read", "crm.workflows.execute"},
            correlation_id="wf-auto-user1",
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
        test_client.app_state = {"assignee_id": assignee_id}
        yield test_client, set_actor
    app.dependency_overrides.clear()


def _create_lead_payload(legal_entity_id: uuid.UUID) -> dict[str, object]:
    return {
        "status": "New",
        "source": "Web",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "company_name": "Auto Workflow",
    }


def _create_rule(test_client: TestClient, body: dict[str, object]) -> dict[str, object]:
    response = test_client.post("/api/crm/workflows", json=body)
    assert response.status_code == 201
    return response.json()


def test_auto_exec_enqueues_job_on_event(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    _create_rule(
        test_client,
        {
            "name": "Auto qualify",
            "trigger_event": "crm.lead.created",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "queued"}],
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    jobs = db_session.scalars(select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")).all()
    assert len(jobs) == 1
    params = json.loads(jobs[0].params_json)
    assert params["entity_type"] == "lead"
    assert params["entity_id"] == lead["id"]
    assert params["event_type"] == "crm.lead.created"
    assert jobs[0].correlation_id is not None


def test_job_runner_executes_rule_and_mutates_entity(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    assignee_id = test_client.app_state["assignee_id"]
    set_actor("admin")

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    rule = _create_rule(
        test_client,
        {
            "name": "Execute actions",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [
                {"type": "SET_FIELD", "path": "qualification_notes", "value": "applied"},
                {
                    "type": "CREATE_TASK",
                    "title": "Follow up",
                    "due_in_days": 3,
                    "assigned_to_user_id": str(assignee_id),
                    "entity_ref": {"type": "lead", "id": lead["id"]},
                },
            ],
        },
    )

    events.publish(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "crm.lead.updated",
            "occurred_at": "2026-02-24T00:00:00Z",
            "actor_user_id": "admin-1",
            "legal_entity_id": str(legal_entities["le1"]),
            "payload": {"lead_id": lead["id"]},
            "version": 1,
            "correlation_id": "wf-auto-runner-1",
        }
    )

    job = db_session.scalar(
        select(CRMJob)
        .where(CRMJob.job_type == "WORKFLOW_EXECUTION")
        .order_by(CRMJob.created_at.desc())
    )
    assert job is not None

    runner = WorkflowExecutionJobRunner()
    completed = runner.run_workflow_execution_job(db_session, job.id)
    assert completed.status == "Succeeded"

    refreshed = test_client.get(f"/api/crm/leads/{lead['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["qualification_notes"] == "applied"

    task = db_session.scalar(
        select(CRMActivity).where(
            CRMActivity.entity_type == "lead",
            CRMActivity.entity_id == uuid.UUID(lead["id"]),
            CRMActivity.activity_type == "Task",
            CRMActivity.subject == "Follow up",
        )
    )
    assert task is not None
    assert task.assigned_to_user_id == assignee_id

    result = json.loads(completed.result_json or "{}")
    assert result.get("matched") is True
    assert result.get("actions_executed_count") == 2
    assert result.get("rule_id") == rule["id"]


def test_dedupe_by_event_id_and_rule_id(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    rule = _create_rule(
        test_client,
        {
            "name": "Dedupe",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "first-only"}],
        },
    )

    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "crm.lead.updated",
        "occurred_at": "2026-02-24T00:00:00Z",
        "actor_user_id": "admin-1",
        "legal_entity_id": str(legal_entities["le1"]),
        "payload": {"lead_id": lead["id"]},
        "version": 1,
        "correlation_id": "wf-auto-dedupe",
    }
    events.publish(envelope)
    events.publish(envelope)

    jobs = db_session.scalars(select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")).all()
    rule_jobs = [job for job in jobs if json.loads(job.params_json).get("rule_id") == rule["id"]]
    assert len(rule_jobs) == 1

    runner = WorkflowExecutionJobRunner()
    runner.run_workflow_execution_job(db_session, rule_jobs[0].id)
    rerun = runner.run_workflow_execution_job(db_session, rule_jobs[0].id)
    assert rerun.status == "Succeeded"


def test_scope_rule_only_matches_same_legal_entity(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    _create_rule(
        test_client,
        {
            "name": "LE2 scoped",
            "trigger_event": "crm.lead.created",
            "legal_entity_id": str(legal_entities["le2"]),
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "le2"}],
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201

    jobs = db_session.scalars(select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")).all()
    assert jobs == []


def test_inactive_rule_not_executed(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, set_actor = client
    set_actor("admin")

    _create_rule(
        test_client,
        {
            "name": "Inactive",
            "trigger_event": "crm.lead.created",
            "is_active": False,
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "inactive"}],
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201

    jobs = db_session.scalars(select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")).all()
    assert jobs == []
