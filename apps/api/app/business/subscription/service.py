from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import events
from app.business.catalog.models import CatalogPricebook, CatalogPricebookItem
from app.business.revenue.models import RevenueContract, RevenueOrder, RevenueOrderLine
from app.business.subscription.models import (
    Subscription,
    SubscriptionChange,
    SubscriptionItem,
    SubscriptionPlan,
    SubscriptionPlanItem,
)
from app.business.subscription.repository import (
    PlanItemRepository,
    PlanRepository,
    SubscriptionChangeRepository,
    SubscriptionItemRepository,
    SubscriptionRepository,
)
from app.business.subscription.schemas import (
    ActivateSubscriptionRequest,
    CancelSubscriptionRequest,
    ChangeQuantityRequest,
    CreateSubscriptionFromContractRequest,
    PlanCreate,
    PlanItemCreate,
    PlanItemRead,
    PlanRead,
    ResumeSubscriptionRequest,
    SubscriptionChangeRead,
    SubscriptionRead,
    SuspendSubscriptionRequest,
)
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError


VALID_SUBSCRIPTION_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"SUSPENDED", "CANCELLED", "EXPIRED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED"},
    "CANCELLED": set(),
    "EXPIRED": set(),
}


@dataclass(slots=True)
class SubscriptionService:
    plan_repository: PlanRepository = PlanRepository()
    plan_item_repository: PlanItemRepository = PlanItemRepository()
    subscription_repository: SubscriptionRepository = SubscriptionRepository()
    subscription_item_repository: SubscriptionItemRepository = SubscriptionItemRepository()
    subscription_change_repository: SubscriptionChangeRepository = SubscriptionChangeRepository()

    def create_plan(self, session: Session, ctx: AuthContext, payload: PlanCreate) -> PlanRead:
        data = payload.model_dump(mode="python")
        try:
            self.plan_repository.validate_write_security(data, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        plan = SubscriptionPlan(**data)
        session.add(plan)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="subscription plan already exists")
        session.refresh(plan)
        return self._to_plan_read(plan, ctx)

    def add_plan_item(self, session: Session, ctx: AuthContext, plan_id: uuid.UUID, payload: PlanItemCreate) -> PlanItemRead:
        plan = self._get_plan(session, ctx, plan_id, with_items=False)

        item = session.scalar(
            select(CatalogPricebookItem)
            .join(CatalogPricebook, CatalogPricebook.id == CatalogPricebookItem.pricebook_id)
            .where(
                and_(
                    CatalogPricebookItem.id == payload.pricebook_item_id,
                    CatalogPricebook.tenant_id == plan.tenant_id,
                    CatalogPricebook.company_code == plan.company_code,
                    CatalogPricebook.is_active.is_(True),
                    CatalogPricebookItem.is_active.is_(True),
                )
            )
        )
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pricebook item not found")
        if item.currency != plan.currency:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="currency mismatch")

        line_payload = {
            "plan_id": plan.id,
            "product_id": payload.product_id,
            "pricebook_item_id": payload.pricebook_item_id,
            "quantity_default": self._q(payload.quantity_default),
            "unit_price_snapshot": self._q(item.unit_price),
        }
        try:
            self.plan_item_repository.validate_write_security(
                line_payload,
                ctx,
                existing_scope={"company_code": plan.company_code, "region_code": plan.region_code},
                action="create",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        plan_item = SubscriptionPlanItem(**line_payload)
        session.add(plan_item)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan item already exists")
        session.refresh(plan_item)
        return self._to_plan_item_read(plan_item, ctx)

    def create_subscription_from_contract(
        self,
        session: Session,
        ctx: AuthContext,
        contract_id: uuid.UUID,
        payload: CreateSubscriptionFromContractRequest,
    ) -> SubscriptionRead:
        contract = session.scalar(
            self.subscription_repository.apply_scope_query(
                select(RevenueContract).where(RevenueContract.id == contract_id),
                ctx,
            )
        )
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract not found")

        order = session.scalar(
            select(RevenueOrder)
            .where(RevenueOrder.id == contract.order_id)
            .options(selectinload(RevenueOrder.lines))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contract order not found")

        plan = None
        if payload.plan_id is not None:
            plan = self._get_plan(session, ctx, payload.plan_id, with_items=True)
            if plan.currency != order.currency:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="currency mismatch")

        renewal_billing_period = payload.renewal_billing_period or (plan.billing_period if plan is not None else "MONTHLY")
        sub_payload = {
            "tenant_id": contract.tenant_id,
            "company_code": contract.company_code,
            "region_code": contract.region_code,
            "subscription_number": self._next_number(session, Subscription, contract.company_code, "S"),
            "contract_id": contract.id,
            "account_id": payload.account_id,
            "currency": order.currency,
            "status": "DRAFT",
            "start_date": payload.start_date,
            "current_period_start": None,
            "current_period_end": None,
            "auto_renew": payload.auto_renew,
            "renewal_term_count": payload.renewal_term_count,
            "renewal_billing_period": renewal_billing_period,
        }

        try:
            self.subscription_repository.validate_write_security(sub_payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        subscription = Subscription(**sub_payload)
        session.add(subscription)
        session.flush()

        source_items = self._resolve_source_items(order.lines, plan.items if plan is not None else None)
        for source in source_items:
            item_payload = {
                "subscription_id": subscription.id,
                "product_id": source["product_id"],
                "pricebook_item_id": source["pricebook_item_id"],
                "quantity": self._q(source["quantity"]),
                "unit_price_snapshot": self._q(source["unit_price_snapshot"]),
            }
            try:
                self.subscription_item_repository.validate_write_security(
                    item_payload,
                    ctx,
                    existing_scope={"company_code": subscription.company_code, "region_code": subscription.region_code},
                    action="create",
                )
            except (ForbiddenFieldError, AuthorizationError) as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            session.add(SubscriptionItem(**item_payload))

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="subscription creation conflict")

        return self.get_subscription(session, ctx, subscription.id)

    def activate_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        payload: ActivateSubscriptionRequest,
    ) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        self._assert_transition(subscription.status, "ACTIVE")

        period_start = payload.start_date or subscription.start_date or date.today()
        period_end = self._calculate_period_end(
            period_start,
            subscription.renewal_billing_period,
            subscription.renewal_term_count,
        )

        write_payload = {
            "status": "ACTIVE",
            "start_date": period_start,
            "current_period_start": period_start,
            "current_period_end": period_end,
        }
        self._validate_subscription_write(write_payload, subscription, ctx)

        subscription.status = "ACTIVE"
        subscription.start_date = period_start
        subscription.current_period_start = period_start
        subscription.current_period_end = period_end
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        self._emit_subscription_event("subscription.activated", subscription, ctx)
        self._record_change(session, ctx, subscription, "UPGRADE", period_start, {"action": "activate"}, commit=True)
        return self._to_subscription_read(subscription, ctx)

    def suspend_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        payload: SuspendSubscriptionRequest,
    ) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        self._assert_transition(subscription.status, "SUSPENDED")
        self._validate_subscription_write({"status": "SUSPENDED"}, subscription, ctx)

        subscription.status = "SUSPENDED"
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        self._record_change(session, ctx, subscription, "SUSPEND", payload.effective_date, None, commit=True)
        return self._to_subscription_read(subscription, ctx)

    def resume_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        payload: ResumeSubscriptionRequest,
    ) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        self._assert_transition(subscription.status, "ACTIVE")
        self._validate_subscription_write({"status": "ACTIVE"}, subscription, ctx)

        subscription.status = "ACTIVE"
        if subscription.current_period_start is None:
            subscription.current_period_start = payload.effective_date
        if subscription.current_period_end is None:
            subscription.current_period_end = self._calculate_period_end(
                subscription.current_period_start,
                subscription.renewal_billing_period,
                subscription.renewal_term_count,
            )
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        self._record_change(session, ctx, subscription, "RESUME", payload.effective_date, None, commit=True)
        return self._to_subscription_read(subscription, ctx)

    def cancel_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        payload: CancelSubscriptionRequest,
    ) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        self._assert_transition(subscription.status, "CANCELLED")
        self._validate_subscription_write({"status": "CANCELLED"}, subscription, ctx)

        subscription.status = "CANCELLED"
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        self._record_change(
            session,
            ctx,
            subscription,
            "CANCEL",
            payload.effective_date,
            {"reason": payload.reason},
            commit=True,
        )
        self._emit_subscription_event("subscription.cancelled", subscription, ctx)
        return self._to_subscription_read(subscription, ctx)

    def renew_subscription(self, session: Session, ctx: AuthContext, subscription_id: uuid.UUID) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        if subscription.status != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="subscription must be ACTIVE")
        if not subscription.auto_renew:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="subscription auto_renew is disabled")
        if subscription.current_period_start is None or subscription.current_period_end is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="subscription period is not set")

        new_start = subscription.current_period_end + timedelta(days=1)
        new_end = self._calculate_period_end(
            new_start,
            subscription.renewal_billing_period,
            subscription.renewal_term_count,
        )
        self._validate_subscription_write(
            {"current_period_start": new_start, "current_period_end": new_end},
            subscription,
            ctx,
        )

        subscription.current_period_start = new_start
        subscription.current_period_end = new_end
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        self._record_change(
            session,
            ctx,
            subscription,
            "RENEW",
            new_start,
            {"term_count": subscription.renewal_term_count, "billing_period": subscription.renewal_billing_period},
            commit=True,
        )
        self._emit_subscription_event("subscription.renewed", subscription, ctx)
        return self._to_subscription_read(subscription, ctx)

    def change_quantity(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        product_id: uuid.UUID,
        payload: ChangeQuantityRequest,
    ) -> SubscriptionRead:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False)
        item = next((row for row in subscription.items if row.product_id == product_id), None)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription item not found")

        write_payload = {"quantity": self._q(payload.new_qty)}
        try:
            self.subscription_item_repository.validate_write_security(
                write_payload,
                ctx,
                existing_scope={"company_code": subscription.company_code, "region_code": subscription.region_code},
                action="update",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        if payload.effective_date <= date.today():
            item.quantity = self._q(payload.new_qty)
            session.add(item)
            session.commit()
            session.refresh(subscription)

        self._record_change(
            session,
            ctx,
            subscription,
            "QUANTITY_CHANGE",
            payload.effective_date,
            {"product_id": str(product_id), "new_qty": str(payload.new_qty)},
            commit=True,
        )
        self._emit_subscription_event("subscription.quantity_changed", subscription, ctx)
        return self._to_subscription_read(subscription, ctx)

    def list_plans(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[PlanRead]:
        stmt: Select[tuple[SubscriptionPlan]] = (
            select(SubscriptionPlan)
            .where(SubscriptionPlan.tenant_id == tenant_id)
            .options(selectinload(SubscriptionPlan.items))
        )
        if company_code is not None:
            stmt = stmt.where(SubscriptionPlan.company_code == company_code)
        stmt = self.plan_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(SubscriptionPlan.created_at.desc())).all()
        return [self._to_plan_read(row, ctx) for row in rows]

    def get_plan(self, session: Session, ctx: AuthContext, plan_id: uuid.UUID) -> PlanRead:
        return self._to_plan_read(self._get_plan(session, ctx, plan_id, with_items=True), ctx)

    def list_subscriptions(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None = None,
    ) -> list[SubscriptionRead]:
        stmt: Select[tuple[Subscription]] = (
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .options(selectinload(Subscription.items))
        )
        if company_code is not None:
            stmt = stmt.where(Subscription.company_code == company_code)
        stmt = self.subscription_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(Subscription.created_at.desc())).all()
        return [self._to_subscription_read(row, ctx) for row in rows]

    def get_subscription(self, session: Session, ctx: AuthContext, subscription_id: uuid.UUID) -> SubscriptionRead:
        return self._to_subscription_read(self._get_subscription(session, ctx, subscription_id, with_items=True, with_changes=False), ctx)

    def list_subscription_changes(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
    ) -> list[SubscriptionChangeRead]:
        subscription = self._get_subscription(session, ctx, subscription_id, with_items=False, with_changes=False)
        rows = session.scalars(
            select(SubscriptionChange)
            .where(SubscriptionChange.subscription_id == subscription.id)
            .order_by(SubscriptionChange.created_at.asc())
        ).all()
        payload = [
            {
                "id": row.id,
                "subscription_id": row.subscription_id,
                "change_type": row.change_type,
                "effective_date": row.effective_date,
                "payload_json": row.payload_json,
                "created_at": row.created_at,
            }
            for row in rows
        ]
        secured = self.subscription_change_repository.apply_read_security_many(payload, ctx)
        return [SubscriptionChangeRead.model_validate(item) for item in secured]

    def _get_plan(self, session: Session, ctx: AuthContext, plan_id: uuid.UUID, *, with_items: bool) -> SubscriptionPlan:
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        if with_items:
            stmt = stmt.options(selectinload(SubscriptionPlan.items))
        plan = session.scalar(self.plan_repository.apply_scope_query(stmt, ctx))
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        return plan

    def _get_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        *,
        with_items: bool,
        with_changes: bool,
    ) -> Subscription:
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        if with_items:
            stmt = stmt.options(selectinload(Subscription.items))
        if with_changes:
            stmt = stmt.options(selectinload(Subscription.changes))
        subscription = session.scalar(self.subscription_repository.apply_scope_query(stmt, ctx))
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription not found")
        return subscription

    @staticmethod
    def _assert_transition(current: str, target: str) -> None:
        allowed = VALID_SUBSCRIPTION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"invalid subscription transition {current} -> {target}")

    def _validate_subscription_write(self, payload: dict[str, object], subscription: Subscription, ctx: AuthContext) -> None:
        try:
            self.subscription_repository.validate_write_security(
                payload,
                ctx,
                existing_scope={"company_code": subscription.company_code, "region_code": subscription.region_code},
                action="update",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    def _resolve_source_items(
        self,
        order_lines: list[RevenueOrderLine],
        plan_items: list[SubscriptionPlanItem] | None,
    ) -> list[dict[str, Decimal | uuid.UUID]]:
        if plan_items:
            return [
                {
                    "product_id": item.product_id,
                    "pricebook_item_id": item.pricebook_item_id,
                    "quantity": Decimal(item.quantity_default),
                    "unit_price_snapshot": Decimal(item.unit_price_snapshot),
                }
                for item in plan_items
            ]
        return [
            {
                "product_id": item.product_id,
                "pricebook_item_id": item.pricebook_item_id,
                "quantity": Decimal(item.quantity),
                "unit_price_snapshot": Decimal(item.unit_price),
            }
            for item in order_lines
        ]

    def _record_change(
        self,
        session: Session,
        ctx: AuthContext,
        subscription: Subscription,
        change_type: str,
        effective_date: date,
        payload_json: dict[str, object] | None,
        *,
        commit: bool,
    ) -> None:
        change_payload = {
            "subscription_id": subscription.id,
            "change_type": change_type,
            "effective_date": effective_date,
            "payload_json": payload_json,
        }
        try:
            self.subscription_change_repository.validate_write_security(
                change_payload,
                ctx,
                existing_scope={"company_code": subscription.company_code, "region_code": subscription.region_code},
                action="create",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        session.add(SubscriptionChange(**change_payload))
        if commit:
            session.commit()

    def _emit_subscription_event(self, event_type: str, subscription: Subscription, ctx: AuthContext) -> None:
        events.publish(
            {
                "event_type": event_type,
                "subscription_id": str(subscription.id),
                "company_code": subscription.company_code,
                "currency": subscription.currency,
                "period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
                "period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
                "correlation_id": ctx.correlation_id,
            }
        )

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.000001"))

    def _calculate_period_end(self, start: date, billing_period: str, term_count: int) -> date:
        if billing_period == "MONTHLY":
            end_exclusive = self._add_months(start, term_count)
        elif billing_period == "YEARLY":
            end_exclusive = self._add_months(start, 12 * term_count)
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid billing period")
        return end_exclusive - timedelta(days=1)

    @staticmethod
    def _add_months(base_date: date, months: int) -> date:
        month_index = base_date.month - 1 + months
        year = base_date.year + (month_index // 12)
        month = month_index % 12 + 1
        day = min(base_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _to_plan_item_read(self, item: SubscriptionPlanItem, ctx: AuthContext) -> PlanItemRead:
        payload = {
            "id": item.id,
            "plan_id": item.plan_id,
            "product_id": item.product_id,
            "pricebook_item_id": item.pricebook_item_id,
            "quantity_default": item.quantity_default,
            "unit_price_snapshot": item.unit_price_snapshot,
            "created_at": item.created_at,
        }
        secured = self.plan_item_repository.apply_read_security(payload, ctx)
        return PlanItemRead.model_validate(secured)

    def _to_plan_read(self, plan: SubscriptionPlan, ctx: AuthContext) -> PlanRead:
        payload = {
            "id": plan.id,
            "tenant_id": plan.tenant_id,
            "company_code": plan.company_code,
            "region_code": plan.region_code,
            "name": plan.name,
            "code": plan.code,
            "currency": plan.currency,
            "status": plan.status,
            "billing_period": plan.billing_period,
            "default_pricebook_id": plan.default_pricebook_id,
            "created_at": plan.created_at,
            "items": [
                {
                    "id": item.id,
                    "plan_id": item.plan_id,
                    "product_id": item.product_id,
                    "pricebook_item_id": item.pricebook_item_id,
                    "quantity_default": item.quantity_default,
                    "unit_price_snapshot": item.unit_price_snapshot,
                    "created_at": item.created_at,
                }
                for item in plan.items
            ],
        }
        secured = self.plan_repository.apply_read_security(payload, ctx)
        secured_items = self.plan_item_repository.apply_read_security_many(secured.get("items", []), ctx)
        secured["items"] = [PlanItemRead.model_validate(item) for item in secured_items]
        return PlanRead.model_validate(secured)

    def _to_subscription_read(self, subscription: Subscription, ctx: AuthContext) -> SubscriptionRead:
        payload = {
            "id": subscription.id,
            "tenant_id": subscription.tenant_id,
            "company_code": subscription.company_code,
            "region_code": subscription.region_code,
            "subscription_number": subscription.subscription_number,
            "contract_id": subscription.contract_id,
            "account_id": subscription.account_id,
            "currency": subscription.currency,
            "status": subscription.status,
            "start_date": subscription.start_date,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "auto_renew": subscription.auto_renew,
            "renewal_term_count": subscription.renewal_term_count,
            "renewal_billing_period": subscription.renewal_billing_period,
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at,
            "items": [
                {
                    "id": item.id,
                    "subscription_id": item.subscription_id,
                    "product_id": item.product_id,
                    "pricebook_item_id": item.pricebook_item_id,
                    "quantity": item.quantity,
                    "unit_price_snapshot": item.unit_price_snapshot,
                    "created_at": item.created_at,
                }
                for item in subscription.items
            ],
        }
        secured = self.subscription_repository.apply_read_security(payload, ctx)
        secured_items = self.subscription_item_repository.apply_read_security_many(secured.get("items", []), ctx)
        secured["items"] = [
            {
                "id": item["id"],
                "subscription_id": item["subscription_id"],
                "product_id": item["product_id"],
                "pricebook_item_id": item["pricebook_item_id"],
                "quantity": item["quantity"],
                "unit_price_snapshot": item["unit_price_snapshot"],
                "created_at": item["created_at"],
            }
            for item in secured_items
        ]
        return SubscriptionRead.model_validate(secured)

    def _next_number(self, session: Session, model: type[Subscription], company_code: str, prefix: str) -> str:
        counter = session.scalar(select(func.count()).select_from(model).where(model.company_code == company_code)) or 0
        return f"{prefix}-{company_code}-{counter + 1:05d}"


subscription_service = SubscriptionService()
