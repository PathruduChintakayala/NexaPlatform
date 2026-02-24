from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
def configure_rate_limiter_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_CRM_MUTATIONS_PER_MINUTE", "3")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield
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
            permissions={"crm.accounts.read", "crm.accounts.write"},
            correlation_id=getattr(request.state, "correlation_id", None),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[crm_get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_mutating_crm_endpoints_are_rate_limited(client: TestClient, legal_entity_id: uuid.UUID) -> None:
    responses = []
    for index in range(5):
        response = client.post(
            "/api/crm/accounts",
            json={
                "name": f"Rate Limit Account {index}",
                "legal_entity_ids": [str(legal_entity_id)],
            },
        )
        responses.append(response)

    limited = [response for response in responses if response.status_code == 429]
    assert limited

    first_limited = limited[0]
    body = first_limited.json()
    assert body["code"] == "RATE_LIMITED"
    assert body["message"] == "Too many requests"
    assert body["correlation_id"] is not None
    assert first_limited.headers.get("Retry-After") is not None


def test_get_endpoints_are_not_rate_limited(client: TestClient, legal_entity_id: uuid.UUID) -> None:
    create = client.post(
        "/api/crm/accounts",
        json={
            "name": "Readable Account",
            "legal_entity_ids": [str(legal_entity_id)],
        },
    )
    assert create.status_code == 201

    responses = [client.get("/api/crm/accounts") for _ in range(10)]
    assert all(response.status_code != 429 for response in responses)
