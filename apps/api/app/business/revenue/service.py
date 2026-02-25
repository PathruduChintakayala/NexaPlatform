from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import events
from app.business.catalog.models import CatalogPricebook, CatalogPricebookItem
from app.business.revenue.models import RevenueContract, RevenueOrder, RevenueOrderLine, RevenueQuote, RevenueQuoteLine
from app.business.revenue.repository import (
    RevenueContractRepository,
    RevenueOrderLineRepository,
    RevenueOrderRepository,
    RevenueQuoteLineRepository,
    RevenueQuoteRepository,
)
from app.business.revenue.schemas import (
    RevenueContractRead,
    RevenueOrderRead,
    RevenueQuoteCreate,
    RevenueQuoteLineCreate,
    RevenueQuoteLineRead,
    RevenueQuoteRead,
    RevenueOrderLineRead,
)
from app.core.config import get_settings
from app.platform.ledger.models import LedgerAccount
from app.platform.ledger.schemas import JournalEntryPostRequest, JournalLineInput
from app.platform.ledger.service import ledger_service
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError


VALID_QUOTE_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SENT"},
    "SENT": {"ACCEPTED", "REJECTED", "EXPIRED"},
    "ACCEPTED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
}

VALID_ORDER_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"FULFILLED", "CANCELLED"},
    "FULFILLED": set(),
    "CANCELLED": set(),
}


