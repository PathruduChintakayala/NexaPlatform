from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.catalog.models import CatalogPricebook, CatalogPricebookItem, CatalogProduct
from app.business.catalog.repository import (
    CatalogPricebookItemRepository,
    CatalogPricebookRepository,
    CatalogProductRepository,
)
from app.business.catalog.schemas import (
    CatalogPriceRead,
    CatalogPricebookCreate,
    CatalogPricebookItemRead,
    CatalogPricebookItemUpsert,
    CatalogPricebookRead,
    CatalogProductCreate,
    CatalogProductRead,
)
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError


@dataclass(slots=True)
class CatalogService:
    product_repository: CatalogProductRepository = CatalogProductRepository()
    pricebook_repository: CatalogPricebookRepository = CatalogPricebookRepository()
    pricebook_item_repository: CatalogPricebookItemRepository = CatalogPricebookItemRepository()

    def create_product(self, session: Session, ctx: AuthContext, dto: CatalogProductCreate) -> CatalogProductRead:
        payload = dto.model_dump(mode="python")
        try:
            self.product_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        product = CatalogProduct(**payload)
        session.add(product)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="catalog product already exists")
        session.refresh(product)

        secured = self.product_repository.apply_read_security(CatalogProductRead.model_validate(product).model_dump(mode="python"), ctx)
        return CatalogProductRead.model_validate(secured)

    def list_products(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None = None,
    ) -> list[CatalogProductRead]:
        stmt: Select[tuple[CatalogProduct]] = select(CatalogProduct).where(CatalogProduct.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(CatalogProduct.company_code == company_code)

        stmt = self.product_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(CatalogProduct.sku.asc())).all()

        payload = [CatalogProductRead.model_validate(row).model_dump(mode="python") for row in rows]
        secured_rows = self.product_repository.apply_read_security_many(payload, ctx)
        return [CatalogProductRead.model_validate(item) for item in secured_rows]

    def create_pricebook(self, session: Session, ctx: AuthContext, dto: CatalogPricebookCreate) -> CatalogPricebookRead:
        payload = dto.model_dump(mode="python")
        try:
            self.pricebook_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        if dto.valid_from and dto.valid_to and dto.valid_to < dto.valid_from:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="valid_to must be on or after valid_from")

        if dto.is_default:
            existing_default = session.scalar(
                self.pricebook_repository.apply_scope_query(
                    select(CatalogPricebook).where(
                        and_(
                            CatalogPricebook.tenant_id == dto.tenant_id,
                            CatalogPricebook.company_code == dto.company_code,
                            CatalogPricebook.currency == dto.currency,
                            CatalogPricebook.is_default.is_(True),
                            CatalogPricebook.is_active.is_(True),
                        )
                    ),
                    ctx,
                )
            )
            if existing_default is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="default pricebook already exists")

        pricebook = CatalogPricebook(**payload)
        session.add(pricebook)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="catalog pricebook already exists")
        session.refresh(pricebook)

        secured = self.pricebook_repository.apply_read_security(CatalogPricebookRead.model_validate(pricebook).model_dump(mode="python"), ctx)
        return CatalogPricebookRead.model_validate(secured)

    def list_pricebooks(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None = None,
        currency: str | None = None,
    ) -> list[CatalogPricebookRead]:
        stmt: Select[tuple[CatalogPricebook]] = select(CatalogPricebook).where(CatalogPricebook.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(CatalogPricebook.company_code == company_code)
        if currency is not None:
            stmt = stmt.where(CatalogPricebook.currency == currency)

        stmt = self.pricebook_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(CatalogPricebook.name.asc())).all()

        payload = [CatalogPricebookRead.model_validate(row).model_dump(mode="python") for row in rows]
        secured_rows = self.pricebook_repository.apply_read_security_many(payload, ctx)
        return [CatalogPricebookRead.model_validate(item) for item in secured_rows]

    def upsert_pricebook_item(
        self,
        session: Session,
        ctx: AuthContext,
        dto: CatalogPricebookItemUpsert,
    ) -> CatalogPricebookItemRead:
        payload = dto.model_dump(mode="python")

        pricebook = session.scalar(
            self.pricebook_repository.apply_scope_query(
                select(CatalogPricebook).where(CatalogPricebook.id == dto.pricebook_id),
                ctx,
            )
        )
        if pricebook is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricebook not found")

        product = session.scalar(
            self.product_repository.apply_scope_query(
                select(CatalogProduct).where(CatalogProduct.id == dto.product_id),
                ctx,
            )
        )
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")

        if product.tenant_id != pricebook.tenant_id or product.company_code != pricebook.company_code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="product and pricebook scope mismatch")

        try:
            self.pricebook_item_repository.validate_write_security(
                {
                    **payload,
                    "company_code": pricebook.company_code,
                    "region_code": pricebook.region_code,
                },
                ctx,
                action="upsert",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        existing = session.scalar(
            select(CatalogPricebookItem).where(
                and_(
                    CatalogPricebookItem.pricebook_id == dto.pricebook_id,
                    CatalogPricebookItem.product_id == dto.product_id,
                    CatalogPricebookItem.billing_period == dto.billing_period,
                    CatalogPricebookItem.currency == dto.currency,
                )
            )
        )

        if existing is None:
            existing = CatalogPricebookItem(**payload)
            session.add(existing)
        else:
            existing.unit_price = dto.unit_price
            existing.is_active = dto.is_active

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="catalog pricebook item conflict")
        session.refresh(existing)

        secured = self.pricebook_item_repository.apply_read_security(
            CatalogPricebookItemRead.model_validate(existing).model_dump(mode="python"),
            ctx,
        )
        return CatalogPricebookItemRead.model_validate(secured)

    def get_price(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str,
        sku: str,
        currency: str,
        billing_period: str,
        at_date: date | None,
    ) -> CatalogPriceRead:
        target_date = at_date or date.today()

        stmt = (
            select(CatalogPricebookItem, CatalogPricebook, CatalogProduct)
            .join(CatalogPricebook, CatalogPricebook.id == CatalogPricebookItem.pricebook_id)
            .join(CatalogProduct, CatalogProduct.id == CatalogPricebookItem.product_id)
            .where(
                and_(
                    CatalogProduct.tenant_id == tenant_id,
                    CatalogProduct.company_code == company_code,
                    CatalogProduct.sku == sku,
                    CatalogProduct.is_active.is_(True),
                    CatalogPricebook.tenant_id == tenant_id,
                    CatalogPricebook.company_code == company_code,
                    CatalogPricebook.currency == currency,
                    CatalogPricebook.is_active.is_(True),
                    CatalogPricebookItem.currency == currency,
                    CatalogPricebookItem.billing_period == billing_period,
                    CatalogPricebookItem.is_active.is_(True),
                )
            )
            .order_by(CatalogPricebook.is_default.desc(), CatalogPricebook.created_at.asc())
        )

        stmt = self.pricebook_repository.apply_scope_query(stmt, ctx)
        rows = session.execute(stmt).all()

        for item, pricebook, product in rows:
            if pricebook.valid_from and target_date < pricebook.valid_from:
                continue
            if pricebook.valid_to and target_date > pricebook.valid_to:
                continue

            try:
                self.product_repository.validate_read_scope(
                    ctx,
                    company_code=product.company_code,
                    region_code=product.region_code,
                    action="read",
                )
            except AuthorizationError as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

            secured = self.pricebook_item_repository.apply_read_security(
                {
                    "tenant_id": product.tenant_id,
                    "company_code": product.company_code,
                    "sku": product.sku,
                    "product_id": product.id,
                    "pricebook_id": pricebook.id,
                    "currency": item.currency,
                    "billing_period": item.billing_period,
                    "unit_price": item.unit_price,
                    "valid_from": pricebook.valid_from,
                    "valid_to": pricebook.valid_to,
                },
                ctx,
            )
            return CatalogPriceRead.model_validate(secured)

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="price not found")

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
        existing = session.scalar(
            self.pricebook_repository.apply_scope_query(
                select(CatalogPricebook).where(
                    and_(
                        CatalogPricebook.tenant_id == tenant_id,
                        CatalogPricebook.company_code == company_code,
                        CatalogPricebook.currency == currency,
                        CatalogPricebook.is_default.is_(True),
                        CatalogPricebook.is_active.is_(True),
                    )
                ),
                ctx,
            )
        )
        if existing is not None:
            return CatalogPricebookRead.model_validate(existing)

        return self.create_pricebook(
            session,
            ctx,
            CatalogPricebookCreate(
                tenant_id=tenant_id,
                company_code=company_code,
                region_code=region_code,
                name=f"Default {currency}",
                currency=currency,
                is_default=True,
                is_active=True,
            ),
        )


catalog_service = CatalogService()
