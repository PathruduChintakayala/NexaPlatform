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
    a1 = CRMAccount(name="Account LE1", status="Active")
    a2 = CRMAccount(name="Account LE2", status="Active")
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

    actors = {
        "user1": ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions={
                "crm.opportunities.create",
                "crm.opportunities.read",
                "crm.opportunities.update",
                "crm.opportunities.change_stage",
                "crm.opportunities.close_won",
                "crm.opportunities.close_lost",
            },
            correlation_id="corr-opp",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={
                "crm.opportunities.create",
                "crm.opportunities.read",
                "crm.opportunities.update",
                "crm.opportunities.change_stage",
                "crm.opportunities.close_won",
                "crm.opportunities.close_lost",
            },
            correlation_id="corr-opp",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={
                "crm.pipelines.manage",
                "crm.opportunities.create",
                "crm.opportunities.create_all",
                "crm.opportunities.read",
                "crm.opportunities.read_all",
                "crm.opportunities.update",
                "crm.opportunities.update_all",
                "crm.opportunities.change_stage",
                "crm.opportunities.close_won",
                "crm.opportunities.close_lost",
                "crm.opportunities.reopen",
                "crm.opportunities.edit_closed",
            },
            correlation_id="corr-opp",
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


@pytest.fixture()
def pipeline_setup(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> dict[str, str]:
    test_client, set_actor = client
    set_actor("admin")

    pipeline = test_client.post(
        "/api/crm/pipelines",
        json={"name": "LE1 Default", "selling_legal_entity_id": str(legal_entities["le1"]), "is_default": True},
    )
    assert pipeline.status_code == 201
    pipeline_id = pipeline.json()["id"]

    stage1 = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={
            "name": "Discovery",
            "position": 1,
            "stage_type": "Open",
            "requires_amount": False,
            "requires_expected_close_date": False,
        },
    )
    assert stage1.status_code == 201

    stage2 = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={
            "name": "Proposal",
            "position": 2,
            "stage_type": "Open",
            "requires_amount": True,
            "requires_expected_close_date": True,
        },
    )
    assert stage2.status_code == 201

    stage_won = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Won", "position": 90, "stage_type": "ClosedWon"},
    )
    assert stage_won.status_code == 201

    stage_lost = test_client.post(
        f"/api/crm/pipelines/{pipeline_id}/stages",
        json={"name": "Lost", "position": 91, "stage_type": "ClosedLost"},
    )
    assert stage_lost.status_code == 201

    set_actor("user1")
    return {
        "pipeline_id": pipeline_id,
        "stage1": stage1.json()["id"],
        "stage2": stage2.json()["id"],
        "won": stage_won.json()["id"],
        "lost": stage_lost.json()["id"],
    }


