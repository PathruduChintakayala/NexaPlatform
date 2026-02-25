from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session, selectinload

from app import events
from app.business.billing.models import BillingInvoice
from app.business.payments.models import Payment, PaymentAllocation, Refund
from app.business.payments.repository import PaymentAllocationRepository, PaymentRepository, RefundRepository
from app.business.payments.schemas import (
    AllocatePaymentRequest,
    PaymentCreate,
    PaymentRead,
    PaymentAllocationRead,
    RefundCreate,
    RefundRead,
)
from app.platform.ledger.models import LedgerAccount
from app.platform.ledger.schemas import JournalEntryPostRequest, JournalLineInput
from app.platform.ledger.service import ledger_service
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError


@dataclass(slots=True)
class PaymentsService:
    payment_repository: PaymentRepository = PaymentRepository()
    allocation_repository: PaymentAllocationRepository = PaymentAllocationRepository()
    refund_repository: RefundRepository = RefundRepository()

    def create_payment(self, session: Session, ctx: AuthContext, payload: PaymentCreate) -> PaymentRead:
        data = payload.model_dump(mode="python")
        allocations_payload = data.pop("allocations", [])
        fx_rate_to_company_base = Decimal(data.pop("fx_rate_to_company_base", Decimal("1")))
        data["payment_number"] = self._next_number(session, data["company_code"])
        data["status"] = "CONFIRMED"
        data["received_at"] = data.get("received_at") or datetime.now(timezone.utc)
        data["ledger_journal_entry_id"] = None

        try:
            self.payment_repository.validate_write_security(data, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        payment = Payment(**data)
        session.add(payment)
        session.flush()

        payment.ledger_journal_entry_id = self._post_payment_to_ledger(session, ctx, payment, fx_rate_to_company_base)
        session.add(payment)
        session.commit()
        session.refresh(payment)

        if allocations_payload:
            for row in allocations_payload:
                self.allocate_payment(
                    session,
                    ctx,
                    payment.id,
                    AllocatePaymentRequest(invoice_id=row["invoice_id"], amount=row["amount"]),
                )

        events.publish(
            {
                "event_type": "payment.confirmed",
                "payment_id": str(payment.id),
                "company_code": payment.company_code,
                "currency": payment.currency,
                "amount": str(payment.amount),
            }
        )
        return self.get_payment(session, ctx, payment.id)

    def allocate_payment(
        self,
        session: Session,
        ctx: AuthContext,
        payment_id: uuid.UUID,
        payload: AllocatePaymentRequest,
    ) -> PaymentRead:
        payment = self._get_payment(session, ctx, payment_id, with_related=False)
        if payment.status not in {"CONFIRMED", "REFUNDED"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="payment is not allocatable")

        invoice = session.scalar(
            self.payment_repository.apply_scope_query(
                select(BillingInvoice).where(BillingInvoice.id == payload.invoice_id),
                ctx,
            )
        )
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invoice not found")

        if invoice.company_code != payment.company_code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invoice and payment company mismatch")
        if invoice.currency != payment.currency:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invoice and payment currency mismatch")
        if invoice.status not in {"ISSUED", "OVERDUE"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invoice must be ISSUED or OVERDUE")

        allocation_amount = self._q(payload.amount)
        if allocation_amount > Decimal(invoice.amount_due):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="allocation exceeds invoice amount_due")

        current_allocated = session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount_allocated), 0)).where(PaymentAllocation.payment_id == payment.id)
        )
        if self._q(Decimal(current_allocated) + allocation_amount) > self._q(Decimal(payment.amount)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="allocation exceeds payment amount")

        allocation_data = {
            "payment_id": payment.id,
            "invoice_id": invoice.id,
            "amount_allocated": allocation_amount,
        }
        try:
            self.allocation_repository.validate_write_security(
                allocation_data,
                ctx,
                existing_scope={"company_code": payment.company_code, "region_code": payment.region_code},
                action="create",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        allocation = PaymentAllocation(**allocation_data)
        session.add(allocation)

        invoice.amount_due = self._q(Decimal(invoice.amount_due) - allocation_amount)
        if invoice.amount_due == Decimal("0"):
            invoice.status = "PAID"

        session.add(invoice)
        session.commit()

        events.publish(
            {
                "event_type": "payment.allocated",
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
                "company_code": payment.company_code,
                "currency": payment.currency,
                "amount_allocated": str(allocation_amount),
                "invoice_amount_due": str(invoice.amount_due),
            }
        )
        return self.get_payment(session, ctx, payment.id)

    def refund_payment(
        self,
        session: Session,
        ctx: AuthContext,
        payment_id: uuid.UUID,
        payload: RefundCreate,
    ) -> RefundRead:
        payment = self._get_payment(session, ctx, payment_id, with_related=False)
        if payment.status not in {"CONFIRMED", "REFUNDED"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="payment cannot be refunded")

        refund_amount = self._q(payload.amount)
        existing_refunded = session.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                and_(Refund.payment_id == payment.id, Refund.status == "CONFIRMED")
            )
        )
        if self._q(Decimal(existing_refunded) + refund_amount) > self._q(Decimal(payment.amount)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="refund exceeds payment amount")

        refund_data = {
            "tenant_id": payment.tenant_id,
            "company_code": payment.company_code,
            "region_code": payment.region_code,
            "payment_id": payment.id,
            "amount": refund_amount,
            "reason": payload.reason,
            "status": "CONFIRMED",
            "ledger_journal_entry_id": None,
        }
        try:
            self.refund_repository.validate_write_security(refund_data, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        refund = Refund(**refund_data)
        session.add(refund)
        session.flush()

        refund.ledger_journal_entry_id = self._post_refund_to_ledger(
            session,
            ctx,
            payment,
            refund,
            Decimal(payload.fx_rate_to_company_base),
        )
        session.add(refund)

        if self._q(Decimal(existing_refunded) + refund_amount) == self._q(Decimal(payment.amount)):
            payment.status = "REFUNDED"
            session.add(payment)

        session.commit()
        session.refresh(refund)

        events.publish(
            {
                "event_type": "payment.refunded",
                "payment_id": str(payment.id),
                "refund_id": str(refund.id),
                "company_code": payment.company_code,
                "currency": payment.currency,
                "amount": str(refund.amount),
            }
        )
        return self._to_refund_read(refund, ctx)

    def list_payments(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[PaymentRead]:
        stmt: Select[tuple[Payment]] = (
            select(Payment)
            .where(Payment.tenant_id == tenant_id)
            .options(selectinload(Payment.allocations), selectinload(Payment.refunds))
        )
        if company_code is not None:
            stmt = stmt.where(Payment.company_code == company_code)

        stmt = self.payment_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(Payment.created_at.desc())).all()
        return [self._to_payment_read(row, ctx) for row in rows]

    def get_payment(self, session: Session, ctx: AuthContext, payment_id: uuid.UUID) -> PaymentRead:
        return self._to_payment_read(self._get_payment(session, ctx, payment_id, with_related=True), ctx)

    def list_allocations(self, session: Session, ctx: AuthContext, payment_id: uuid.UUID) -> list[PaymentAllocationRead]:
        payment = self._get_payment(session, ctx, payment_id, with_related=True)
        payload = [
            {
                "id": item.id,
                "payment_id": item.payment_id,
                "invoice_id": item.invoice_id,
                "amount_allocated": item.amount_allocated,
                "created_at": item.created_at,
            }
            for item in payment.allocations
        ]
        secured = self.allocation_repository.apply_read_security_many(payload, ctx)
        return [PaymentAllocationRead.model_validate(item) for item in secured]

    def _get_payment(self, session: Session, ctx: AuthContext, payment_id: uuid.UUID, *, with_related: bool) -> Payment:
        stmt = select(Payment).where(Payment.id == payment_id)
        if with_related:
            stmt = stmt.options(selectinload(Payment.allocations), selectinload(Payment.refunds))
        payment = session.scalar(self.payment_repository.apply_scope_query(stmt, ctx))
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not found")
        return payment

    def _post_payment_to_ledger(self, session: Session, ctx: AuthContext, payment: Payment, fx_rate: Decimal) -> uuid.UUID:
        cash = self._get_ledger_account(session, payment.tenant_id, payment.company_code, "1000")
        ar = self._get_ledger_account(session, payment.tenant_id, payment.company_code, "1100")
        self._validate_fx(cash.currency, payment.currency, fx_rate)

        entry = ledger_service.post_entry(
            session,
            ctx,
            JournalEntryPostRequest(
                tenant_id=payment.tenant_id,
                company_code=payment.company_code,
                entry_date=(payment.received_at.date() if payment.received_at else date.today()),
                description=f"Payment {payment.payment_number}",
                source_module="payments",
                source_type="payment",
                source_id=str(payment.id),
                created_by=ctx.user_id,
                lines=[
                    JournalLineInput(
                        account_id=cash.id,
                        debit_amount=Decimal(payment.amount),
                        credit_amount=Decimal("0"),
                        currency=payment.currency,
                        fx_rate_to_company_base=fx_rate,
                    ),
                    JournalLineInput(
                        account_id=ar.id,
                        debit_amount=Decimal("0"),
                        credit_amount=Decimal(payment.amount),
                        currency=payment.currency,
                        fx_rate_to_company_base=fx_rate,
                    ),
                ],
            ),
        )
        return entry.id

    def _post_refund_to_ledger(self, session: Session, ctx: AuthContext, payment: Payment, refund: Refund, fx_rate: Decimal) -> uuid.UUID:
        cash = self._get_ledger_account(session, payment.tenant_id, payment.company_code, "1000")
        ar = self._get_ledger_account(session, payment.tenant_id, payment.company_code, "1100")
        self._validate_fx(cash.currency, payment.currency, fx_rate)

        entry = ledger_service.post_entry(
            session,
            ctx,
            JournalEntryPostRequest(
                tenant_id=payment.tenant_id,
                company_code=payment.company_code,
                entry_date=date.today(),
                description=f"Refund for payment {payment.payment_number}",
                source_module="payments",
                source_type="refund",
                source_id=str(refund.id),
                created_by=ctx.user_id,
                lines=[
                    JournalLineInput(
                        account_id=ar.id,
                        debit_amount=Decimal(refund.amount),
                        credit_amount=Decimal("0"),
                        currency=payment.currency,
                        fx_rate_to_company_base=fx_rate,
                    ),
                    JournalLineInput(
                        account_id=cash.id,
                        debit_amount=Decimal("0"),
                        credit_amount=Decimal(refund.amount),
                        currency=payment.currency,
                        fx_rate_to_company_base=fx_rate,
                    ),
                ],
            ),
        )
        return entry.id

    @staticmethod
    def _validate_fx(account_currency: str, transaction_currency: str, fx_rate: Decimal) -> None:
        if account_currency != transaction_currency and Decimal(fx_rate) <= Decimal("0"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="fx_rate_to_company_base must be > 0")

    @staticmethod
    def _get_ledger_account(session: Session, tenant_id: str, company_code: str, code: str) -> LedgerAccount:
        account = session.scalar(
            select(LedgerAccount).where(
                and_(
                    LedgerAccount.tenant_id == tenant_id,
                    LedgerAccount.company_code == company_code,
                    LedgerAccount.code == code,
                    LedgerAccount.is_active.is_(True),
                )
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ledger account {code} not found")
        return account

    def _to_payment_read(self, payment: Payment, ctx: AuthContext) -> PaymentRead:
        payload = {
            "id": payment.id,
            "tenant_id": payment.tenant_id,
            "company_code": payment.company_code,
            "region_code": payment.region_code,
            "payment_number": payment.payment_number,
            "account_id": payment.account_id,
            "currency": payment.currency,
            "amount": payment.amount,
            "status": payment.status,
            "payment_method": payment.payment_method,
            "received_at": payment.received_at,
            "ledger_journal_entry_id": payment.ledger_journal_entry_id,
            "created_at": payment.created_at,
            "allocations": [
                {
                    "id": item.id,
                    "payment_id": item.payment_id,
                    "invoice_id": item.invoice_id,
                    "amount_allocated": item.amount_allocated,
                    "created_at": item.created_at,
                }
                for item in payment.allocations
            ],
            "refunds": [
                {
                    "id": item.id,
                    "tenant_id": item.tenant_id,
                    "company_code": item.company_code,
                    "region_code": item.region_code,
                    "payment_id": item.payment_id,
                    "amount": item.amount,
                    "reason": item.reason,
                    "status": item.status,
                    "ledger_journal_entry_id": item.ledger_journal_entry_id,
                    "created_at": item.created_at,
                }
                for item in payment.refunds
            ],
        }

        secured = self.payment_repository.apply_read_security(payload, ctx)
        secured_allocations = self.allocation_repository.apply_read_security_many(secured.get("allocations", []), ctx)
        secured_refunds = self.refund_repository.apply_read_security_many(secured.get("refunds", []), ctx)
        secured["allocations"] = [PaymentAllocationRead.model_validate(item) for item in secured_allocations]
        secured["refunds"] = [RefundRead.model_validate(item) for item in secured_refunds]
        return PaymentRead.model_validate(secured)

    def _to_refund_read(self, refund: Refund, ctx: AuthContext) -> RefundRead:
        payload = {
            "id": refund.id,
            "tenant_id": refund.tenant_id,
            "company_code": refund.company_code,
            "region_code": refund.region_code,
            "payment_id": refund.payment_id,
            "amount": refund.amount,
            "reason": refund.reason,
            "status": refund.status,
            "ledger_journal_entry_id": refund.ledger_journal_entry_id,
            "created_at": refund.created_at,
        }
        secured = self.refund_repository.apply_read_security(payload, ctx)
        return RefundRead.model_validate(secured)

    def _next_number(self, session: Session, company_code: str) -> str:
        counter = session.scalar(select(func.count()).select_from(Payment).where(Payment.company_code == company_code)) or 0
        return f"PAY-{company_code}-{counter + 1:05d}"

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.000001"))


payments_service = PaymentsService()
