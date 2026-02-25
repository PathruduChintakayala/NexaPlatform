from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.models import Permission, Role, RolePermission, UserRole
from app.authz.schemas import (
    PermissionCreate,
    PermissionRead,
    PermissionUpdate,
    RoleCreate,
    RolePermissionRead,
    RoleRead,
    RoleUpdate,
    UserRoleRead,
)


class AuthorizationAdminService:
    def create_role(self, session: Session, dto: RoleCreate) -> RoleRead:
        role = Role(name=dto.name.strip(), description=dto.description, is_system=dto.is_system)
        session.add(role)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role already exists")
        session.refresh(role)
        return RoleRead.model_validate(role)

    def list_roles(self, session: Session) -> list[RoleRead]:
        rows = session.scalars(select(Role).order_by(Role.name.asc())).all()
        return [RoleRead.model_validate(row) for row in rows]

    def update_role(self, session: Session, role_id: uuid.UUID, dto: RoleUpdate) -> RoleRead:
        role = session.scalar(select(Role).where(Role.id == role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
        if role.is_system:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system role cannot be modified")

        if dto.name is not None:
            role.name = dto.name.strip()
        role.description = dto.description

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role already exists")
        session.refresh(role)
        return RoleRead.model_validate(role)

    def delete_role(self, session: Session, role_id: uuid.UUID) -> None:
        role = session.scalar(select(Role).where(Role.id == role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
        if role.is_system:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system role cannot be deleted")

        session.delete(role)
        session.commit()

    def create_permission(self, session: Session, dto: PermissionCreate) -> PermissionRead:
        permission = Permission(
            resource=dto.resource.strip(),
            action=dto.action.strip(),
            field=dto.field.strip() if dto.field is not None else None,
            scope_type=dto.scope_type,
            scope_value=dto.scope_value,
            effect=dto.effect,
            description=dto.description,
        )
        session.add(permission)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="permission already exists")
        session.refresh(permission)
        return PermissionRead.model_validate(permission)

    def list_permissions(self, session: Session) -> list[PermissionRead]:
        rows = session.scalars(
            select(Permission).order_by(Permission.resource.asc(), Permission.action.asc(), Permission.field.asc())
        ).all()
        return [PermissionRead.model_validate(row) for row in rows]

    def update_permission(self, session: Session, permission_id: uuid.UUID, dto: PermissionUpdate) -> PermissionRead:
        permission = session.scalar(select(Permission).where(Permission.id == permission_id))
        if permission is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="permission not found")

        if dto.resource is not None:
            permission.resource = dto.resource.strip()
        if dto.action is not None:
            permission.action = dto.action.strip()
        permission.field = dto.field
        permission.scope_type = dto.scope_type
        permission.scope_value = dto.scope_value
        if dto.effect is not None:
            permission.effect = dto.effect
        permission.description = dto.description

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="permission already exists")
        session.refresh(permission)
        return PermissionRead.model_validate(permission)

    def delete_permission(self, session: Session, permission_id: uuid.UUID) -> None:
        permission = session.scalar(select(Permission).where(Permission.id == permission_id))
        if permission is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="permission not found")

        session.delete(permission)
        session.commit()

    def attach_permission_to_role(self, session: Session, role_id: uuid.UUID, permission_id: uuid.UUID) -> RolePermissionRead:
        role = session.scalar(select(Role).where(Role.id == role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")

        permission = session.scalar(select(Permission).where(Permission.id == permission_id))
        if permission is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="permission not found")

        mapping = session.scalar(
            select(RolePermission).where(
                and_(RolePermission.role_id == role_id, RolePermission.permission_id == permission_id)
            )
        )
        if mapping is None:
            mapping = RolePermission(role_id=role_id, permission_id=permission_id)
            session.add(mapping)
            session.commit()
            session.refresh(mapping)

        return RolePermissionRead(
            role_id=role.id,
            role_name=role.name,
            permission_id=permission.id,
            resource=permission.resource,
            action=permission.action,
            field=permission.field,
            scope_type=permission.scope_type,
            scope_value=permission.scope_value,
            effect=permission.effect,
            created_at=mapping.created_at,
        )

    def assign_role_to_user(self, session: Session, user_id: str, role_id: uuid.UUID) -> UserRoleRead:
        role = session.scalar(select(Role).where(Role.id == role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")

        mapping = session.scalar(
            select(UserRole).where(
                and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
            )
        )
        if mapping is None:
            mapping = UserRole(user_id=user_id, role_id=role_id)
            session.add(mapping)
            session.commit()
            session.refresh(mapping)

        return UserRoleRead(user_id=mapping.user_id, role_id=mapping.role_id, role_name=role.name, created_at=mapping.created_at)

    def list_role_permissions(self, session: Session, role_id: uuid.UUID | None = None) -> list[RolePermissionRead]:
        stmt = (
            select(RolePermission, Role, Permission)
            .join(Role, RolePermission.role_id == Role.id)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .order_by(Role.name.asc(), Permission.resource.asc(), Permission.action.asc(), Permission.field.asc())
        )
        if role_id is not None:
            stmt = stmt.where(RolePermission.role_id == role_id)

        rows = session.execute(stmt).all()
        return [
            RolePermissionRead(
                role_id=role.id,
                role_name=role.name,
                permission_id=permission.id,
                resource=permission.resource,
                action=permission.action,
                field=permission.field,
                scope_type=permission.scope_type,
                scope_value=permission.scope_value,
                effect=permission.effect,
                created_at=mapping.created_at,
            )
            for mapping, role, permission in rows
        ]

    def detach_permission_from_role(self, session: Session, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:
        mapping = session.scalar(
            select(RolePermission).where(
                and_(RolePermission.role_id == role_id, RolePermission.permission_id == permission_id)
            )
        )
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role-permission mapping not found")

        session.delete(mapping)
        session.commit()

    def list_user_roles(self, session: Session, user_id: str | None = None) -> list[UserRoleRead]:
        stmt = select(UserRole, Role).join(Role, UserRole.role_id == Role.id).order_by(UserRole.user_id.asc(), Role.name.asc())
        if user_id is not None:
            stmt = stmt.where(UserRole.user_id == user_id)
        rows = session.execute(stmt).all()
        return [
            UserRoleRead(user_id=mapping.user_id, role_id=mapping.role_id, role_name=role.name, created_at=mapping.created_at)
            for mapping, role in rows
        ]

    def unassign_role_from_user(self, session: Session, user_id: str, role_id: uuid.UUID) -> None:
        mapping = session.scalar(
            select(UserRole).where(
                and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
            )
        )
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user-role mapping not found")

        session.delete(mapping)
        session.commit()


authorization_admin_service = AuthorizationAdminService()
