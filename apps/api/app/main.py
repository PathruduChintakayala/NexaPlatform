from contextlib import asynccontextmanager, contextmanager
from datetime import date
import logging
from typing import Any
import uuid

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.context import RequestContextMiddleware
from app.core.events import InternalEvent, event_bus
from app.core.database import SessionLocal, get_db
from app.business.billing.service import billing_service
from app.crm.service import WorkflowAutomationService, WorkflowExecutionJobRunner
from app.logging import configure_logging
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.rate_limit import CrmMutationRateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.otel import get_fastapi_server_request_hook, setup_otel
from app.platform.security.policies import DbPolicyBackend, InMemoryPolicyBackend, set_policy_backend


configure_logging()
logger = logging.getLogger("app.lifecycle")
workflow_automation_service = WorkflowAutomationService()
workflow_execution_job_runner = WorkflowExecutionJobRunner()
_subscriptions_registered = False

_workflow_event_types = [
    "crm.lead.created",
    "crm.lead.updated",
    "crm.opportunity.stage_changed",
    "crm.opportunity.closed_won",
    "crm.opportunity.closed_lost",
    "crm.account.created",
    "crm.account.updated",
]

_billing_event_types = [
    "subscription.activated",
    "subscription.renewed",
]

def _on_system_started(event: InternalEvent) -> None:
    logger.info("system_event", extra={"event_name": event.name, "event_payload": event.payload})


@contextmanager
def _workflow_session_scope():
    override = app.dependency_overrides.get(get_db) if "app" in globals() else None
    if override is None:
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
        return

    generator = override()
    session = next(generator)
    try:
        yield session
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


def _on_crm_domain_event(event: InternalEvent) -> None:
    if not isinstance(event.payload, dict):
        return
    envelope: dict[str, Any] = event.payload
    settings = get_settings()
    try:
        with _workflow_session_scope() as session:
            queued_job_ids = workflow_automation_service.enqueue_for_event(session, envelope)
            if settings.auto_run_workflow_jobs or settings.auto_run_jobs:
                for job_id in queued_job_ids:
                    workflow_execution_job_runner.run_workflow_execution_job(session, job_id)
    except Exception as exc:
        logger.exception("workflow_auto_enqueue_failed", extra={"event_name": event.name, "error": str(exc)[:500]})


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _on_subscription_billing_event(event: InternalEvent) -> None:
    if not isinstance(event.payload, dict):
        return
    envelope: dict[str, Any] = event.payload

    subscription_id_raw = envelope.get("subscription_id")
    company_code = envelope.get("company_code")
    currency = envelope.get("currency")

    if not isinstance(subscription_id_raw, str) or not isinstance(company_code, str) or not isinstance(currency, str):
        return

    try:
        subscription_id = uuid.UUID(subscription_id_raw)
    except ValueError:
        return

    period_start = _parse_iso_date(envelope.get("period_start"))
    period_end = _parse_iso_date(envelope.get("period_end"))
    correlation_id = envelope.get("correlation_id") if isinstance(envelope.get("correlation_id"), str) else None

    try:
        with _workflow_session_scope() as session:
            billing_service.handle_subscription_billing_event(
                session,
                subscription_id=subscription_id,
                company_code=company_code,
                currency=currency,
                period_start=period_start,
                period_end=period_end,
                correlation_id=correlation_id,
            )
    except Exception as exc:
        logger.exception("billing_auto_invoice_failed", extra={"event_name": event.name, "error": str(exc)[:500]})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _subscriptions_registered
    if not _subscriptions_registered:
        event_bus.subscribe("system.started", _on_system_started)
        for event_name in _workflow_event_types:
            event_bus.subscribe(event_name, _on_crm_domain_event)
        for event_name in _billing_event_types:
            event_bus.subscribe(event_name, _on_subscription_billing_event)
        _subscriptions_registered = True
    event_bus.publish("system.started", {"service": "api"})
    yield


app = FastAPI(title="Nexa API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CrmMutationRateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.include_router(api_router)

settings = get_settings()
backend_choice = settings.authz_policy_backend.lower()
if backend_choice == "auto":
    backend_choice = "db" if settings.app_env.lower() in {"prod", "production"} else "inmemory"

if backend_choice == "db":
    set_policy_backend(DbPolicyBackend(default_allow=settings.authz_default_allow))
else:
    set_policy_backend(InMemoryPolicyBackend(default_allow=settings.authz_default_allow))

if settings.otel_enabled:
    setup_otel("api", True)

if not getattr(app, "_is_instrumented_by_opentelemetry", False):
    FastAPIInstrumentor().instrument_app(app, server_request_hook=get_fastapi_server_request_hook())
