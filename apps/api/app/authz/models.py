from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "authz_role"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Permission(Base):
    __tablename__ = "authz_permission"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effect: Mapped[str] = mapped_column(String(16), nullable=False, default="allow", server_default="allow")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    roles: Mapped[list[RolePermission]] = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "resource",
            "action",
            "field",
            "scope_type",
            "scope_value",
            "effect",
            name="uq_authz_permission_rule",
        ),
    )


class RolePermission(Base):
    __tablename__ = "authz_role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("authz_role.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("authz_permission.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    role: Mapped[Role] = relationship("Role", back_populates="permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="roles")


class UserRole(Base):
    __tablename__ = "authz_user_role"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("authz_role.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PolicySet(Base):
    __tablename__ = "authz_policy_set"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class TenantPolicy(Base):
    __tablename__ = "authz_tenant_policy"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    policy_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("authz_policy_set.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
