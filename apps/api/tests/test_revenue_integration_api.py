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
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMRevOrder, CRMRevQuote
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
                "crm.opportunities.close_won",
                "crm.opportunities.revenue_handoff",
            },
            correlation_id="corr-revenue",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={
                "crm.opportunities.create",
                "crm.opportunities.read",
                "crm.opportunities.close_won",
                "crm.opportunities.revenue_handoff",
            },
            correlation_id="corr-revenue",
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
                "crm.opportunities.close_won",
                "crm.opportunities.revenue_handoff",
            },
            correlation_id="corr-revenue",
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

    pipeline_le1 = test_client.post(
        "/api/crm/pipelines",
        json={"name": "LE1 Default", "selling_legal_entity_id": str(legal_entities["le1"]), "is_default": True},
    )
    assert pipeline_le1.status_code == 201

    pipeline_le2 = test_client.post(
        "/api/crm/pipelines",
        json={"name": "LE2 Default", "selling_legal_entity_id": str(legal_entities["le2"]), "is_default": True},
    )
    assert pipeline_le2.status_code == 201

    for pipeline in [pipeline_le1.json(), pipeline_le2.json()]:
        open_stage = test_client.post(
            f"/api/crm/pipelines/{pipeline['id']}/stages",
            json={"name": "Open", "position": 1, "stage_type": "Open"},
        )
        assert open_stage.status_code == 201

        won_stage = test_client.post(
            f"/api/crm/pipelines/{pipeline['id']}/stages",
            json={"name": "Won", "position": 90, "stage_type": "ClosedWon"},
        )
        assert won_stage.status_code == 201

    set_actor("user1")
    return {"pipeline_le1": pipeline_le1.json()["id"], "pipeline_le2": pipeline_le2.json()["id"]}


def _create_opportunity(
    client: TestClient,
    account_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    amount: float = 100,
) -> dict:
    payload: dict[str, object] = {
        "account_id": str(account_id),
        "name": "Revenue Opportunity",
        "selling_legal_entity_id": str(legal_entity_id),
        "region_code": "US",
        "currency_code": "USD",
        "amount": amount,
    }
    response = client.post("/api/crm/opportunities", json=payload)
    assert response.status_code == 201
    return response.json()


def _close_won(client: TestClient, opportunity: dict) -> dict:
    response = client.post(
        f"/api/crm/opportunities/{opportunity['id']}/close-won",
        json={"row_version": opportunity["row_version"]},
    )
    assert response.status_code == 200
    return response.json()


def test_handoff_requires_closed_won(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])

    response = test_client.post(
        f"/api/crm/opportunities/{opportunity['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-closedwon-required"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "OPPORTUNITY_NOT_CLOSED_WON"


def test_handoff_creates_quote_and_persists_id(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    won = _close_won(test_client, opportunity)

    handoff = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-create-quote"},
    )
    assert handoff.status_code == 200
    quote_id = handoff.json()["quote"]["id"]

    refreshed = test_client.get(f"/api/crm/opportunities/{won['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["revenue_quote_id"] == quote_id

    quote = db_session.scalar(select(CRMRevQuote).where(CRMRevQuote.id == uuid.UUID(quote_id)))
    assert quote is not None
    assert quote.status == "DRAFT"


def test_handoff_idempotent_same_key(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    won = _close_won(test_client, opportunity)

    first = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-idempotent-1"},
    )
    assert first.status_code == 200

    second = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-idempotent-1"},
    )
    assert second.status_code == 200

    first_quote_id = first.json()["quote"]["id"]
    second_quote_id = second.json()["quote"]["id"]
    assert first_quote_id == second_quote_id

    quote_count = db_session.scalar(select(func.count()).select_from(CRMRevQuote))
    assert int(quote_count or 0) == 1


def test_get_revenue_status_returns_quote(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    won = _close_won(test_client, opportunity)

    handoff = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-status-1"},
    )
    assert handoff.status_code == 200

    status_response = test_client.get(f"/api/crm/opportunities/{won['id']}/revenue")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["quote"] is not None
    assert payload["quote"]["status"] == "DRAFT"
    assert payload["order"] is None


def test_scope_enforced(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    won = _close_won(test_client, opportunity)

    set_actor("user2")

    handoff = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_QUOTE"},
        headers={"Idempotency-Key": "handoff-scope-1"},
    )
    assert handoff.status_code == 404

    status_response = test_client.get(f"/api/crm/opportunities/{won['id']}/revenue")
    assert status_response.status_code == 404


def test_handoff_order_flow(
    client: tuple[TestClient, Callable[[str], None]],
    accounts: dict[str, uuid.UUID],
    legal_entities: dict[str, uuid.UUID],
    db_session: Session,
    pipeline_setup: dict[str, str],
) -> None:
    test_client, _ = client
    opportunity = _create_opportunity(test_client, accounts["a1"], legal_entities["le1"])
    won = _close_won(test_client, opportunity)

    handoff = test_client.post(
        f"/api/crm/opportunities/{won['id']}/revenue/handoff",
        json={"mode": "CREATE_DRAFT_ORDER"},
        headers={"Idempotency-Key": "handoff-order-1"},
    )
    assert handoff.status_code == 200
    order_id = handoff.json()["order"]["id"]
    assert handoff.json()["order"]["status"] == "DRAFT"

    refreshed = test_client.get(f"/api/crm/opportunities/{won['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["revenue_order_id"] == order_id

    order = db_session.scalar(select(CRMRevOrder).where(CRMRevOrder.id == uuid.UUID(order_id)))
    assert order is not None
    assert order.status == "DRAFT"
