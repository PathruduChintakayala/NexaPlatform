from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform.security.context import AuthContext
from app.platform.ledger.service import ledger_service


def seed_minimal_chart_of_accounts(
    session: Session,
    *,
    tenant_id: str,
    company_code: str,
    currency: str,
    actor_user_id: str = "system",
) -> None:
    ctx = AuthContext(user_id=actor_user_id, tenant_id=tenant_id, entity_scope=[company_code], is_super_admin=True)
    ledger_service.seed_chart_of_accounts(
        session,
        ctx,
        tenant_id=tenant_id,
        company_code=company_code,
        currency=currency,
    )
