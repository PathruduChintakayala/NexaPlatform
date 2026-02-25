from __future__ import annotations

import uuid
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.authz.models import Permission, Role, RolePermission, UserRole
from app.core.database import Base
from app.platform.security.context import AuthContext
from app.platform.security.policies import DbPolicyBackend, FieldDecision


def _seed_role_with_permissions(
    session: Session,
    *,
    user_id: str,
    role_name: str,
    permissions: list[tuple[str, str, str | None, str]],
) -> None:
    role = Role(name=role_name, is_system=False)
    session.add(role)
    session.flush()

    for resource, action, field, effect in permissions:
        permission = Permission(resource=resource, action=action, field=field, effect=effect)
        session.add(permission)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))

    session.add(UserRole(user_id=user_id, role_id=role.id))
    session.commit()


def test_db_policy_field_precedence_and_conflicts() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        _seed_role_with_permissions(
            session,
            user_id="user-a",
            role_name="Role-A",
            permissions=[
                ("crm.contact", "field.read", "*", "allow"),
                ("crm.contact", "field.read", "email", "deny"),
                ("crm.contact", "field.mask", "email", "allow"),
                ("crm.contact", "field.edit", "*", "allow"),
                ("crm.contact", "field.edit", "phone", "deny"),
            ],
        )

    backend = DbPolicyBackend(session_factory=SessionLocal, default_allow=True)
    ctx = AuthContext(user_id="user-a")

    assert backend.evaluate_field_read("crm.contact", "email", ctx) == FieldDecision.DENY
    assert backend.evaluate_field_read("crm.contact", "first_name", ctx) == FieldDecision.ALLOW
    assert backend.can_edit_field("crm.contact", "phone", ctx) is False
    assert backend.can_edit_field("crm.contact", "department", ctx) is True


def test_db_policy_mask_overrides_allow_and_default_allow_without_roles() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        _seed_role_with_permissions(
            session,
            user_id="user-b",
            role_name="Role-B",
            permissions=[
                ("crm.contact", "field.read", "email", "allow"),
                ("crm.contact", "field.mask", "email", "allow"),
            ],
        )

    backend = DbPolicyBackend(session_factory=SessionLocal, default_allow=True)

    masked_ctx = AuthContext(user_id="user-b")
    assert backend.evaluate_field_read("crm.contact", "email", masked_ctx) == FieldDecision.MASK

    no_role_ctx = AuthContext(user_id="no-roles-user")
    assert backend.evaluate_field_read("crm.contact", "email", no_role_ctx) == FieldDecision.ALLOW
    assert backend.can_edit_field("crm.contact", "title", no_role_ctx) is True
