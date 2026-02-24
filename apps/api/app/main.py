from contextlib import asynccontextmanager, contextmanager
import logging
from typing import Any

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.context import RequestContextMiddleware
from app.core.events import InternalEvent, event_bus
from app.core.database import SessionLocal, get_db
from app.crm.service import WorkflowAutomationService, WorkflowExecutionJobRunner
from app.logging import configure_logging
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.rate_limit import CrmMutationRateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.otel import get_fastapi_server_request_hook, setup_otel


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _subscriptions_registered
    if not _subscriptions_registered:
        event_bus.subscribe("system.started", _on_system_started)
        for event_name in _workflow_event_types:
            event_bus.subscribe(event_name, _on_crm_domain_event)
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
if settings.otel_enabled:
    setup_otel("api", True)
    FastAPIInstrumentor().instrument_app(app, server_request_hook=get_fastapi_server_request_hook())
