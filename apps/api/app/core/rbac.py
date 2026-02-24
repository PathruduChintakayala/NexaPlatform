from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.auth import AuthUser, get_current_user


def require_permissions(*permissions: str) -> Callable[[AuthUser], AuthUser]:
    async def checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        missing_permissions = [permission for permission in permissions if permission not in user.roles]
        if missing_permissions:
            # TODO: Replace role-only check with policy-based RBAC/ABAC evaluation.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing_permissions)}",
            )
        return user

    return checker