@dataclass(slots=True)
class RevenueService:
    quote_repository: RevenueQuoteRepository = RevenueQuoteRepository()
    quote_line_repository: RevenueQuoteLineRepository = RevenueQuoteLineRepository()
    order_repository: RevenueOrderRepository = RevenueOrderRepository()
    order_line_repository: RevenueOrderLineRepository = RevenueOrderLineRepository()
    contract_repository: RevenueContractRepository = RevenueContractRepository()

    def create_quote(self, session: Session, ctx: AuthContext, payload: RevenueQuoteCreate) -> RevenueQuoteRead:
        data = payload.model_dump(mode="python")
        data["created_by"] = ctx.user_id
        data["quote_number"] = self._next_number(session, RevenueQuote, data["company_code"], "Q")
        data.setdefault("subtotal", Decimal("0"))
        data.setdefault("total", Decimal("0"))
        data.setdefault("status", "DRAFT")

        try:
            self.quote_repository.validate_write_security(data, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        quote = RevenueQuote(**data)
        session.add(quote)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="revenue quote already exists")
        session.refresh(quote)
        return self._to_quote_read(quote, ctx)

    def add_quote_line(
        self,
        session: Session,
        ctx: AuthContext,
        quote_id: uuid.UUID,
        payload: RevenueQuoteLineCreate,
    ) -> RevenueQuoteLineRead:
        quote = self._get_quote(session, ctx, quote_id, with_lines=False)
        if quote.status != "DRAFT":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="quote is not editable")

        item = session.scalar(
            select(CatalogPricebookItem)
            .join(CatalogPricebook, CatalogPricebook.id == CatalogPricebookItem.pricebook_id)
            .where(
                and_(
                    CatalogPricebookItem.id == payload.pricebook_item_id,
                    CatalogPricebook.tenant_id == quote.tenant_id,
                    CatalogPricebook.company_code == quote.company_code,
                    CatalogPricebook.is_active.is_(True),
                    CatalogPricebookItem.is_active.is_(True),
                )
            )
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricebook item not found")
        if item.currency != quote.currency:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="currency mismatch")

        line_total = self._q(payload.quantity * item.unit_price)
        line_payload = {
            "quote_id": quote.id,
            "product_id": payload.product_id,
            "pricebook_item_id": payload.pricebook_item_id,
            "description": payload.description,
            "quantity": self._q(payload.quantity),
            "unit_price": self._q(item.unit_price),
            "line_total": line_total,
        }
        try:
            self.quote_line_repository.validate_write_security(
                line_payload,
                ctx,
                existing_scope={"company_code": quote.company_code, "region_code": quote.region_code},
                action="create",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        line = RevenueQuoteLine(**line_payload)
        session.add(line)
        session.flush()

        self._recompute_quote_totals(session, quote)
        session.commit()
        session.refresh(line)
        return self._to_quote_line_read(line, ctx)

    def send_quote(self, session: Session, ctx: AuthContext, quote_id: uuid.UUID) -> RevenueQuoteRead:
        quote = self._get_quote(session, ctx, quote_id, with_lines=True)
        self._transition_quote_status(session, ctx, quote, "SENT")
        return self._to_quote_read(quote, ctx)

    def accept_quote(self, session: Session, ctx: AuthContext, quote_id: uuid.UUID) -> RevenueQuoteRead:
        quote = self._get_quote(session, ctx, quote_id, with_lines=True)
        self._transition_quote_status(session, ctx, quote, "ACCEPTED")
        return self._to_quote_read(quote, ctx)

    def create_order_from_quote(self, session: Session, ctx: AuthContext, quote_id: uuid.UUID) -> RevenueOrderRead:
        quote = self._get_quote(session, ctx, quote_id, with_lines=True)
        if quote.status != "ACCEPTED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="quote must be ACCEPTED")
        if not quote.lines:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="quote has no lines")

        self._validate_quote_totals(quote)

        order_payload = {
            "tenant_id": quote.tenant_id,
            "company_code": quote.company_code,
            "region_code": quote.region_code,
            "order_number": self._next_number(session, RevenueOrder, quote.company_code, "O"),
            "quote_id": quote.id,
            "currency": quote.currency,
            "status": "DRAFT",
            "subtotal": quote.subtotal,
            "discount_total": quote.discount_total,
            "tax_total": quote.tax_total,
            "total": quote.total,
            "created_by": ctx.user_id,
        }
        try:
            self.order_repository.validate_write_security(order_payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        order = RevenueOrder(**order_payload)
        session.add(order)
        session.flush()

        for quote_line in quote.lines:
            line_payload = {
                "order_id": order.id,
                "product_id": quote_line.product_id,
                "pricebook_item_id": quote_line.pricebook_item_id,
                "quantity": quote_line.quantity,
                "unit_price": quote_line.unit_price,
                "line_total": quote_line.line_total,
                "service_start": None,
                "service_end": None,
            }
            try:
                self.order_line_repository.validate_write_security(
                    line_payload,
                    ctx,
                    existing_scope={"company_code": quote.company_code, "region_code": quote.region_code},
                    action="create",
                )
            except (ForbiddenFieldError, AuthorizationError) as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            session.add(RevenueOrderLine(**line_payload))

        session.commit()
        order = self._get_order(session, ctx, order.id, with_lines=True)
        return self._to_order_read(order, ctx)

    def confirm_order(self, session: Session, ctx: AuthContext, order_id: uuid.UUID) -> RevenueOrderRead:
        order = self._get_order(session, ctx, order_id, with_lines=True)
        self._transition_order_status(session, ctx, order, "CONFIRMED")

        events.publish(
            {
                "event_type": "revenue.order.confirmed",
                "tenant_id": order.tenant_id,
                "company_code": order.company_code,
                "order_id": str(order.id),
                "total": str(order.total),
            }
        )

        settings = get_settings()
        if settings.revenue_post_to_ledger:
            self._post_order_to_ledger(session, ctx, order)

        return self._to_order_read(order, ctx)

    def create_contract_from_order(self, session: Session, ctx: AuthContext, order_id: uuid.UUID) -> RevenueContractRead:
        order = self._get_order(session, ctx, order_id, with_lines=True)
        if order.status != "CONFIRMED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="order must be CONFIRMED")

        existing = session.scalar(
            self.contract_repository.apply_scope_query(
                select(RevenueContract).where(RevenueContract.order_id == order.id),
                ctx,
            )
        )
        if existing is not None:
            return self._to_contract_read(existing, ctx)

        payload = {
            "tenant_id": order.tenant_id,
            "company_code": order.company_code,
            "region_code": order.region_code,
            "contract_number": self._next_number(session, RevenueContract, order.company_code, "C"),
            "order_id": order.id,
            "status": "ACTIVE",
            "start_date": date.today(),
            "end_date": None,
        }
        try:
            self.contract_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        contract = RevenueContract(**payload)
        session.add(contract)
        session.commit()
        session.refresh(contract)
        return self._to_contract_read(contract, ctx)

    def list_quotes(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[RevenueQuoteRead]:
        stmt: Select[tuple[RevenueQuote]] = (
            select(RevenueQuote)
            .where(RevenueQuote.tenant_id == tenant_id)
            .options(selectinload(RevenueQuote.lines))
        )
        if company_code is not None:
            stmt = stmt.where(RevenueQuote.company_code == company_code)
        stmt = self.quote_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(RevenueQuote.created_at.desc())).all()
        return [self._to_quote_read(row, ctx) for row in rows]

    def get_quote(self, session: Session, ctx: AuthContext, quote_id: uuid.UUID) -> RevenueQuoteRead:
        return self._to_quote_read(self._get_quote(session, ctx, quote_id, with_lines=True), ctx)

    def list_orders(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[RevenueOrderRead]:
        stmt: Select[tuple[RevenueOrder]] = (
            select(RevenueOrder)
            .where(RevenueOrder.tenant_id == tenant_id)
            .options(selectinload(RevenueOrder.lines))
        )
        if company_code is not None:
            stmt = stmt.where(RevenueOrder.company_code == company_code)
        stmt = self.order_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(RevenueOrder.created_at.desc())).all()
        return [self._to_order_read(row, ctx) for row in rows]

    def get_order(self, session: Session, ctx: AuthContext, order_id: uuid.UUID) -> RevenueOrderRead:
        return self._to_order_read(self._get_order(session, ctx, order_id, with_lines=True), ctx)

    def list_contracts(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[RevenueContractRead]:
        stmt: Select[tuple[RevenueContract]] = select(RevenueContract).where(RevenueContract.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(RevenueContract.company_code == company_code)
        stmt = self.contract_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(RevenueContract.created_at.desc())).all()
        return [self._to_contract_read(row, ctx) for row in rows]

    def get_contract(self, session: Session, ctx: AuthContext, contract_id: uuid.UUID) -> RevenueContractRead:
        contract = session.scalar(
            self.contract_repository.apply_scope_query(
                select(RevenueContract).where(RevenueContract.id == contract_id),
                ctx,
            )
        )
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract not found")
        return self._to_contract_read(contract, ctx)

    def _transition_quote_status(self, session: Session, ctx: AuthContext, quote: RevenueQuote, target: str) -> None:
        allowed = VALID_QUOTE_TRANSITIONS.get(quote.status, set())
        if target not in allowed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"invalid quote transition {quote.status} -> {target}")

        self._validate_quote_totals(quote)
        write_payload = {
            "status": target,
            "subtotal": quote.subtotal,
            "discount_total": quote.discount_total,
            "tax_total": quote.tax_total,
            "total": quote.total,
        }
        try:
            self.quote_repository.validate_write_security(
                write_payload,
                ctx,
                existing_scope={"company_code": quote.company_code, "region_code": quote.region_code},
                action="update",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        quote.status = target
        session.add(quote)
        session.commit()
        session.refresh(quote)

    def _transition_order_status(self, session: Session, ctx: AuthContext, order: RevenueOrder, target: str) -> None:
        allowed = VALID_ORDER_TRANSITIONS.get(order.status, set())
        if target not in allowed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"invalid order transition {order.status} -> {target}")

        self._validate_order_totals(order)
        write_payload = {
            "status": target,
            "subtotal": order.subtotal,
            "discount_total": order.discount_total,
            "tax_total": order.tax_total,
            "total": order.total,
        }
        try:
            self.order_repository.validate_write_security(
                write_payload,
                ctx,
                existing_scope={"company_code": order.company_code, "region_code": order.region_code},
                action="update",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        order.status = target
        session.add(order)
        session.commit()
        session.refresh(order)

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.000001"))

    def _recompute_quote_totals(self, session: Session, quote: RevenueQuote) -> None:
        subtotal = session.scalar(
            select(func.coalesce(func.sum(RevenueQuoteLine.line_total), 0)).where(RevenueQuoteLine.quote_id == quote.id)
        )
        quote.subtotal = self._q(Decimal(subtotal))
        quote.total = self._q(quote.subtotal - quote.discount_total + quote.tax_total)
        session.add(quote)

    def _validate_quote_totals(self, quote: RevenueQuote) -> None:
        subtotal = self._q(sum((Decimal(line.line_total) for line in quote.lines), start=Decimal("0")))
        if subtotal != self._q(quote.subtotal):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="quote subtotal mismatch")
        total = self._q(Decimal(quote.subtotal) - Decimal(quote.discount_total) + Decimal(quote.tax_total))
        if total != self._q(quote.total):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="quote total mismatch")

    def _validate_order_totals(self, order: RevenueOrder) -> None:
        subtotal = self._q(sum((Decimal(line.line_total) for line in order.lines), start=Decimal("0")))
        if subtotal != self._q(order.subtotal):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="order subtotal mismatch")
        total = self._q(Decimal(order.subtotal) - Decimal(order.discount_total) + Decimal(order.tax_total))
        if total != self._q(order.total):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="order total mismatch")

    def _post_order_to_ledger(self, session: Session, ctx: AuthContext, order: RevenueOrder) -> None:
        ar_account = session.scalar(
            select(LedgerAccount).where(
                and_(
                    LedgerAccount.tenant_id == order.tenant_id,
                    LedgerAccount.company_code == order.company_code,
                    LedgerAccount.code == "1100",
                    LedgerAccount.is_active.is_(True),
                )
            )
        )
        revenue_account = session.scalar(
            select(LedgerAccount).where(
                and_(
                    LedgerAccount.tenant_id == order.tenant_id,
                    LedgerAccount.company_code == order.company_code,
                    LedgerAccount.code == "4000",
                    LedgerAccount.is_active.is_(True),
                )
            )
        )
        if ar_account is None or revenue_account is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="required ledger accounts missing")

        request = JournalEntryPostRequest(
            tenant_id=order.tenant_id,
            company_code=order.company_code,
            entry_date=date.today(),
            description=f"Revenue booking for order {order.order_number}",
            source_module="revenue",
            source_type="order",
            source_id=str(order.id),
            created_by=ctx.user_id,
            lines=[
                JournalLineInput(
                    account_id=ar_account.id,
                    debit_amount=order.total,
                    credit_amount=Decimal("0"),
                    currency=order.currency,
                    fx_rate_to_company_base=Decimal("1"),
                    memo="AR booking",
                ),
                JournalLineInput(
                    account_id=revenue_account.id,
                    debit_amount=Decimal("0"),
                    credit_amount=order.total,
                    currency=order.currency,
                    fx_rate_to_company_base=Decimal("1"),
                    memo="Revenue booking",
                ),
            ],
        )
        ledger_service.post_entry(session, ctx, request)

    def _get_quote(self, session: Session, ctx: AuthContext, quote_id: uuid.UUID, *, with_lines: bool) -> RevenueQuote:
        stmt = select(RevenueQuote).where(RevenueQuote.id == quote_id)
        if with_lines:
            stmt = stmt.options(selectinload(RevenueQuote.lines))
        quote = session.scalar(self.quote_repository.apply_scope_query(stmt, ctx))
        if quote is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quote not found")
        return quote

    def _get_order(self, session: Session, ctx: AuthContext, order_id: uuid.UUID, *, with_lines: bool) -> RevenueOrder:
        stmt = select(RevenueOrder).where(RevenueOrder.id == order_id)
        if with_lines:
            stmt = stmt.options(selectinload(RevenueOrder.lines))
        order = session.scalar(self.order_repository.apply_scope_query(stmt, ctx))
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
        return order

    def _to_quote_line_read(self, line: RevenueQuoteLine, ctx: AuthContext) -> RevenueQuoteLineRead:
        payload = {
            "id": line.id,
            "quote_id": line.quote_id,
            "product_id": line.product_id,
            "pricebook_item_id": line.pricebook_item_id,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "line_total": line.line_total,
        }
        secured = self.quote_line_repository.apply_read_security(payload, ctx)
        return RevenueQuoteLineRead.model_validate(secured)

    def _to_quote_read(self, quote: RevenueQuote, ctx: AuthContext) -> RevenueQuoteRead:
        payload = {
            "id": quote.id,
            "tenant_id": quote.tenant_id,
            "company_code": quote.company_code,
            "region_code": quote.region_code,
            "quote_number": quote.quote_number,
            "account_id": quote.account_id,
            "currency": quote.currency,
            "status": quote.status,
            "valid_until": quote.valid_until,
            "subtotal": quote.subtotal,
            "discount_total": quote.discount_total,
            "tax_total": quote.tax_total,
            "total": quote.total,
            "created_by": quote.created_by,
            "created_at": quote.created_at,
            "updated_at": quote.updated_at,
            "lines": [
                {
                    "id": line.id,
                    "quote_id": line.quote_id,
                    "product_id": line.product_id,
                    "pricebook_item_id": line.pricebook_item_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "line_total": line.line_total,
                }
                for line in quote.lines
            ],
        }
        secured = self.quote_repository.apply_read_security(payload, ctx)
        secured_lines = self.quote_line_repository.apply_read_security_many(secured.get("lines", []), ctx)
        secured["lines"] = [RevenueQuoteLineRead.model_validate(item) for item in secured_lines]
        return RevenueQuoteRead.model_validate(secured)

    def _to_order_read(self, order: RevenueOrder, ctx: AuthContext) -> RevenueOrderRead:
        payload = {
            "id": order.id,
            "tenant_id": order.tenant_id,
            "company_code": order.company_code,
            "region_code": order.region_code,
            "order_number": order.order_number,
            "quote_id": order.quote_id,
            "currency": order.currency,
            "status": order.status,
            "subtotal": order.subtotal,
            "discount_total": order.discount_total,
            "tax_total": order.tax_total,
            "total": order.total,
            "created_by": order.created_by,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "lines": [
                {
                    "id": line.id,
                    "order_id": line.order_id,
                    "product_id": line.product_id,
                    "pricebook_item_id": line.pricebook_item_id,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "line_total": line.line_total,
                    "service_start": line.service_start,
                    "service_end": line.service_end,
                }
                for line in order.lines
            ],
        }
        secured = self.order_repository.apply_read_security(payload, ctx)
        secured_lines = self.order_line_repository.apply_read_security_many(secured.get("lines", []), ctx)
        secured["lines"] = [RevenueOrderLineRead.model_validate(item) for item in secured_lines]
        return RevenueOrderRead.model_validate(secured)

    def _to_contract_read(self, contract: RevenueContract, ctx: AuthContext) -> RevenueContractRead:
        payload = {
            "id": contract.id,
            "tenant_id": contract.tenant_id,
            "company_code": contract.company_code,
            "region_code": contract.region_code,
            "contract_number": contract.contract_number,
            "order_id": contract.order_id,
            "status": contract.status,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "created_at": contract.created_at,
        }
        secured = self.contract_repository.apply_read_security(payload, ctx)
        return RevenueContractRead.model_validate(secured)

    def _next_number(self, session: Session, model: type[RevenueQuote] | type[RevenueOrder] | type[RevenueContract], company_code: str, prefix: str) -> str:
        counter = session.scalar(select(func.count()).select_from(model).where(model.company_code == company_code)) or 0
        return f"{prefix}-{company_code}-{counter + 1:05d}"


revenue_service = RevenueService()
