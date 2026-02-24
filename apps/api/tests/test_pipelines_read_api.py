from __future__ import annotations

import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMPipelineStage
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
            permissions={"crm.pipelines.read"},
            correlation_id="corr-pipeline-read",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions={"crm.pipelines.read"},
            correlation_id="corr-pipeline-read",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={"crm.pipelines.manage", "crm.pipelines.read", "crm.pipelines.read_all", "crm.opportunities.read"},
            correlation_id="corr-pipeline-read",
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
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> dict[str, str]:
    test_client, set_actor = client
    set_actor("admin")

    global_default = test_client.post(
        "/api/crm/pipelines",
        json={"name": "Global Default", "is_default": True},
    )
    assert global_default.status_code == 201
    global_pipeline_id = global_default.json()["id"]

    global_stage1 = test_client.post(
        f"/api/crm/pipelines/{global_pipeline_id}/stages",
        json={"name": "Global Open", "position": 10, "stage_type": "Open", "is_active": True},
    )
    assert global_stage1.status_code == 201

    le1_default = test_client.post(
        "/api/crm/pipelines",
        json={"name": "LE1 Default", "selling_legal_entity_id": str(legal_entities["le1"]), "is_default": True},
    )
    assert le1_default.status_code == 201
    le1_pipeline_id = le1_default.json()["id"]

    stage_pos20 = test_client.post(
        f"/api/crm/pipelines/{le1_pipeline_id}/stages",
        json={"name": "LE1 Stage 20", "position": 20, "stage_type": "Open", "is_active": True},
    )
    assert stage_pos20.status_code == 201

    stage_pos5 = test_client.post(
        f"/api/crm/pipelines/{le1_pipeline_id}/stages",
        json={"name": "LE1 Stage 5", "position": 5, "stage_type": "Open", "is_active": True},
    )
    assert stage_pos5.status_code == 201

    stage_inactive = test_client.post(
        f"/api/crm/pipelines/{le1_pipeline_id}/stages",
        json={"name": "LE1 Inactive", "position": 30, "stage_type": "Open", "is_active": False},
    )
    assert stage_inactive.status_code == 201

    stage_deleted = test_client.post(
        f"/api/crm/pipelines/{le1_pipeline_id}/stages",
        json={"name": "LE1 Deleted", "position": 40, "stage_type": "Open", "is_active": True},
    )
    assert stage_deleted.status_code == 201

    stage_deleted_id = uuid.UUID(stage_deleted.json()["id"])
    deleted_row = db_session.get(CRMPipelineStage, stage_deleted_id)
    assert deleted_row is not None
    deleted_row.deleted_at = datetime.now(timezone.utc)
    db_session.add(deleted_row)
    db_session.commit()

    le2_pipeline = test_client.post(
        "/api/crm/pipelines",
        json={"name": "LE2 Only", "selling_legal_entity_id": str(legal_entities["le2"]), "is_default": False},
    )
    assert le2_pipeline.status_code == 201

    set_actor("user1")
    return {
        "global_pipeline_id": global_pipeline_id,
        "le1_pipeline_id": le1_pipeline_id,
        "le2_pipeline_id": le2_pipeline.json()["id"],
        "inactive_stage_id": stage_inactive.json()["id"],
        "deleted_stage_id": stage_deleted.json()["id"],
    }


def test_get_default_pipeline_prefers_le_specific(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client

    set_actor("user1")
    le1_response = test_client.get(f"/api/crm/pipelines/default?selling_legal_entity_id={legal_entities['le1']}")
    assert le1_response.status_code == 200
    assert le1_response.json()["id"] == pipeline_setup["le1_pipeline_id"]

    set_actor("user2")
    le2_response = test_client.get(f"/api/crm/pipelines/default?selling_legal_entity_id={legal_entities['le2']}")
    assert le2_response.status_code == 200
    assert le2_response.json()["id"] == pipeline_setup["global_pipeline_id"]


def test_pipeline_visibility_scoped(
    client: tuple[TestClient, Callable[[str], None]],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("user1")

    blocked = test_client.get(f"/api/crm/pipelines/{pipeline_setup['le2_pipeline_id']}")
    assert blocked.status_code == 404


def test_list_stages_orders_by_position(
    client: tuple[TestClient, Callable[[str], None]],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client
    set_actor("user1")

    response = test_client.get(f"/api/crm/pipelines/{pipeline_setup['le1_pipeline_id']}/stages")
    assert response.status_code == 200
    positions = [item["position"] for item in response.json()]
    assert positions == sorted(positions)


def test_include_inactive_requires_manage(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client

    set_actor("user1")
    forbidden = test_client.get(
        f"/api/crm/pipelines/default?selling_legal_entity_id={legal_entities['le1']}&include_inactive=true"
    )
    assert forbidden.status_code == 403

    set_actor("admin")
    allowed = test_client.get(
        f"/api/crm/pipelines/default?selling_legal_entity_id={legal_entities['le1']}&include_inactive=true"
    )
    assert allowed.status_code == 200

    stage_ids = {item["id"] for item in allowed.json()["stages"]}
    assert pipeline_setup["inactive_stage_id"] in stage_ids
    assert pipeline_setup["deleted_stage_id"] in stage_ids


def test_deleted_or_inactive_stages_hidden_by_default(
    client: tuple[TestClient, Callable[[str], None]],
    pipeline_setup: dict[str, str],
) -> None:
    test_client, set_actor = client

    set_actor("user1")
    default_list = test_client.get(f"/api/crm/pipelines/{pipeline_setup['le1_pipeline_id']}/stages")
    assert default_list.status_code == 200
    stage_ids = {item["id"] for item in default_list.json()}
    assert pipeline_setup["inactive_stage_id"] not in stage_ids
    assert pipeline_setup["deleted_stage_id"] not in stage_ids

    set_actor("admin")
    include_inactive = test_client.get(
        f"/api/crm/pipelines/{pipeline_setup['le1_pipeline_id']}/stages?include_inactive=true"
    )
    assert include_inactive.status_code == 200
    all_ids = {item["id"] for item in include_inactive.json()}
    assert pipeline_setup["inactive_stage_id"] in all_ids
    assert pipeline_setup["deleted_stage_id"] in all_ids
