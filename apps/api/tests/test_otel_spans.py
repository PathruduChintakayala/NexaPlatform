from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("OTEL_ENABLED", "true")

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user as crm_get_current_user
from app.crm.models import CRMJob
from app.crm.service import ActorUser
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter
from app.otel import setup_inmemory_otel


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
def setup_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "true")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield
    get_settings.cache_clear()
    reset_rate_limiter()


@pytest.fixture()
def legal_entity_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def span_exporter() -> InMemorySpanExporter:
    exporter = setup_inmemory_otel("api")
    exporter.clear()
    return exporter


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


def _create_account(client: TestClient, legal_entity_id: uuid.UUID, correlation_id: str) -> dict:
    response = client.post(
        "/api/crm/accounts",
        json={"name": "OTel Account", "legal_entity_ids": [str(legal_entity_id)]},
        headers={"X-Correlation-Id": correlation_id},
    )
    assert response.status_code == 201
    return response.json()


def _create_opportunity(client: TestClient, account_id: str, legal_entity_id: uuid.UUID) -> dict:
    response = client.post(
        "/api/crm/opportunities",
        json={
            "account_id": account_id,
            "name": "OTel Opportunity",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 300,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_request_span_contains_correlation_id(client: TestClient, span_exporter: InMemorySpanExporter, legal_entity_id: uuid.UUID) -> None:
    response = client.post(
        "/api/crm/leads",
        json={
            "status": "New",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
        },
        headers={"X-Correlation-Id": "otel-corr-1"},
    )
    assert response.status_code == 201

    spans = span_exporter.get_finished_spans()
    assert spans
    assert any(span.attributes.get("correlation_id") == "otel-corr-1" for span in spans)


def test_job_span_contains_job_id_and_correlation(
    client: TestClient,
    db_session: Session,
    span_exporter: InMemorySpanExporter,
    legal_entity_id: uuid.UUID,
) -> None:
    _create_pipeline_with_stages(client, legal_entity_id)
    account = _create_account(client, legal_entity_id, "otel-job-corr-1")
    opportunity = _create_opportunity(client, account["id"], legal_entity_id)

    close_won = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won?sync=true",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"X-Correlation-Id": "otel-job-corr-1", "Idempotency-Key": "otel-job-idem-1"},
    )
    assert close_won.status_code == 200

    job = db_session.scalar(
        select(CRMJob).where(CRMJob.job_type == "REVENUE_HANDOFF").order_by(CRMJob.created_at.desc())
    )
    assert job is not None

    spans = span_exporter.get_finished_spans()
    job_spans = [span for span in spans if span.name == "crm.job.run"]
    assert job_spans
    assert any(
        span.attributes.get("job_id") == str(job.id)
        and span.attributes.get("job_type") == "REVENUE_HANDOFF"
        and span.attributes.get("correlation_id") == "otel-job-corr-1"
        for span in job_spans
    )
