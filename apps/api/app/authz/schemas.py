from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    is_system: bool = False


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_system: bool
    created_at: datetime


class PermissionCreate(BaseModel):
    resource: str = Field(min_length=1)
    action: str = Field(min_length=1)
    field: str | None = None
    scope_type: str | None = Field(default=None, pattern="^(entity|region)$")
    scope_value: str | None = None
    effect: str = Field(default="allow", pattern="^(allow|deny)$")
    description: str | None = None


class PermissionUpdate(BaseModel):
    resource: str | None = Field(default=None, min_length=1)
    action: str | None = Field(default=None, min_length=1)
    field: str | None = None
    scope_type: str | None = Field(default=None, pattern="^(entity|region)$")
    scope_value: str | None = None
    effect: str | None = Field(default=None, pattern="^(allow|deny)$")
    description: str | None = None


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource: str
    action: str
    field: str | None
    scope_type: str | None
    scope_value: str | None
    effect: str
    description: str | None
    created_at: datetime


class AttachRolePermissionRequest(BaseModel):
    permission_id: UUID


class AssignUserRoleRequest(BaseModel):
    role_id: UUID


class UserRoleRead(BaseModel):
    user_id: str
    role_id: UUID
    role_name: str
    created_at: datetime


class RolePermissionRead(BaseModel):
    role_id: UUID
    role_name: str
    permission_id: UUID
    resource: str
    action: str
    field: str | None
    scope_type: str | None
    scope_value: str | None
    effect: str
    created_at: datetime
