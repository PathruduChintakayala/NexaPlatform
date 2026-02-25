"""create authz tables and baseline seed

Revision ID: 202602250001
Revises: 202602240012
Create Date: 2026-02-25 10:00:00
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = "202602250001"
down_revision: str | None = "202602240012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "authz_role",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "authz_permission",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=128), nullable=True),
        sa.Column("scope_type", sa.String(length=16), nullable=True),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("effect", sa.String(length=16), nullable=False, server_default="allow"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource",
            "action",
            "field",
            "scope_type",
            "scope_value",
            "effect",
            name="uq_authz_permission_rule",
        ),
    )

    op.create_table(
        "authz_role_permission",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["authz_permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["authz_role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "authz_user_role",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["authz_role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        "authz_policy_set",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "authz_tenant_policy",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("policy_set_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_set_id"], ["authz_policy_set.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "policy_set_id"),
    )

    _seed_baseline()


def downgrade() -> None:
    op.drop_table("authz_tenant_policy")
    op.drop_table("authz_policy_set")
    op.drop_table("authz_user_role")
    op.drop_table("authz_role_permission")
    op.drop_table("authz_permission")
    op.drop_table("authz_role")


def _seed_baseline() -> None:
    now = datetime.now(timezone.utc)

    role_ids = {
        "Admin": uuid.UUID("52fb1ed5-5e01-4658-a573-0a09f64a48f5"),
        "Sales": uuid.UUID("4f2c0099-adb3-453f-8ec7-2dc76396f2f6"),
        "Support": uuid.UUID("fbecf7e6-a1da-43e4-99c6-7d5dbfa4932a"),
        "ReadOnly": uuid.UUID("62f1006e-3605-4dc6-84cd-44f6f89ec3f6"),
    }

    permission_ids = {
        "contact.read": uuid.UUID("75f56a5f-ea08-4e66-a2a3-70cfaf2ce5fc"),
        "contact.create": uuid.UUID("21a0a00f-c82a-4659-b0df-b6e4c1c41d7e"),
        "contact.update": uuid.UUID("4c6e6ce9-4633-4905-a79e-c8c7af2a29de"),
        "contact.delete": uuid.UUID("6f849fc8-efde-4637-a80e-f7d0b37a2ad5"),
        "contact.field.read.all": uuid.UUID("6d6bcbb6-8f55-4324-95f7-f381c6fd42df"),
        "contact.field.edit.all": uuid.UUID("d9bc9db1-2277-4338-9821-02b640df8f5d"),
        "contact.field.mask.email": uuid.UUID("6f8f92fc-8cb5-4ccf-aed3-e6f5fddf789d"),
        "contact.field.mask.phone": uuid.UUID("40f0d2af-39cb-4d0a-8581-472554dc18be"),
    }

    role_table = sa.table(
        "authz_role",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        role_table,
        [
            {"id": role_ids["Admin"], "name": "Admin", "description": "Platform administrators", "is_system": True, "created_at": now},
            {"id": role_ids["Sales"], "name": "Sales", "description": "CRM sales users", "is_system": True, "created_at": now},
            {"id": role_ids["Support"], "name": "Support", "description": "Support users with masked contact data", "is_system": True, "created_at": now},
            {"id": role_ids["ReadOnly"], "name": "ReadOnly", "description": "Read-only CRM users", "is_system": True, "created_at": now},
        ],
    )

    permission_table = sa.table(
        "authz_permission",
        sa.column("id", sa.Uuid()),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("field", sa.String()),
        sa.column("scope_type", sa.String()),
        sa.column("scope_value", sa.String()),
        sa.column("effect", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        permission_table,
        [
            {"id": permission_ids["contact.read"], "resource": "crm.contact", "action": "read", "field": None, "scope_type": None, "scope_value": None, "effect": "allow", "description": "Read contacts", "created_at": now},
            {"id": permission_ids["contact.create"], "resource": "crm.contact", "action": "create", "field": None, "scope_type": None, "scope_value": None, "effect": "allow", "description": "Create contacts", "created_at": now},
            {"id": permission_ids["contact.update"], "resource": "crm.contact", "action": "update", "field": None, "scope_type": None, "scope_value": None, "effect": "allow", "description": "Update contacts", "created_at": now},
            {"id": permission_ids["contact.delete"], "resource": "crm.contact", "action": "delete", "field": None, "scope_type": None, "scope_value": None, "effect": "allow", "description": "Delete contacts", "created_at": now},
            {"id": permission_ids["contact.field.read.all"], "resource": "crm.contact", "action": "field.read", "field": "*", "scope_type": None, "scope_value": None, "effect": "allow", "description": "Read all contact fields", "created_at": now},
            {"id": permission_ids["contact.field.edit.all"], "resource": "crm.contact", "action": "field.edit", "field": "*", "scope_type": None, "scope_value": None, "effect": "allow", "description": "Edit all contact fields", "created_at": now},
            {"id": permission_ids["contact.field.mask.email"], "resource": "crm.contact", "action": "field.mask", "field": "email", "scope_type": None, "scope_value": None, "effect": "allow", "description": "Mask contact email", "created_at": now},
            {"id": permission_ids["contact.field.mask.phone"], "resource": "crm.contact", "action": "field.mask", "field": "phone", "scope_type": None, "scope_value": None, "effect": "allow", "description": "Mask contact phone", "created_at": now},
        ],
    )

    role_permission_table = sa.table(
        "authz_role_permission",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    links: list[dict[str, object]] = []

    for permission_id in permission_ids.values():
        links.append({"role_id": role_ids["Admin"], "permission_id": permission_id, "created_at": now})

    for key in [
        "contact.read",
        "contact.create",
        "contact.update",
        "contact.field.read.all",
        "contact.field.edit.all",
    ]:
        links.append({"role_id": role_ids["Sales"], "permission_id": permission_ids[key], "created_at": now})

    for key in [
        "contact.read",
        "contact.field.read.all",
        "contact.field.mask.email",
        "contact.field.mask.phone",
    ]:
        links.append({"role_id": role_ids["Support"], "permission_id": permission_ids[key], "created_at": now})

    for key in ["contact.read", "contact.field.read.all"]:
        links.append({"role_id": role_ids["ReadOnly"], "permission_id": permission_ids[key], "created_at": now})

    op.bulk_insert(role_permission_table, links)
