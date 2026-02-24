from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.context import get_correlation_id
from app.core.config import get_settings


@dataclass
class _BucketState:
    tokens: float
    last_refill: float


class _TokenBucketLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _BucketState] = {}

    def take(self, user_id: str, route_group: str, capacity: int, window_seconds: int) -> tuple[bool, int]:
        if capacity <= 0:
            return False, window_seconds

        now = time.monotonic()
        refill_rate = capacity / float(window_seconds)
        key = (user_id, route_group)

        with self._lock:
            current = self._buckets.get(key)
            if current is None:
                current = _BucketState(tokens=float(capacity), last_refill=now)
                self._buckets[key] = current

            elapsed = max(0.0, now - current.last_refill)
            current.tokens = min(float(capacity), current.tokens + (elapsed * refill_rate))
            current.last_refill = now

            if current.tokens < 1.0:
                retry_after = max(1, math.ceil((1.0 - current.tokens) / refill_rate))
                return False, retry_after

            current.tokens -= 1.0
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


_limiter = _TokenBucketLimiter()


class CrmMutationRateLimitMiddleware(BaseHTTPMiddleware):
    mutating_methods = {"POST", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = get_settings()
        if settings.rate_limit_disabled:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/crm") or request.method.upper() not in self.mutating_methods:
            return await call_next(request)

        user_id = _resolve_user_id(request)
        route_group = _resolve_route_group(path)
        allowed, retry_after = _limiter.take(
            user_id=user_id,
            route_group=route_group,
            capacity=settings.rate_limit_crm_mutations_per_minute,
            window_seconds=60,
        )
        if allowed:
            return await call_next(request)

        correlation_id = (
            get_correlation_id()
            or getattr(request.state, "correlation_id", None)
            or request.headers.get("x-correlation-id")
            or str(uuid.uuid4())
        )
        response = JSONResponse(
            status_code=429,
            content={
                "code": "RATE_LIMITED",
                "message": "Too many requests",
                "details": None,
                "correlation_id": correlation_id,
            },
        )
        response.headers["Retry-After"] = str(retry_after)
        response.headers["X-Correlation-Id"] = correlation_id
        return response


def _resolve_route_group(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3:
        return "crm"
    return parts[2]


def _resolve_user_id(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    if not token:
        return "anonymous"

    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return "anonymous"

    subject = payload.get("sub")
    if subject is None:
        return "anonymous"
    return str(subject)


def reset_rate_limiter() -> None:
    _limiter.clear()
