from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMJob, CRMOpportunity, CRMRevQuote
from app.crm.service import ActorUser, RevenueHandoffJobRunner
from app.main import app
from app.revenue.client import StubRevenueClient


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
    return {"le1": uuid.uuid4()}


@pytest.fixture()
def account_id(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> uuid.UUID:
    account = CRMAccount(name="Account LE1", status="Active")
    db_session.add(account)
    db_session.flush()
    db_session.add(CRMAccountLegalEntity(account_id=account.id, legal_entity_id=legal_entities["le1"], is_default=True))
    db_session.commit()
    return account.id


@pytest.fixture()
def actor_user(legal_entities: dict[str, uuid.UUID]) -> ActorUser:
    return ActorUser(
        user_id="user-1",
        allowed_legal_entity_ids=[legal_entities["le1"]],
        current_legal_entity_id=legal_entities["le1"],
        permissions={
            "crm.pipelines.manage",
            "crm.opportunities.create",
            "crm.opportunities.read",
            "crm.opportunities.close_won",
            "crm.opportunities.revenue_handoff",
        },
        correlation_id="corr-revenue-jobs",
    )


@pytest.fixture()
def client(
    db_session: Session,
    actor_user: ActorUser,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user() -> ActorUser:
        return actor_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def pipeline_setup(client: TestClient, legal_entities: dict[str, uuid.UUID]) -> dict[str, str]:
    pipeline = client.post(
        "/api/crm/pipelines",
        json={"name": "LE1 Default", "selling_legal_entity_id": str(legal_entities["le1"]), "is_default": True},
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

    return {"pipeline_id": pipeline_id}


def _create_opportunity(client: TestClient, account_id: uuid.UUID, legal_entity_id: uuid.UUID) -> dict:
    response = client.post(
        "/api/crm/opportunities",
        json={
            "account_id": str(account_id),
            "name": "Revenue Jobs Opportunity",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "currency_code": "USD",
            "amount": 125,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_close_won_sync_runs_handoff_success(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    opportunity = _create_opportunity(client, account_id, legal_entities["le1"])

    response = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won?sync=true",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"Idempotency-Key": "job-close-won-sync-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["revenue_handoff_status"] == "Succeeded"
    assert payload["revenue_handoff_last_error"] is None
    assert payload["revenue_quote_id"] is not None

    jobs_count = db_session.scalar(
        select(func.count()).select_from(CRMJob).where(CRMJob.job_type == "REVENUE_HANDOFF")
    )
    assert int(jobs_count or 0) == 1


def test_close_won_without_sync_queues_job(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    opportunity = _create_opportunity(client, account_id, legal_entities["le1"])

    response = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"Idempotency-Key": "job-close-won-queued-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["revenue_handoff_status"] == "Queued"
    assert payload["revenue_quote_id"] is None

    job = db_session.scalar(select(CRMJob).where(CRMJob.job_type == "REVENUE_HANDOFF").order_by(CRMJob.created_at.desc()))
    assert job is not None
    assert job.status == "Queued"


def test_retry_requires_failed_state(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    opportunity = _create_opportunity(client, account_id, legal_entities["le1"])

    close_won = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"Idempotency-Key": "job-retry-not-failed-1"},
    )
    assert close_won.status_code == 200

    retry_response = client.post(f"/api/crm/opportunities/{opportunity['id']}/revenue/retry")
    assert retry_response.status_code == 422
    assert retry_response.json()["code"] == "REVENUE_HANDOFF_NOT_FAILED"


def test_failed_then_retry_sync_clears_error(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_quote(self: StubRevenueClient, opportunity_id: uuid.UUID, idempotency_key: str) -> uuid.UUID:
        raise RuntimeError("simulated revenue outage")

    monkeypatch.setattr(StubRevenueClient, "create_draft_quote", fail_quote)

    opportunity = _create_opportunity(client, account_id, legal_entities["le1"])
    failed_close = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won?sync=true",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"Idempotency-Key": "job-fail-then-retry-1"},
    )
    assert failed_close.status_code == 200
    assert failed_close.json()["revenue_handoff_status"] == "Failed"
    assert failed_close.json()["revenue_handoff_last_error"] is not None

    monkeypatch.undo()

    retry = client.post(f"/api/crm/opportunities/{opportunity['id']}/revenue/retry?sync=true")
    assert retry.status_code == 200
    assert retry.json()["status"] == "Succeeded"

    refreshed = client.get(f"/api/crm/opportunities/{opportunity['id']}")
    assert refreshed.status_code == 200
    payload = refreshed.json()
    assert payload["revenue_handoff_status"] == "Succeeded"
    assert payload["revenue_handoff_last_error"] is None
    assert payload["revenue_quote_id"] is not None

    failed_jobs = db_session.scalar(select(func.count()).select_from(CRMJob).where(CRMJob.status == "Failed"))
    succeeded_jobs = db_session.scalar(select(func.count()).select_from(CRMJob).where(CRMJob.status == "Succeeded"))
    assert int(failed_jobs or 0) >= 1
    assert int(succeeded_jobs or 0) >= 1


def test_same_job_repeat_is_safe_no_duplicate_quotes(
    db_session: Session,
    actor_user: ActorUser,
    client: TestClient,
    account_id: uuid.UUID,
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    opportunity = _create_opportunity(client, account_id, legal_entities["le1"])

    close_won = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won",
        json={
            "row_version": opportunity["row_version"],
            "revenue_handoff": {"requested": True, "mode": "CREATE_DRAFT_QUOTE"},
        },
        headers={"Idempotency-Key": "job-repeat-safe-1"},
    )
    assert close_won.status_code == 200

    job = db_session.scalar(
        select(CRMJob)
        .where(CRMJob.job_type == "REVENUE_HANDOFF")
        .order_by(CRMJob.created_at.desc())
    )
    assert job is not None

    runner = RevenueHandoffJobRunner()
    first = runner.run_revenue_handoff_job(db_session, actor_user, job.id)
    second = runner.run_revenue_handoff_job(db_session, actor_user, job.id)

    assert first.status == "Succeeded"
    assert second.status == "Succeeded"

    quote_count = db_session.scalar(select(func.count()).select_from(CRMRevQuote))
    assert int(quote_count or 0) == 1

    refreshed_opp = db_session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == uuid.UUID(opportunity["id"])))
    assert refreshed_opp is not None
    assert refreshed_opp.revenue_handoff_status == "Succeeded"
