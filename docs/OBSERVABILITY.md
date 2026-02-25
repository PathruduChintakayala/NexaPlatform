# Observability

## Logging Strategy
Backend uses JSON structured logging with correlation-id enrichment:
- Config and formatter: `apps/api/app/logging.py`
- Request logs middleware: `apps/api/app/middleware/request_logging.py`
- Correlation middleware: `apps/api/app/middleware/correlation_id.py`

Frontend forwards `x-correlation-id` in each API call:
- `apps/web/lib/api/core.ts`

## Metrics Structure
Prometheus metrics are declared and exported in `apps/api/app/metrics.py`.

Main metric families:
- HTTP traffic and latency
- CRM job throughput/duration
- Workflow guardrail blocks
- Authz cache and DB query counters
- FLS/RLS deny/mask counters
- Ledger posting counters/failures

Metrics endpoint:
- `GET /metrics` in `apps/api/app/api/routes.py`
- gated by config + role check

## Tracing
OTEL instrumentation is initialized in:
- `apps/api/app/otel.py`
- `apps/api/app/main.py`

Capabilities in code:
- FastAPI instrumentation hook
- Optional OTLP exporter via `OTEL_EXPORTER_OTLP_ENDPOINT`
- Optional console exporter via `OTEL_CONSOLE_EXPORTER`
- In-memory exporter helper for tests

## How to Add New Instrumentation
1. **Metrics**: add counter/histogram in `apps/api/app/metrics.py`; call from service/middleware/repository.
2. **Logs**: emit logger records with known fields or structured extras (`apps/api/app/logging.py`).
3. **Traces**: use tracer from `apps/api/app/otel.py` and add span attributes (including correlation id where useful).

## Source References
- `apps/api/app/metrics.py`
- `apps/api/app/logging.py`
- `apps/api/app/otel.py`
- `apps/api/app/api/routes.py`
- `apps/api/tests/test_metrics_endpoint.py`
- `apps/api/tests/test_otel_spans.py`
