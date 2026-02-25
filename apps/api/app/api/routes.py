from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.auth import AuthUser, get_current_user
from app.core.config import get_settings
from app.metrics import generate_metrics_payload, metrics_content_type
from app.business.catalog.api import router as catalog_router
from app.business.billing.api import router as billing_router
from app.business.payments.api import router as payments_router
from app.business.revenue.api import router as revenue_router
from app.business.subscription.api import router as subscription_router
from app.business.reporting.finance.api import router as reporting_finance_router
from app.authz.api import admin_router
from app.platform.ledger.api import router as ledger_router
from app.crm.api import (
    activities_router,
    audit_router,
    attachments_router,
    contacts_router,
    custom_fields_router,
    import_export_router,
    jobs_router,
    leads_router,
    notes_router,
    opportunities_router,
    pipelines_router,
    search_router,
    workflows_router,
    router as crm_accounts_router,
)

router = APIRouter()
router.include_router(admin_router)
router.include_router(catalog_router)
router.include_router(billing_router)
router.include_router(payments_router)
router.include_router(revenue_router)
router.include_router(subscription_router)
router.include_router(reporting_finance_router)
router.include_router(ledger_router)
router.include_router(crm_accounts_router)
router.include_router(contacts_router)
router.include_router(leads_router)
router.include_router(pipelines_router)
router.include_router(opportunities_router)
router.include_router(activities_router)
router.include_router(audit_router)
router.include_router(notes_router)
router.include_router(attachments_router)
router.include_router(search_router)
router.include_router(custom_fields_router)
router.include_router(workflows_router)
router.include_router(import_export_router)
router.include_router(jobs_router)


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/me", tags=["auth"])
async def me(user: AuthUser = Depends(get_current_user)) -> dict[str, str | list[str]]:
    return {
        "sub": user.sub,
        "roles": user.roles,
    }


@router.get("/metrics", tags=["system"])
def metrics(user: AuthUser = Depends(get_current_user)) -> Response:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if "system.metrics.read" not in user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: system.metrics.read")
    return Response(content=generate_metrics_payload(), media_type=metrics_content_type())
