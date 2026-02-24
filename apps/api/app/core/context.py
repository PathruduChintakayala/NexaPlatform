from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


@dataclass
class RequestContext:
    request_id: str
    correlation_id: str
    user_id: str | None
    legal_entity: str
    region: str
    currency: str


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = getattr(request.state, "correlation_id", None)
        request.state.context = RequestContext(
            request_id=correlation_id or "",
            correlation_id=correlation_id or "",
            user_id=None,
            legal_entity=request.headers.get("x-legal-entity", "default"),
            region=request.headers.get("x-region", "global"),
            currency=request.headers.get("x-currency", "USD"),
        )
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.context.request_id
        return response
