from dataclasses import dataclass

from jose import JWTError, jwt
from starlette.requests import Request

from app.core.config import get_settings


@dataclass
class AuthUser:
    sub: str
    roles: list[str]


async def get_current_user(request: Request) -> AuthUser:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    if not token:
        return AuthUser(sub="anonymous", roles=["guest"])

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        subject = str(payload.get("sub", "anonymous"))
        roles = payload.get("roles", ["user"])
        if not isinstance(roles, list):
            roles = ["user"]
        request.state.context.user_id = subject
        return AuthUser(sub=subject, roles=[str(role) for role in roles])
    except JWTError:
        # TODO: Replace with strict auth failure once real identity provider is wired.
        return AuthUser(sub="anonymous", roles=["guest"])
