from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import AuthUser, get_current_user as auth_get_current_user
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user as crm_get_current_user
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
def configure_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("METRICS_ENABLED", "true")
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
def client(db_session: Session, legal_entity_id: uuid.UUID) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_crm_user() -> ActorUser:
        return ActorUser(
            user_id="metrics-user",
            allowed_legal_entity_ids=[legal_entity_id],
            current_legal_entity_id=legal_entity_id,
            permissions={
                "crm.accounts.read",
                "crm.accounts.write",
                "crm.pipelines.manage",
                "crm.opportunities.create",
                "crm.opportunities.read",
                "crm.opportunities.close_won",
            },
            correlation_id="metrics-corr-1",
        )

    def override_auth_user() -> AuthUser:
        return AuthUser(sub="metrics-admin", roles=["system.metrics.read"])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[crm_get_current_user] = override_crm_user
    app.dependency_overrides[auth_get_current_user] = override_auth_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _create_pipeline_with_stages(client: TestClient, legal_entity_id: uuid.UUID) -> None:
    pipeline = client.post(
        "/api/crm/pipelines",
        json={"name": "Metrics Pipeline", "selling_legal_entity_id": str(legal_entity_id), "is_default": True},
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


def test_metrics_endpoint_exposes_http_and_job_metrics(client: TestClient, legal_entity_id: uuid.UUID) -> None:
    health = client.get("/health")
    assert health.status_code == 200

    account = client.post(
        "/api/crm/accounts",
        json={"name": "Metrics Account", "legal_entity_ids": [str(legal_entity_id)]},
    )
    assert account.status_code == 201

    _create_pipeline_with_stages(client, legal_entity_id)

    opportunity = client.post(
        "/api/crm/opportunities",
        json={
            "account_id": account.json()["id"],
            "name": "Metrics Opportunity",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 100,
        },
    )
    assert opportunity.status_code == 201

    close_won = client.post(
        f"/api/crm/opportunities/{opportunity.json()['id']}/close-won?sync=true",
        json={"row_version": opportunity.json()["row_version"], "revenue_handoff": {"requested": True}},
    )
    assert close_won.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text

    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "crm_jobs_total" in body
    assert "crm_job_duration_seconds" in body

    assert 'path="/health"' in body
    assert 'path="/api/crm/opportunities/{opportunity_id}/close-won"' in body
    assert 'job_type="REVENUE_HANDOFF"' in body
