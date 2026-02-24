from __future__ import annotations

import uuid

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.context import reset_correlation_id, set_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute("correlation_id", correlation_id)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)

        response.headers["x-correlation-id"] = correlation_id
        return response
