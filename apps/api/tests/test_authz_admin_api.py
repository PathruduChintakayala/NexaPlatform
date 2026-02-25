from __future__ import annotations

import uuid
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.authz.api import get_current_user as get_admin_current_user
from app.core.auth import AuthUser
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.crm.api import get_current_user as get_crm_current_user
from app.crm.models import CRMAccount, CRMAccountLegalEntity
from app.crm.service import ActorUser
from app.main import app
from app.middleware.rate_limit import reset_rate_limiter
from app.platform.security.policies import DbPolicyBackend, InMemoryPolicyBackend, set_policy_backend


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
def setup_env(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> Generator[None, None, None]:
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "true")
    get_settings.cache_clear()
    set_policy_backend(DbPolicyBackend(session_factory=sessionmaker(bind=db_session.bind), default_allow=True))
    reset_rate_limiter()
    yield
    set_policy_backend(InMemoryPolicyBackend(default_allow=True))
    get_settings.cache_clear()
    reset_rate_limiter()


@pytest.fixture()
def legal_entity_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def account_id(db_session: Session, legal_entity_id: uuid.UUID) -> uuid.UUID:
    account = CRMAccount(name="Authz Account", status="Active")
    db_session.add(account)
    db_session.flush()
    db_session.add(CRMAccountLegalEntity(account_id=account.id, legal_entity_id=legal_entity_id, is_default=True))
    db_session.commit()
    return account.id


@pytest.fixture()
def client(
    db_session: Session,
    legal_entity_id: uuid.UUID,
) -> Generator[tuple[TestClient, Callable[[str], None]], None, None]:
    state = {"actor": "admin"}

    admin_user = AuthUser(sub="admin-user", roles=["admin"])

    crm_actors = {
        "admin": ActorUser(
            user_id="admin-user",
            allowed_legal_entity_ids=[legal_entity_id],
            current_legal_entity_id=legal_entity_id,
            permissions={
                "crm.contacts.create",
                "crm.contacts.read",
                "crm.contacts.update",
                "crm.contacts.delete",
                "crm.workflows.manage",
                "crm.workflows.execute",
                "crm.workflows.read",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
                "crm.custom_fields.manage",
                "crm.custom_fields.read",
            },
            correlation_id="authz-admin",
        ),
        "sales": ActorUser(
            user_id="sales-user",
            allowed_legal_entity_ids=[legal_entity_id],
            current_legal_entity_id=legal_entity_id,
            permissions={
                "crm.contacts.create",
                "crm.contacts.read",
                "crm.contacts.update",
                "crm.contacts.delete",
                "crm.workflows.manage",
                "crm.workflows.execute",
                "crm.workflows.read",
                "crm.leads.create",
                "crm.leads.read",
                "crm.leads.update",
            },
            correlation_id="authz-sales",
        ),
    }

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_crm_user() -> ActorUser:
        actor = crm_actors[state["actor"]]
        return ActorUser(
            user_id=actor.user_id,
            allowed_legal_entity_ids=actor.allowed_legal_entity_ids,
            current_legal_entity_id=actor.current_legal_entity_id,
            permissions=actor.permissions,
            correlation_id=str(uuid.uuid4()),
        )

    def override_admin_user() -> AuthUser:
        return admin_user

    def set_actor(actor: str) -> None:
        state["actor"] = actor

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_crm_current_user] = override_crm_user
    app.dependency_overrides[get_admin_current_user] = override_admin_user

    with TestClient(app) as test_client:
        yield test_client, set_actor

    app.dependency_overrides.clear()


def _create_role_permission_and_assign(client: TestClient, user_id: str) -> None:
    role_response = client.post(
        "/admin/roles",
        json={"name": "MaskedRole", "description": "Mask email and deny custom fields", "is_system": False},
    )
    assert role_response.status_code == 201
    role_id = role_response.json()["id"]

    permissions_payloads = [
        {"resource": "crm.contact", "action": "field.read", "field": "*", "effect": "allow"},
        {"resource": "crm.contact", "action": "field.mask", "field": "email", "effect": "allow"},
        {"resource": "crm.contact", "action": "field.read", "field": "custom_fields", "effect": "deny"},
        {"resource": "crm.contact", "action": "field.edit", "field": "first_name", "effect": "allow"},
        {"resource": "crm.lead", "action": "field.edit", "field": "qualification_notes", "effect": "deny"},
    ]

    permission_ids: list[str] = []
    for payload in permissions_payloads:
        response = client.post("/admin/permissions", json=payload)
        assert response.status_code == 201
        permission_ids.append(response.json()["id"])

    for permission_id in permission_ids:
        link_response = client.post(f"/admin/roles/{role_id}/permissions", json={"permission_id": permission_id})
        assert link_response.status_code == 201

    assign_response = client.post(f"/admin/users/{user_id}/roles", json={"role_id": role_id})
    assert assign_response.status_code == 201


