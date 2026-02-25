from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.authz.schemas import (
    AssignUserRoleRequest,
    AttachRolePermissionRequest,
    PermissionCreate,
    PermissionRead,
    PermissionUpdate,
    RolePermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserRoleRead,
)
from app.authz.service import authorization_admin_service
from app.core.auth import AuthUser, get_current_user
from app.core.database import get_db


admin_router = APIRouter(prefix="/admin", tags=["admin.authz"])


def _require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if "admin" not in user.roles and "system.admin" not in user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing role: admin")
    return user


@admin_router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    dto: RoleCreate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> RoleRead:
    return authorization_admin_service.create_role(db, dto)


@admin_router.get("/roles", response_model=list[RoleRead])
def list_roles(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> list[RoleRead]:
    return authorization_admin_service.list_roles(db)


@admin_router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: uuid.UUID,
    dto: RoleUpdate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> RoleRead:
    return authorization_admin_service.update_role(db, role_id, dto)


@admin_router.delete("/roles/{role_id}", status_code=status.HTTP_200_OK)
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> None:
    authorization_admin_service.delete_role(db, role_id)


@admin_router.post("/permissions", response_model=PermissionRead, status_code=status.HTTP_201_CREATED)
def create_permission(
    dto: PermissionCreate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> PermissionRead:
    return authorization_admin_service.create_permission(db, dto)


@admin_router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> list[PermissionRead]:
    return authorization_admin_service.list_permissions(db)


@admin_router.patch("/permissions/{permission_id}", response_model=PermissionRead)
def update_permission(
    permission_id: uuid.UUID,
    dto: PermissionUpdate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> PermissionRead:
    return authorization_admin_service.update_permission(db, permission_id, dto)


@admin_router.delete("/permissions/{permission_id}", status_code=status.HTTP_200_OK)
def delete_permission(
    permission_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> None:
    authorization_admin_service.delete_permission(db, permission_id)


@admin_router.post("/roles/{role_id}/permissions", response_model=RolePermissionRead, status_code=status.HTTP_201_CREATED)
def attach_role_permission(
    role_id: uuid.UUID,
    dto: AttachRolePermissionRequest,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> RolePermissionRead:
    return authorization_admin_service.attach_permission_to_role(db, role_id, dto.permission_id)


@admin_router.get("/roles/{role_id}/permissions", response_model=list[RolePermissionRead])
def list_role_permissions(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> list[RolePermissionRead]:
    return authorization_admin_service.list_role_permissions(db, role_id=role_id)


@admin_router.delete("/roles/{role_id}/permissions/{permission_id}", status_code=status.HTTP_200_OK)
def detach_role_permission(
    role_id: uuid.UUID,
    permission_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> None:
    authorization_admin_service.detach_permission_from_role(db, role_id, permission_id)


@admin_router.post("/users/{user_id}/roles", response_model=UserRoleRead, status_code=status.HTTP_201_CREATED)
def assign_user_role(
    user_id: str,
    dto: AssignUserRoleRequest,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> UserRoleRead:
    return authorization_admin_service.assign_role_to_user(db, user_id, dto.role_id)


@admin_router.get("/users/{user_id}/roles", response_model=list[UserRoleRead])
def list_user_roles(
    user_id: str,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> list[UserRoleRead]:
    return authorization_admin_service.list_user_roles(db, user_id=user_id)


@admin_router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_200_OK)
def unassign_user_role(
    user_id: str,
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> None:
    authorization_admin_service.unassign_role_from_user(db, user_id=user_id, role_id=role_id)


@admin_router.get("/user-role-assignments", response_model=list[UserRoleRead])
def list_all_user_roles(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(_require_admin),
) -> list[UserRoleRead]:
    return authorization_admin_service.list_user_roles(db)
