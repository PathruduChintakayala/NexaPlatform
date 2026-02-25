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

fls_masked_fields_count = Counter(
    "fls_masked_fields_count",
    "Total FLS-masked fields",
    ["resource", "operation"],
)

fls_denied_fields_count = Counter(
    "fls_denied_fields_count",
    "Total FLS-denied fields",
    ["resource", "operation"],
)

authz_policy_cache_hit_total = Counter(
    "authz_policy_cache_hit_total",
    "Authorization policy cache hits",
)

authz_policy_cache_miss_total = Counter(
    "authz_policy_cache_miss_total",
    "Authorization policy cache misses",
)

authz_db_queries_count_total = Counter(
    "authz_db_queries_count_total",
    "Authorization DB query count",
)

rls_denied_reads_count = Counter(
    "rls_denied_reads_count",
    "Total denied reads by RLS",
    ["resource", "scope_type"],
)

rls_denied_writes_count = Counter(
    "rls_denied_writes_count",
    "Total denied writes by RLS",
    ["resource", "scope_type"],
)

ledger_entries_posted_count = Counter(
    "ledger_entries_posted_count",
    "Total posted ledger entries",
)

ledger_lines_posted_count = Counter(
    "ledger_lines_posted_count",
    "Total posted ledger lines",
)

ledger_post_failures_count = Counter(
    "ledger_post_failures_count",
    "Total ledger post failures by reason",
    ["reason"],
)


_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_INT_RE = re.compile(r"/\d+\b")
_PATH_PARAM_RE = re.compile(r"\{[^{}]+\}")


def _normalize_route_template(path: str) -> str:
    if path == "/api/crm/opportunities/{opportunity_id}/close-won":
        return path
    return _PATH_PARAM_RE.sub("{id}", path)


def _sanitize_path(path: str) -> str:
    without_uuids = _UUID_RE.sub("{id}", path)
    return _INT_RE.sub("/{id}", without_uuids)


def resolve_http_path_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path_format = getattr(route, "path_format", None)
        if isinstance(path_format, str) and path_format:
            return _normalize_route_template(path_format)
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            return _normalize_route_template(route_path)
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


def observe_fls_field_counts(resource: str, operation: str, masked_count: int, denied_count: int) -> None:
    if masked_count > 0:
        fls_masked_fields_count.labels(resource=resource, operation=operation).inc(masked_count)
    if denied_count > 0:
        fls_denied_fields_count.labels(resource=resource, operation=operation).inc(denied_count)


def observe_authz_policy_cache_hit() -> None:
    authz_policy_cache_hit_total.inc()


def observe_authz_policy_cache_miss() -> None:
    authz_policy_cache_miss_total.inc()


def observe_authz_db_queries_count(count: int = 1) -> None:
    if count > 0:
        authz_db_queries_count_total.inc(count)


def observe_rls_denied_read(resource: str, scope_type: str) -> None:
    rls_denied_reads_count.labels(resource=resource, scope_type=scope_type).inc()


def observe_rls_denied_write(resource: str, scope_type: str) -> None:
    rls_denied_writes_count.labels(resource=resource, scope_type=scope_type).inc()


def observe_ledger_entries_posted(count: int = 1) -> None:
    if count > 0:
        ledger_entries_posted_count.inc(count)


def observe_ledger_lines_posted(count: int = 1) -> None:
    if count > 0:
        ledger_lines_posted_count.inc(count)


def observe_ledger_post_failure(reason: str) -> None:
    ledger_post_failures_count.labels(reason=reason).inc()


def generate_metrics_payload() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