def test_admin_role_assignment_enforces_contact_and_workflow_fls(
    client: tuple[TestClient, Callable[[str], None]],
    account_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
) -> None:
    test_client, set_actor = client

    set_actor("admin")
    custom_field_def = test_client.post(
        "/api/crm/custom-fields/contact",
        json={"field_key": "vip", "label": "VIP", "data_type": "bool"},
    )
    assert custom_field_def.status_code == 201

    set_actor("sales")

    create_contact = test_client.post(
        f"/api/crm/accounts/{account_id}/contacts",
        json={
            "account_id": str(account_id),
            "first_name": "Jamie",
            "last_name": "Doe",
            "email": "jamie@example.com",
            "title": "Rep",
            "custom_fields": {"vip": True},
        },
    )
    assert create_contact.status_code == 201
    contact = create_contact.json()

    set_actor("admin")
    _create_role_permission_and_assign(test_client, "sales-user")
    set_actor("sales")

    read_contact = test_client.get(f"/api/crm/contacts/{contact['id']}")
    assert read_contact.status_code == 200
    read_body = read_contact.json()
    assert read_body["email"] == "***"
    assert read_body["custom_fields"] == {}

    patch_forbidden = test_client.patch(
        f"/api/crm/contacts/{contact['id']}",
        json={"row_version": contact["row_version"], "title": "Director"},
    )
    assert patch_forbidden.status_code == 403

    create_lead = test_client.post(
        "/api/crm/leads",
        json={
            "status": "New",
            "source": "Web",
            "selling_legal_entity_id": str(legal_entity_id),
            "region_code": "US",
            "company_name": "AuthzCo",
        },
    )
    assert create_lead.status_code == 201
    lead_id = create_lead.json()["id"]

    create_rule = test_client.post(
        "/api/crm/workflows",
        json={
            "name": "Blocked by FLS",
            "trigger_event": "crm.lead.updated",
            "condition_json": {"path": "status", "op": "eq", "value": "New"},
            "actions_json": [{"type": "SET_FIELD", "path": "qualification_notes", "value": "blocked"}],
        },
    )
    assert create_rule.status_code == 201

    execute_rule = test_client.post(
        f"/api/crm/workflows/{create_rule.json()['id']}/execute",
        json={"entity_type": "lead", "entity_id": lead_id},
    )
    assert execute_rule.status_code == 403


def test_admin_listing_endpoints(
    client: tuple[TestClient, Callable[[str], None]],
) -> None:
    test_client, _set_actor = client

    _create_role_permission_and_assign(test_client, "sales-user")

    roles = test_client.get("/admin/roles")
    permissions = test_client.get("/admin/permissions")
    assignments = test_client.get("/admin/user-role-assignments")

    assert roles.status_code == 200
    assert permissions.status_code == 200
    assert assignments.status_code == 200
    assert any(item["user_id"] == "sales-user" for item in assignments.json())


def test_admin_can_update_and_remove_role_permission_assignments(
    client: tuple[TestClient, Callable[[str], None]],
) -> None:
    test_client, _set_actor = client

    role_response = test_client.post(
        "/admin/roles",
        json={"name": "OpsEditor", "description": "Initial", "is_system": False},
    )
    assert role_response.status_code == 201
    role_id = role_response.json()["id"]

    permission_response = test_client.post(
        "/admin/permissions",
        json={"resource": "crm.contact", "action": "field.read", "field": "email", "effect": "allow"},
    )
    assert permission_response.status_code == 201
    permission_id = permission_response.json()["id"]

    attach_response = test_client.post(
        f"/admin/roles/{role_id}/permissions",
        json={"permission_id": permission_id},
    )
    assert attach_response.status_code == 201

    assign_response = test_client.post(f"/admin/users/sales-user/roles", json={"role_id": role_id})
    assert assign_response.status_code == 201

    update_role_response = test_client.patch(
        f"/admin/roles/{role_id}",
        json={"name": "OpsEditorUpdated", "description": "Updated"},
    )
    assert update_role_response.status_code == 200
    assert update_role_response.json()["name"] == "OpsEditorUpdated"

    update_permission_response = test_client.patch(
        f"/admin/permissions/{permission_id}",
        json={"action": "field.mask", "field": "email", "effect": "allow"},
    )
    assert update_permission_response.status_code == 200
    assert update_permission_response.json()["action"] == "field.mask"

    detach_response = test_client.delete(f"/admin/roles/{role_id}/permissions/{permission_id}")
    assert detach_response.status_code == 200

    role_permissions_after_detach = test_client.get(f"/admin/roles/{role_id}/permissions")
    assert role_permissions_after_detach.status_code == 200
    assert role_permissions_after_detach.json() == []

    unassign_response = test_client.delete(f"/admin/users/sales-user/roles/{role_id}")
    assert unassign_response.status_code == 200

    assignments_after_unassign = test_client.get("/admin/user-role-assignments")
    assert assignments_after_unassign.status_code == 200
    assert all(item["role_id"] != role_id for item in assignments_after_unassign.json())

    delete_permission_response = test_client.delete(f"/admin/permissions/{permission_id}")
    assert delete_permission_response.status_code == 200

    delete_role_response = test_client.delete(f"/admin/roles/{role_id}")
    assert delete_role_response.status_code == 200
