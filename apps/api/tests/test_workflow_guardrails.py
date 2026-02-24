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
from app.crm.models import CRMJob, CRMLead
from app.crm.service import ActorUser, WorkflowAutomationService, WorkflowExecutionJobRunner
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
    monkeypatch.setenv("WORKFLOW_MAX_DEPTH", "3")
    monkeypatch.setenv("WORKFLOW_MAX_ACTIONS", "20")
    monkeypatch.setenv("WORKFLOW_MAX_SET_FIELD", "10")
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
            correlation_id="wf-guardrails-admin",
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
        yield test_client, set_actor
    app.dependency_overrides.clear()


def _create_lead_payload(legal_entity_id: uuid.UUID) -> dict[str, object]:
    return {
        "status": "New",
        "source": "Web",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "company_name": "Guardrail Lead",
        "qualification_notes": "init",
    }


def _create_rule(test_client: TestClient, body: dict[str, object]) -> dict[str, object]:
    response = test_client.post("/api/crm/workflows", json=body)
    assert response.status_code == 201
    return response.json()


def _enqueue_rule_event(
    db_session: Session,
    *,
    lead_id: str,
    legal_entity_id: uuid.UUID,
    event_id: str | None = None,
    depth: int = 0,
) -> list[uuid.UUID]:
    automation = WorkflowAutomationService()
    envelope = {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "crm.lead.updated",
        "occurred_at": "2026-02-24T00:00:00Z",
        "actor_user_id": "admin-1",
        "legal_entity_id": str(legal_entity_id),
        "payload": {"lead_id": lead_id},
        "version": 1,
        "correlation_id": "wf-guardrails-corr",
        "meta": {"workflow_depth": depth},
    }
    return automation.enqueue_for_event(db_session, envelope)


def test_guardrail_max_depth_blocks_enqueue(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client

    _create_rule(
        test_client,
        {
            "name": "Depth blocked rule",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "depth"}],
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead_id = lead_response.json()["id"]

    queued = _enqueue_rule_event(
        db_session,
        lead_id=lead_id,
        legal_entity_id=legal_entities["le1"],
        depth=get_settings().workflow_max_depth,
    )

    assert queued == []
    jobs = db_session.scalars(select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")).all()
    assert jobs == []
    assert any(
        entry["action"] == "workflow.blocked" and (entry.get("after") or {}).get("reason") == "MAX_DEPTH"
        for entry in audit.audit_entries
    )


def test_guardrail_cooldown_throttles_second_run(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client

    _create_rule(
        test_client,
        {
            "name": "Cooldown rule",
            "trigger_event": "crm.lead.updated",
            "cooldown_seconds": 60,
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "first-run"}],
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    runner = WorkflowExecutionJobRunner()

    first_ids = _enqueue_rule_event(db_session, lead_id=lead["id"], legal_entity_id=legal_entities["le1"], event_id=str(uuid.uuid4()))
    assert len(first_ids) == 1
    first_job = runner.run_workflow_execution_job(db_session, first_ids[0])
    assert first_job.status == "Succeeded"

    second_ids = _enqueue_rule_event(db_session, lead_id=lead["id"], legal_entity_id=legal_entities["le1"], event_id=str(uuid.uuid4()))
    assert len(second_ids) == 1
    second_job = runner.run_workflow_execution_job(db_session, second_ids[0])
    assert second_job.status == "Succeeded"

    second_result = json.loads(second_job.result_json or "{}")
    assert second_result.get("throttled") is True

    refreshed = test_client.get(f"/api/crm/leads/{lead['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["qualification_notes"] == "first-run"


def test_guardrail_max_action_limit_fails_job(
    monkeypatch: pytest.MonkeyPatch,
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    monkeypatch.setenv("WORKFLOW_MAX_ACTIONS", "20")
    monkeypatch.setenv("WORKFLOW_MAX_SET_FIELD", "100")
    get_settings.cache_clear()

    test_client, _ = client

    actions = [{"type": "SET_FIELD", "path": "qualification_notes", "value": f"a-{index}"} for index in range(1, 26)]
    _create_rule(
        test_client,
        {
            "name": "Max actions rule",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": actions,
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    queued = _enqueue_rule_event(db_session, lead_id=lead["id"], legal_entity_id=legal_entities["le1"], event_id=str(uuid.uuid4()))
    assert len(queued) == 1

    runner = WorkflowExecutionJobRunner()
    failed_job = runner.run_workflow_execution_job(db_session, queued[0])
    assert failed_job.status == "Failed"

    result = json.loads(failed_job.result_json or "{}")
    assert result.get("code") == "WORKFLOW_LIMIT_EXCEEDED"
    assert result.get("reason") == "MAX_ACTIONS"
    assert result.get("actions_executed_count") == 20

    refreshed = test_client.get(f"/api/crm/leads/{lead['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["qualification_notes"] == "a-20"


def test_guardrail_max_set_field_limit_fails_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    monkeypatch.setenv("WORKFLOW_MAX_ACTIONS", "50")
    monkeypatch.setenv("WORKFLOW_MAX_SET_FIELD", "10")
    get_settings.cache_clear()

    test_client, _ = client

    actions = [{"type": "SET_FIELD", "path": "qualification_notes", "value": f"s-{index}"} for index in range(1, 16)]
    _create_rule(
        test_client,
        {
            "name": "Max set_field rule",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": actions,
        },
    )

    lead_response = test_client.post("/api/crm/leads", json=_create_lead_payload(legal_entities["le1"]))
    assert lead_response.status_code == 201
    lead = lead_response.json()

    queued = _enqueue_rule_event(db_session, lead_id=lead["id"], legal_entity_id=legal_entities["le1"], event_id=str(uuid.uuid4()))
    assert len(queued) == 1

    runner = WorkflowExecutionJobRunner()
    failed_job = runner.run_workflow_execution_job(db_session, queued[0])
    assert failed_job.status == "Failed"

    result = json.loads(failed_job.result_json or "{}")
    assert result.get("code") == "WORKFLOW_LIMIT_EXCEEDED"
    assert result.get("reason") == "MAX_SET_FIELD"
    assert result.get("set_field_executed_count") == 10

    refreshed = test_client.get(f"/api/crm/leads/{lead['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["qualification_notes"] == "s-10"
