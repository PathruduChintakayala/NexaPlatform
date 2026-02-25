from __future__ import annotations

from app.business.subscription.schemas import PlanCreate, PlanRead
from app.business.subscription.service import SubscriptionService
from app.platform.security.context import AuthContext
from sqlalchemy.orm import Session


class SubscriptionSeedHelper:
    def __init__(self, service: SubscriptionService) -> None:
        self._service = service

    def ensure_sample_plan(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str,
        currency: str,
        billing_period: str = "MONTHLY",
    ) -> PlanRead:
        plans = self._service.list_plans(session, ctx, tenant_id=tenant_id, company_code=company_code)
        if plans:
            return plans[0]
        return self._service.create_plan(
            session,
            ctx,
            PlanCreate(
                tenant_id=tenant_id,
                company_code=company_code,
                name=f"Sample {company_code}",
                code=f"SAMPLE-{company_code}",
                currency=currency,
                billing_period=billing_period,
            ),
        )


subscription_seed_helper = SubscriptionSeedHelper(SubscriptionService())
