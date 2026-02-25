from __future__ import annotations

from app.business.catalog.schemas import CatalogPricebookCreate, CatalogPricebookRead
from app.business.catalog.service import CatalogService
from app.platform.security.context import AuthContext
from sqlalchemy.orm import Session


class CatalogSeedHelper:
    def __init__(self, service: CatalogService) -> None:
        self._service = service

    def ensure_default_pricebook(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str,
        currency: str,
        region_code: str | None = None,
    ) -> CatalogPricebookRead:
        return self._service.ensure_default_pricebook(
            session,
            ctx,
            tenant_id=tenant_id,
            company_code=company_code,
            currency=currency,
            region_code=region_code,
        )


catalog_seed_helper = CatalogSeedHelper(CatalogService())
