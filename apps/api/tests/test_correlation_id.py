from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user as crm_get_current_user
from app.crm.models import CRMJob
from app.crm.service import ActorUser
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter


ALL_PERMISSIONS = {
    "crm.accounts.read",
    "crm.accounts.write",
    "crm.pipelines.manage",
    "crm.opportunities.create",
    "crm.opportunities.read",
    "crm.opportunities.close_won",
    "crm.opportunities.revenue_handoff",
    "crm.leads.create",
}


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
def clear_stubs() -> Generator[None, None, None]:
    audit.audit_entries.clear()
    events.published_events.clear()
    reset_rate_limiter()
    get_settings.cache_clear()
    yield
    audit.audit_entries.clear()
    events.published_events.clear()
    reset_rate_limiter()
    get_settings.cache_clear()


@pytest.fixture()
def legal_entity_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def client(db_session: Session, legal_entity_id: uuid.UUID) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user(request: Request) -> ActorUser:
        return ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entity_id],
            current_legal_entity_id=legal_entity_id,
            permissions=ALL_PERMISSIONS,
            correlation_id=getattr(request.state, "correlation_id", None),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[crm_get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_account(client: TestClient, legal_entity_id: uuid.UUID, correlation_id: str) -> dict:
    response = client.post(
        "/api/crm/accounts",
        json={"name": "Corr Account", "legal_entity_ids": [str(legal_entity_id)]},
        headers={"X-Correlation-Id": correlation_id},
    )
    assert response.status_code == 201
    return response.json()


def _create_pipeline_with_stages(client: TestClient, legal_entity_id: uuid.UUID) -> None:
    pipeline = client.post(
        "/api/crm/pipelines",
        json={"name": "Default", "selling_legal_entity_id": str(legal_entity_id), "is_default": True},
    )
    assert pipeline.status_code == 201
    pipeline_id = pipeline.json()["id"]

    open_stage = client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Open", "position": 1, "stage_type": "Open"},
    )
    assert open_stage.status_code == 201

    won_stage = client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Won", "position": 90, "stage_type": "ClosedWon"},
    )
    assert won_stage.status_code == 201


def _create_opportunity(client: TestClient, account_id: str, legal_entity_id: uuid.UUID) -> dict:
    response = client.post(
        "/api/crm/opportunities",
        json={
            "account_id": account_id,
            "name": "Corr Opportunity",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 250,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_generated_correlation_id_returned_in_header_and_error_envelope(client: TestClient) -> None:
    response = client.get(f"/api/crm/accounts/{uuid.uuid4()}")
    assert response.status_code == 404
    header_value = response.headers.get("x-correlation-id")
    assert header_value
    body = response.json()
    assert body["correlation_id"] == header_value


def test_correlation_id_respected_when_provided(client: TestClient) -> None:
    response = client.get(f"/api/crm/accounts/{uuid.uuid4()}", headers={"X-Correlation-Id": "abc-123"})
    assert response.status_code == 404
    assert response.headers.get("x-correlation-id") == "abc-123"
    assert response.json()["correlation_id"] == "abc-123"


def test_audit_uses_request_correlation_id(
    client: TestClient,
    legal_entity_id: uuid.UUID,
) -> None:
    _create_account(client, legal_entity_id, "corr-audit-1")

    account_audits = [entry for entry in audit.audit_entries if entry.get("entity_type") == "crm.account"]
    assert account_audits
    assert account_audits[-1]["correlation_id"] == "corr-audit-1"


def test_event_envelope_includes_correlation_id(
    client: TestClient,
    legal_entity_id: uuid.UUID,
) -> None:
    response = client.post(
        "/api/crm/leads",
        json={
            "status": "New",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "company_name": "Corr Lead",
        },
        headers={"X-Correlation-Id": "corr-event-1"},
    )
    assert response.status_code == 201

    created_events = [item for item in events.published_events if item.get("event_type") == "crm.lead.created"]
    assert created_events
    assert created_events[-1].get("correlation_id") == "corr-event-1"


def test_job_runner_uses_job_correlation_id(
    client: TestClient,
    db_session: Session,
    legal_entity_id: uuid.UUID,
) -> None:
    _create_pipeline_with_stages(client, legal_entity_id)
    account = _create_account(client, legal_entity_id, "corr-job-1")
    opportunity = _create_opportunity(client, account["id"], legal_entity_id)

    close_won = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won?sync=true",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"X-Correlation-Id": "corr-job-1", "Idempotency-Key": "corr-job-idem-1"},
    )
    assert close_won.status_code == 200

    job = db_session.scalar(
        select(CRMJob).where(CRMJob.job_type == "REVENUE_HANDOFF").order_by(CRMJob.created_at.desc())
    )
    assert job is not None
    assert job.correlation_id == "corr-job-1"

    job_audits = [entry for entry in audit.audit_entries if entry.get("entity_type") == "crm.job"]
    assert job_audits
    assert any(entry.get("correlation_id") == "corr-job-1" for entry in job_audits)

    handoff_events = [
        item
        for item in events.published_events
        if item.get("event_type") in {"crm.opportunity.revenue_handoff_requested", "crm.opportunity.revenue_handoff_queued"}
    ]
    assert handoff_events
    assert all(item.get("correlation_id") == "corr-job-1" for item in handoff_events)


def test_rate_limited_response_includes_correlation_id(
    client: TestClient,
    legal_entity_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_CRM_MUTATIONS_PER_MINUTE", "1")
    get_settings.cache_clear()
    reset_rate_limiter()

    first = client.post(
        "/api/crm/accounts",
        json={"name": "Rate Limit Account 1", "legal_entity_ids": [str(legal_entity_id)]},
        headers={"X-Correlation-Id": "corr-rate-1"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/crm/accounts",
        json={"name": "Rate Limit Account 2", "legal_entity_ids": [str(legal_entity_id)]},
        headers={"X-Correlation-Id": "corr-rate-1"},
    )
    assert second.status_code == 429
    payload = second.json()
    assert payload["correlation_id"] == "corr-rate-1"
    assert second.headers.get("x-correlation-id") == "corr-rate-1"
