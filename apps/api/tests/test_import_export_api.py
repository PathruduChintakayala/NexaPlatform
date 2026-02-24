from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.crm.api import get_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact
from app.crm.service import ActorUser
from app.main import app


def _csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


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
def seed_accounts(db_session: Session, legal_entities: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    a1 = CRMAccount(name="Visible Account", status="Active")
    a2 = CRMAccount(name="Blocked Account", status="Active")
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

    base_permissions = {
        "crm.import.execute",
        "crm.export.execute",
        "crm.jobs.read",
    }
    actors = {
        "user1": ActorUser(
            user_id="user-1",
            allowed_legal_entity_ids=[legal_entities["le1"]],
            current_legal_entity_id=legal_entities["le1"],
            permissions=set(base_permissions),
            correlation_id="corr-import-export",
        ),
        "user2": ActorUser(
            user_id="user-2",
            allowed_legal_entity_ids=[legal_entities["le2"]],
            current_legal_entity_id=legal_entities["le2"],
            permissions=set(base_permissions),
            correlation_id="corr-import-export",
        ),
        "admin": ActorUser(
            user_id="admin-1",
            allowed_legal_entity_ids=[],
            current_legal_entity_id=None,
            permissions={*base_permissions, "crm.jobs.read_all", "crm.accounts.read_all", "crm.contacts.read_all"},
            correlation_id="corr-import-export",
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


def test_import_accounts_partial_success_creates_job_and_error_report(
    client: tuple[TestClient, Callable[[str], None]],
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client
    csv_payload = _csv_bytes(
        ["name", "status"],
        [
            ["A One", "Active"],
            ["", "Active"],
            ["A Two", "Active"],
        ],
    )
    mapping = {
        "name": "name",
        "status": "status",
        "fixed_legal_entity_ids": [str(legal_entities["le1"])],
    }

    response = test_client.post(
        "/api/crm/import/accounts?sync=true",
        files={"file": ("accounts.csv", csv_payload, "text/csv")},
        data={"mapping": json.dumps(mapping)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PartiallySucceeded"
    assert body["result"]["created_count"] == 2
    assert body["result"]["error_count"] == 1

    error_artifact = next(item for item in body["artifacts"] if item["artifact_type"] == "ERROR_REPORT_CSV")
    download = test_client.get(f"/api/crm/jobs/{body['id']}/download/ERROR_REPORT_CSV")
    assert download.status_code == 200
    lines = download.text.strip().splitlines()
    assert len(lines) == 2
    assert "name is required" in lines[1]


def test_import_contacts_requires_account_visibility(
    client: tuple[TestClient, Callable[[str], None]],
    seed_accounts: dict[str, uuid.UUID],
    db_session: Session,
) -> None:
    test_client, _ = client
    csv_payload = _csv_bytes(
        ["account_id", "first_name", "last_name"],
        [[str(seed_accounts["a2"]), "Blocked", "Contact"]],
    )
    mapping = {"account_id": "account_id", "first_name": "first_name", "last_name": "last_name"}

    response = test_client.post(
        "/api/crm/import/contacts?sync=true",
        files={"file": ("contacts.csv", csv_payload, "text/csv")},
        data={"mapping": json.dumps(mapping)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Failed"
    assert body["result"]["created_count"] == 0
    assert body["result"]["error_count"] == 1

    count = db_session.scalar(select(CRMContact).where(CRMContact.account_id == seed_accounts["a2"]))
    assert count is None


def test_import_contacts_primary_switching(
    client: tuple[TestClient, Callable[[str], None]],
    seed_accounts: dict[str, uuid.UUID],
    db_session: Session,
) -> None:
    test_client, _ = client
    csv_payload = _csv_bytes(
        ["account_id", "first_name", "last_name", "email", "is_primary"],
        [
            [str(seed_accounts["a1"]), "First", "Primary", "first@example.com", "true"],
            [str(seed_accounts["a1"]), "Second", "Primary", "second@example.com", "true"],
        ],
    )
    mapping = {
        "account_id": "account_id",
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "is_primary": "is_primary",
    }

    response = test_client.post(
        "/api/crm/import/contacts?sync=true",
        files={"file": ("contacts.csv", csv_payload, "text/csv")},
        data={"mapping": json.dumps(mapping)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Succeeded"
    assert body["result"]["created_count"] == 2

    contacts = db_session.scalars(
        select(CRMContact).where(CRMContact.account_id == seed_accounts["a1"], CRMContact.deleted_at.is_(None))
    ).all()
    primaries = [item for item in contacts if item.is_primary]
    assert len(primaries) == 1
    assert primaries[0].email == "second@example.com"


def test_export_accounts_filters_and_download(
    client: tuple[TestClient, Callable[[str], None]],
    db_session: Session,
    legal_entities: dict[str, uuid.UUID],
) -> None:
    test_client, _ = client

    visible = CRMAccount(name="Export Match", status="Active")
    hidden = CRMAccount(name="Other Name", status="Active")
    db_session.add_all([visible, hidden])
    db_session.flush()
    db_session.add_all(
        [
            CRMAccountLegalEntity(account_id=visible.id, legal_entity_id=legal_entities["le1"], is_default=True),
            CRMAccountLegalEntity(account_id=hidden.id, legal_entity_id=legal_entities["le1"], is_default=False),
        ]
    )
    db_session.commit()

    response = test_client.post("/api/crm/export/accounts?sync=true", json={"name": "Match"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Succeeded"

    download = test_client.get(f"/api/crm/jobs/{body['id']}/download/EXPORT_CSV")
    assert download.status_code == 200
    assert "Export Match" in download.text
    assert "Other Name" not in download.text


def test_jobs_access_control(
    client: tuple[TestClient, Callable[[str], None]],
) -> None:
    test_client, set_actor = client

    set_actor("user1")
    create = test_client.post("/api/crm/export/accounts?sync=true", json={})
    assert create.status_code == 200
    job_id = create.json()["id"]

    set_actor("user2")
    blocked_get = test_client.get(f"/api/crm/jobs/{job_id}")
    assert blocked_get.status_code == 404
    blocked_download = test_client.get(f"/api/crm/jobs/{job_id}/download/EXPORT_CSV")
    assert blocked_download.status_code == 404

    set_actor("admin")
    allowed_get = test_client.get(f"/api/crm/jobs/{job_id}")
    assert allowed_get.status_code == 200
    allowed_download = test_client.get(f"/api/crm/jobs/{job_id}/download/EXPORT_CSV")
    assert allowed_download.status_code == 200