def _create_opportunity(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    amount: float = 0,
    expected_close_date: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "account_id": str(account_id),
        "name": "Opportunity A",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "currency_code": "USD",
        "amount": amount,
    }
    if expected_close_date:
        payload["expected_close_date"] = expected_close_date
    response = client.post("/api/crm/opportunities", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_opportunity_uses_default_open_stage_and_scopes(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    created = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    assert created["stage_id"] == pipeline_setup["stage1"]

    listed_user1 = test_client.get("/api/crm/opportunities")
    assert listed_user1.status_code == 200
    assert any(row["id"] == created["id"] for row in listed_user1.json())

    set_actor("user2")
    listed_user2 = test_client.get("/api/crm/opportunities")
    assert listed_user2.status_code == 200
    assert all(row["id"] != created["id"] for row in listed_user2.json())


def test_create_opportunity_auto_associates_account_to_selling_legal_entity(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("admin")
    created = _create_opportunity(test_client, accounts["a2"], legal_entities["le1"])
    assert created["selling_legal_entity_id"] == str(legal_entities["le1"])

    mapping = db_session.scalar(
        db_session.query(CRMAccountLegalEntity)
        .filter(
            CRMAccountLegalEntity.account_id == accounts["a2"],
            CRMAccountLegalEntity.legal_entity_id == legal_entities["le1"],
        )
        .statement
    )
    assert mapping is not None


def test_change_stage_enforces_requires_amount_and_date(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    created = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"], amount=0)

    fail_change = test_client.post(
        f"/api/crm/opportunities/{created['id']}/change-stage",
        json={"stage_id": pipeline_setup["stage2"], "row_version": created["row_version"]},
    )
    assert fail_change.status_code == 422

    patched = test_client.patch(
        f"/api/crm/opportunities/{created['id']}",
        json={"row_version": created["row_version"], "amount": 1000, "expected_close_date": "2026-12-31"},
    )
    assert patched.status_code == 200

    ok_change = test_client.post(
        f"/api/crm/opportunities/{created['id']}/change-stage",
        json={"stage_id": pipeline_setup["stage2"], "row_version": patched.json()["row_version"]},
    )
    assert ok_change.status_code == 200
    assert ok_change.json()["stage_id"] == pipeline_setup["stage2"]


def test_close_won_sets_terminal_fields_and_emits_event_idempotent(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    created = _create_opportunity(
        test_client,
        accounts["a1"],
        legal_entities["le1"],
        amount=5000,
        expected_close_date="2026-11-01",
    )
    events.published_events.clear()

    first = test_client.post(
        f"/api/crm/opportunities/{created['id']}/close-won",
        json={"row_version": created["row_version"], "revenue_handoff_requested": True},
        headers={"Idempotency-Key": "won-key-1"},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["closed_won_at"] is not None

    second = test_client.post(
        f"/api/crm/opportunities/{created['id']}/close-won",
        json={"row_version": created["row_version"], "revenue_handoff_requested": True},
        headers={"Idempotency-Key": "won-key-1"},
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_body["id"]
    assert second.json()["closed_won_at"].replace("Z", "") == first_body["closed_won_at"].replace("Z", "")

    won_events = [event for event in events.published_events if event["event_type"] == "crm.opportunity.closed_won"]
    assert len(won_events) == 1


def test_close_lost_requires_close_reason(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    created = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"], amount=100)
    missing_reason = test_client.post(
        f"/api/crm/opportunities/{created['id']}/close-lost",
        json={"row_version": created["row_version"], "close_reason": ""},
    )
    assert missing_reason.status_code == 422


def test_closed_opportunity_blocks_amount_edit_without_permission(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    created = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"], amount=250)

    won = test_client.post(
        f"/api/crm/opportunities/{created['id']}/close-won",
        json={"row_version": created["row_version"]},
    )
    assert won.status_code == 200

    blocked = test_client.patch(
        f"/api/crm/opportunities/{created['id']}",
        json={"row_version": won.json()["row_version"], "amount": 500},
    )
    assert blocked.status_code == 422

    set_actor("admin")
    allowed = test_client.patch(
        f"/api/crm/opportunities/{created['id']}",
        json={"row_version": won.json()["row_version"], "amount": 500},
    )
    assert allowed.status_code == 200


def test_reopen_requires_permission_and_resets_closed_fields(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    created = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"], amount=300)
    won = test_client.post(
        f"/api/crm/opportunities/{created['id']}/close-won",
        json={"row_version": created["row_version"]},
    )
    assert won.status_code == 200

    denied = test_client.post(
        f"/api/crm/opportunities/{created['id']}/reopen",
        json={"row_version": won.json()["row_version"]},
    )
    assert denied.status_code == 403

    set_actor("admin")
    reopened = test_client.post(
        f"/api/crm/opportunities/{created['id']}/reopen",
        json={"row_version": won.json()["row_version"], "new_stage_id": pipeline_setup["stage1"]},
    )
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["closed_won_at"] is None
    assert body["closed_lost_at"] is None
    assert body["stage_id"] == pipeline_setup["stage1"]
