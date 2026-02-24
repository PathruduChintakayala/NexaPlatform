from __future__ import annotations

import re

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

crm_jobs_total = Counter(
    "crm_jobs_total",
    "Total CRM jobs by status",
    ["job_type", "status"],
)

crm_job_duration_seconds = Histogram(
    "crm_job_duration_seconds",
    "CRM job duration in seconds",
    ["job_type"],
)

crm_workflow_guardrail_blocks_total = Counter(
    "crm_workflow_guardrail_blocks_total",
    "Total workflow guardrail blocks by reason",
    ["reason"],
)


_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_INT_RE = re.compile(r"/\d+\b")


def _sanitize_path(path: str) -> str:
    without_uuids = _UUID_RE.sub("{id}", path)
    return _INT_RE.sub("/{id}", without_uuids)


def resolve_http_path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path_format = getattr(route, "path_format", None)
        if isinstance(path_format, str) and path_format:
            return path_format
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            return route_path
    return _sanitize_path(request.url.path)


def observe_http_request(method: str, path: str, status: int, duration: float) -> None:
    status_str = str(status)
    http_requests_total.labels(method=method, path=path, status=status_str).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)


def observe_job(job_type: str, status: str, duration: float) -> None:
    crm_jobs_total.labels(job_type=job_type, status=status).inc()
    crm_job_duration_seconds.labels(job_type=job_type).observe(duration)


def observe_workflow_guardrail_block(reason: str) -> None:
    crm_workflow_guardrail_blocks_total.labels(reason=reason).inc()


def generate_metrics_payload() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
