from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import audit, events
from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import (
    CRMAccount,
    CRMAccountLegalEntity,
    CRMContact,
    CRMLead,
    CRMNotificationIntent,
    CRMOpportunity,
    CRMPipeline,
    CRMPipelineStage,
)
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
def data_setup(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    account = CRMAccount(name="A1", status="Active")
    account2 = CRMAccount(name="A2", status="Active")
    db_session.add_all([account, account2])
    db_session.flush()
    db_session.add_all(
        [
            CRMAccountLegalEntity(account_id=account.id, legal_entity_id=legal_entities["le1"], is_default=True),
            CRMAccountLegalEntity(account_id=account2.id, legal_entity_id=legal_entities["le2"], is_default=True),
        ]
    )

    contact = CRMContact(account_id=account.id, first_name="Ana", last_name="Lee", is_primary=True)
    lead = CRMLead(
        status="Qualified",
        source="Web",
        selling_legal_entity_id=legal_entities["le1"],
        region_code="US",
        company_name="Lead Co",
    )
    pipeline = CRMPipeline(name="Default", selling_legal_entity_id=legal_entities["le1"], is_default=True)
    db_session.add_all([contact, lead, pipeline])
    db_session.flush()
    stage = CRMPipelineStage(pipeline_id=pipeline.id, name="Open", position=1, stage_type="Open", is_active=True)
    db_session.add(stage)
    db_session.flush()
    opportunity = CRMOpportunity(
        account_id=account.id,
        name="Opp",
        stage_id=stage.id,
        selling_legal_entity_id=legal_entities["le1"],
        region_code="US",
        currency_code="USD",
        amount=100,
    )
    db_session.add(opportunity)
    db_session.commit()

    return {
        "account": account.id,
        "account2": account2.id,
        "contact": contact.id,
        "lead": lead.id,
        "opportunity": opportunity.id,
    }


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
                "crm.activities.read",
                "crm.activities.create",
                "crm.activities.update",
                "crm.activities.complete",
                "crm.notes.read",
                "crm.notes.create",
                "crm.notes.update",
                "crm.attachments.read",
                "crm.attachments.create",
            },
            correlation_id="corr-activity",
        ),
    }
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: actors["user1"]
    with TestClient(app) as test_client:
        yield test_client, (lambda _name: None)
    app.dependency_overrides.clear()


def test_create_list_activity_for_account(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    create = test_client.post(
        f"/api/crm/entities/account/{data_setup['account']}/activities",
        json={"activity_type": "Call", "subject": "Intro Call"},
    )
    assert create.status_code == 201

    listed = test_client.get(f"/api/crm/entities/account/{data_setup['account']}/activities")
    assert listed.status_code == 200
    assert any(item["subject"] == "Intro Call" for item in listed.json())


def test_create_task_requires_assignee_and_due_date(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    fail = test_client.post(
        f"/api/crm/entities/account/{data_setup['account']}/activities",
        json={"activity_type": "Task", "subject": "Do thing"},
    )
    assert fail.status_code == 422

    success = test_client.post(
        f"/api/crm/entities/account/{data_setup['account']}/activities",
        json={
            "activity_type": "Task",
            "subject": "Do thing",
            "assigned_to_user_id": str(uuid.uuid4()),
            "due_at": "2026-12-31T10:00:00Z",
        },
    )
    assert success.status_code == 201


def test_complete_task_sets_completed_fields_and_emits_event(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    audit.audit_entries.clear()
    events.published_events.clear()
    created = test_client.post(
        f"/api/crm/entities/account/{data_setup['account']}/activities",
        json={
            "activity_type": "Task",
            "subject": "Complete me",
            "assigned_to_user_id": str(uuid.uuid4()),
            "due_at": "2026-10-10T10:00:00Z",
        },
    )
    assert created.status_code == 201

    completed = test_client.post(
        f"/api/crm/activities/{created.json()['id']}/complete",
        json={"row_version": created.json()["row_version"]},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "Completed"
    assert body["completed_at"] is not None
    assert any(event["event_type"] == "crm.activity.completed" for event in events.published_events)


def test_activity_scoping_blocks_other_entity(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    create = test_client.post(
        f"/api/crm/entities/account/{data_setup['account2']}/activities",
        json={"activity_type": "Call", "subject": "Blocked"},
    )
    assert create.status_code == 404

    listed = test_client.get(f"/api/crm/entities/account/{data_setup['account2']}/activities")
    assert listed.status_code == 404


def test_create_and_update_note_with_row_version(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    created = test_client.post(
        f"/api/crm/entities/lead/{data_setup['lead']}/notes",
        json={"content": "Initial note", "content_format": "markdown"},
    )
    assert created.status_code == 201
    note = created.json()

    updated = test_client.patch(
        f"/api/crm/notes/{note['id']}",
        json={"row_version": note["row_version"], "content": "Updated note"},
    )
    assert updated.status_code == 200

    stale = test_client.patch(
        f"/api/crm/notes/{note['id']}",
        json={"row_version": note["row_version"], "content": "Stale"},
    )
    assert stale.status_code == 409


def test_attachment_link_create_and_list(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    file_id = uuid.uuid4()
    created = test_client.post(
        f"/api/crm/entities/opportunity/{data_setup['opportunity']}/attachments",
        json={"file_id": str(file_id)},
    )
    assert created.status_code == 201

    listed = test_client.get(f"/api/crm/entities/opportunity/{data_setup['opportunity']}/attachments")
    assert listed.status_code == 200
    assert any(item["file_id"] == str(file_id) for item in listed.json())


def test_task_assignment_creates_notification_intent(
    client: tuple[TestClient, Callable[[str], None]],
    data_setup: dict[str, uuid.UUID],
    db_session: Session,
) -> None:
    test_client, _ = client
    assignee = uuid.uuid4()
    created = test_client.post(
        f"/api/crm/entities/account/{data_setup['account']}/activities",
        json={
            "activity_type": "Task",
            "subject": "Assigned Task",
            "assigned_to_user_id": str(assignee),
            "due_at": "2026-10-10T10:00:00Z",
        },
    )
    assert created.status_code == 201

    intent = db_session.scalar(
        db_session.query(CRMNotificationIntent)
        .filter(CRMNotificationIntent.activity_id == uuid.UUID(created.json()["id"]))
        .statement
    )
    assert intent is not None
    assert intent.intent_type == "TASK_ASSIGNED"
