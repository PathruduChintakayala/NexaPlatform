from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import events
from app.business.billing.models import (
    BillingCreditNote,
    BillingCreditNoteLine,
    BillingInvoice,
    BillingInvoiceLine,
)
from app.business.billing.repository import (
    CreditNoteLineRepository,
    CreditNoteRepository,
    InvoiceLineRepository,
    InvoiceRepository,
)
from app.business.billing.schemas import (
    CreditNoteCreate,
    CreditNoteLineRead,
    CreditNoteRead,
    InvoiceLineRead,
    InvoiceRead,
    MarkInvoicePaidRequest,
    RefreshOverdueResponse,
)
from app.business.revenue.models import RevenueOrder
from app.business.subscription.models import Subscription
from app.core.config import get_settings
from app.platform.ledger.models import LedgerAccount
from app.platform.ledger.schemas import JournalEntryPostRequest, JournalEntryReverseRequest, JournalLineInput
from app.platform.ledger.service import ledger_service
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError


@dataclass(slots=True)
class BillingService:
    invoice_repository: InvoiceRepository = InvoiceRepository()
    invoice_line_repository: InvoiceLineRepository = InvoiceLineRepository()
    credit_note_repository: CreditNoteRepository = CreditNoteRepository()
    credit_note_line_repository: CreditNoteLineRepository = CreditNoteLineRepository()

    def generate_invoice_from_subscription(
        self,
        session: Session,
        ctx: AuthContext,
        subscription_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> InvoiceRead:
        subscription = session.scalar(
            select(Subscription)
            .where(Subscription.id == subscription_id)
            .options(selectinload(Subscription.items))
        )
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription not found")
        try:
            self.invoice_repository.validate_read_scope(
                ctx,
                company_code=subscription.company_code,
                region_code=subscription.region_code,
                action="read",
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        subtotal = self._q(sum((Decimal(item.quantity) * Decimal(item.unit_price_snapshot) for item in subscription.items), start=Decimal("0")))
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        total = self._q(subtotal - discount_total + tax_total)

        payload = {
            "tenant_id": subscription.tenant_id,
            "company_code": subscription.company_code,
            "region_code": subscription.region_code,
            "invoice_number": self._next_number(session, BillingInvoice, subscription.company_code, "INV"),
            "account_id": subscription.account_id,
            "subscription_id": subscription.id,
            "order_id": None,
            "currency": subscription.currency,
            "status": "DRAFT",
            "issue_date": None,
            "due_date": period_end,
            "period_start": period_start,
            "period_end": period_end,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_total": tax_total,
            "total": total,
            "amount_due": total,
            "ledger_journal_entry_id": None,
        }
        try:
            self.invoice_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        invoice = BillingInvoice(**payload)
        session.add(invoice)
        session.flush()

        for item in subscription.items:
            line_payload = {
                "invoice_id": invoice.id,
                "product_id": item.product_id,
                "description": f"Subscription item {item.product_id}",
                "quantity": self._q(Decimal(item.quantity)),
                "unit_price_snapshot": self._q(Decimal(item.unit_price_snapshot)),
                "line_total": self._q(Decimal(item.quantity) * Decimal(item.unit_price_snapshot)),
                "source_type": "SUBSCRIPTION_ITEM",
                "source_id": item.id,
            }
            try:
                self.invoice_line_repository.validate_write_security(
                    line_payload,
                    ctx,
                    existing_scope={"company_code": subscription.company_code, "region_code": subscription.region_code},
                    action="create",
                )
            except (ForbiddenFieldError, AuthorizationError) as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            session.add(BillingInvoiceLine(**line_payload))

        session.commit()
        return self.get_invoice(session, ctx, invoice.id)

    def issue_invoice(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID) -> InvoiceRead:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=True)
        if invoice.status != "DRAFT":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invoice must be DRAFT")

        write_payload = {"status": "ISSUED", "issue_date": invoice.issue_date or date.today()}
        self._validate_invoice_write(write_payload, invoice, ctx)

        invoice.status = "ISSUED"
        invoice.issue_date = invoice.issue_date or date.today()
        invoice.due_date = invoice.due_date or (invoice.issue_date + timedelta(days=30))

        settings = get_settings()
        if settings.billing_post_to_ledger and invoice.ledger_journal_entry_id is None:
            journal_id = self._post_invoice_to_ledger(session, ctx, invoice)
            invoice.ledger_journal_entry_id = journal_id

        session.add(invoice)
        session.commit()
        session.refresh(invoice)

        events.publish(
            {
                "event_type": "invoice.issued",
                "invoice_id": str(invoice.id),
                "company_code": invoice.company_code,
                "currency": invoice.currency,
                "amount_due": str(invoice.amount_due),
            }
        )
        return self._to_invoice_read(invoice, ctx)

    def void_invoice(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID, reason: str) -> InvoiceRead:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=True)
        if invoice.status not in {"DRAFT", "ISSUED", "OVERDUE"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invoice cannot be voided")

        self._validate_invoice_write({"status": "VOID", "amount_due": Decimal("0")}, invoice, ctx)

        if invoice.ledger_journal_entry_id is not None:
            ledger_service.reverse_entry(
                session,
                ctx,
                invoice.ledger_journal_entry_id,
                JournalEntryReverseRequest(reason=reason, created_by=ctx.user_id),
            )

        invoice.status = "VOID"
        invoice.amount_due = Decimal("0")
        session.add(invoice)
        session.commit()
        session.refresh(invoice)

        events.publish(
            {
                "event_type": "invoice.voided",
                "invoice_id": str(invoice.id),
                "company_code": invoice.company_code,
                "currency": invoice.currency,
            }
        )
        return self._to_invoice_read(invoice, ctx)

    def apply_credit_note(
        self,
        session: Session,
        ctx: AuthContext,
        invoice_id: uuid.UUID,
        payload: CreditNoteCreate,
    ) -> CreditNoteRead:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=True)
        if invoice.status not in {"ISSUED", "OVERDUE"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invoice must be ISSUED or OVERDUE")

        subtotal = Decimal("0")
        line_payloads: list[dict[str, object]] = []
        for line in payload.lines:
            line_total = self._q(line.quantity * line.unit_price_snapshot)
            subtotal += line_total
            line_payloads.append(
                {
                    "invoice_line_id": line.invoice_line_id,
                    "description": line.description,
                    "quantity": self._q(line.quantity),
                    "unit_price_snapshot": self._q(line.unit_price_snapshot),
                    "line_total": line_total,
                }
            )

        subtotal = self._q(subtotal)
        tax_total = self._q(payload.tax_total)
        total = self._q(subtotal + tax_total)

        note_payload = {
            "tenant_id": invoice.tenant_id,
            "company_code": invoice.company_code,
            "region_code": invoice.region_code,
            "credit_note_number": self._next_number(session, BillingCreditNote, invoice.company_code, "CN"),
            "invoice_id": invoice.id,
            "currency": invoice.currency,
            "status": "ISSUED",
            "issue_date": payload.issue_date or date.today(),
            "subtotal": subtotal,
            "tax_total": tax_total,
            "total": total,
            "ledger_journal_entry_id": None,
        }
        try:
            self.credit_note_repository.validate_write_security(note_payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        note = BillingCreditNote(**note_payload)
        session.add(note)
        session.flush()

        for row in line_payloads:
            full = {"credit_note_id": note.id, **row}
            try:
                self.credit_note_line_repository.validate_write_security(
                    full,
                    ctx,
                    existing_scope={"company_code": invoice.company_code, "region_code": invoice.region_code},
                    action="create",
                )
            except (ForbiddenFieldError, AuthorizationError) as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            session.add(BillingCreditNoteLine(**full))

        settings = get_settings()
        if settings.billing_post_to_ledger:
            note.ledger_journal_entry_id = self._post_credit_note_to_ledger(session, ctx, invoice, note)

        invoice.amount_due = self._q(max(Decimal("0"), Decimal(invoice.amount_due) - total))
        if invoice.amount_due == Decimal("0") and invoice.status in {"ISSUED", "OVERDUE"}:
            invoice.status = "PAID"

        note.status = "APPLIED"
        session.add(note)
        session.add(invoice)
        session.commit()
        session.refresh(note)

        events.publish(
            {
                "event_type": "credit_note.issued",
                "credit_note_id": str(note.id),
                "invoice_id": str(invoice.id),
                "company_code": invoice.company_code,
                "currency": invoice.currency,
            }
        )
        events.publish(
            {
                "event_type": "credit_note.applied",
                "credit_note_id": str(note.id),
                "invoice_id": str(invoice.id),
                "company_code": invoice.company_code,
                "currency": invoice.currency,
                "amount_due": str(invoice.amount_due),
            }
        )
        return self._to_credit_note_read(note, ctx)

    def mark_invoice_paid(
        self,
        session: Session,
        ctx: AuthContext,
        invoice_id: uuid.UUID,
        payload: MarkInvoicePaidRequest,
    ) -> InvoiceRead:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=True)
        if invoice.status not in {"ISSUED", "OVERDUE", "PAID"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invoice must be ISSUED/OVERDUE/PAID")

        new_due = self._q(max(Decimal("0"), Decimal(invoice.amount_due) - Decimal(payload.amount)))
        new_status = "PAID" if new_due == Decimal("0") else "ISSUED"

        self._validate_invoice_write({"status": new_status, "amount_due": new_due}, invoice, ctx)

        invoice.amount_due = new_due
        invoice.status = new_status
        session.add(invoice)
        session.commit()
        session.refresh(invoice)

        events.publish(
            {
                "event_type": "invoice.paid",
                "invoice_id": str(invoice.id),
                "company_code": invoice.company_code,
                "currency": invoice.currency,
                "amount_due": str(invoice.amount_due),
            }
        )
        return self._to_invoice_read(invoice, ctx)

    def refresh_overdue(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID) -> RefreshOverdueResponse:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=False)
        is_overdue = bool(
            invoice.status == "ISSUED"
            and invoice.due_date is not None
            and date.today() > invoice.due_date
            and Decimal(invoice.amount_due) > Decimal("0")
        )
        if is_overdue:
            self._validate_invoice_write({"status": "OVERDUE"}, invoice, ctx)
            invoice.status = "OVERDUE"
            session.add(invoice)
            session.commit()
            events.publish(
                {
                    "event_type": "invoice.overdue",
                    "invoice_id": str(invoice.id),
                    "company_code": invoice.company_code,
                    "currency": invoice.currency,
                    "amount_due": str(invoice.amount_due),
                }
            )
        return RefreshOverdueResponse(invoice_id=invoice.id, status=invoice.status, overdue=is_overdue)

    def list_invoices(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[InvoiceRead]:
        stmt: Select[tuple[BillingInvoice]] = (
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .options(selectinload(BillingInvoice.lines))
        )
        if company_code is not None:
            stmt = stmt.where(BillingInvoice.company_code == company_code)
        stmt = self.invoice_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(BillingInvoice.created_at.desc())).all()
        return [self._to_invoice_read(row, ctx) for row in rows]

    def get_invoice(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID) -> InvoiceRead:
        return self._to_invoice_read(self._get_invoice(session, ctx, invoice_id, with_lines=True), ctx)

    def list_invoice_lines(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID) -> list[InvoiceLineRead]:
        invoice = self._get_invoice(session, ctx, invoice_id, with_lines=True)
        payload = [
            {
                "id": line.id,
                "invoice_id": line.invoice_id,
                "product_id": line.product_id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price_snapshot": line.unit_price_snapshot,
                "line_total": line.line_total,
                "source_type": line.source_type,
                "source_id": line.source_id,
            }
            for line in invoice.lines
        ]
        secured = self.invoice_line_repository.apply_read_security_many(payload, ctx)
        return [InvoiceLineRead.model_validate(item) for item in secured]

    def list_credit_notes(self, session: Session, ctx: AuthContext, *, tenant_id: str, company_code: str | None = None) -> list[CreditNoteRead]:
        stmt: Select[tuple[BillingCreditNote]] = (
            select(BillingCreditNote)
            .where(BillingCreditNote.tenant_id == tenant_id)
            .options(selectinload(BillingCreditNote.lines))
        )
        if company_code is not None:
            stmt = stmt.where(BillingCreditNote.company_code == company_code)
        stmt = self.credit_note_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(BillingCreditNote.created_at.desc())).all()
        return [self._to_credit_note_read(row, ctx) for row in rows]

    def get_credit_note(self, session: Session, ctx: AuthContext, credit_note_id: uuid.UUID) -> CreditNoteRead:
        note = session.scalar(
            self.credit_note_repository.apply_scope_query(
                select(BillingCreditNote)
                .where(BillingCreditNote.id == credit_note_id)
                .options(selectinload(BillingCreditNote.lines)),
                ctx,
            )
        )
        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="credit note not found")
        return self._to_credit_note_read(note, ctx)

    def handle_subscription_billing_event(
        self,
        session: Session,
        *,
        subscription_id: uuid.UUID,
        company_code: str,
        currency: str,
        period_start: date | None,
        period_end: date | None,
        correlation_id: str | None,
    ) -> InvoiceRead:
        if period_start is None or period_end is None:
            subscription = session.scalar(select(Subscription).where(Subscription.id == subscription_id))
            if subscription is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="subscription not found")
            period_start = period_start or subscription.current_period_start or date.today()
            period_end = period_end or subscription.current_period_end or period_start

        ctx = AuthContext(
            user_id="system.billing",
            tenant_id=None,
            correlation_id=correlation_id,
            is_super_admin=False,
            entity_scope=[company_code],
        )
        return self.generate_invoice_from_subscription(session, ctx, subscription_id, period_start, period_end)

    def _post_invoice_to_ledger(self, session: Session, ctx: AuthContext, invoice: BillingInvoice) -> uuid.UUID:
        ar = self._get_ledger_account(session, invoice, "1100")
        revenue = self._get_ledger_account(session, invoice, "4000")
        request = JournalEntryPostRequest(
            tenant_id=invoice.tenant_id,
            company_code=invoice.company_code,
            entry_date=invoice.issue_date or date.today(),
            description=f"Invoice {invoice.invoice_number}",
            source_module="billing",
            source_type="invoice",
            source_id=str(invoice.id),
            created_by=ctx.user_id,
            lines=[
                JournalLineInput(
                    account_id=ar.id,
                    debit_amount=Decimal(invoice.total),
                    credit_amount=Decimal("0"),
                    currency=invoice.currency,
                    fx_rate_to_company_base=Decimal("1"),
                ),
                JournalLineInput(
                    account_id=revenue.id,
                    debit_amount=Decimal("0"),
                    credit_amount=Decimal(invoice.total),
                    currency=invoice.currency,
                    fx_rate_to_company_base=Decimal("1"),
                ),
            ],
        )
        entry = ledger_service.post_entry(session, ctx, request)
        return entry.id

    def _post_credit_note_to_ledger(
        self,
        session: Session,
        ctx: AuthContext,
        invoice: BillingInvoice,
        note: BillingCreditNote,
    ) -> uuid.UUID:
        ar = self._get_ledger_account(session, invoice, "1100")
        revenue = self._get_ledger_account(session, invoice, "4000")
        request = JournalEntryPostRequest(
            tenant_id=invoice.tenant_id,
            company_code=invoice.company_code,
            entry_date=note.issue_date or date.today(),
            description=f"Credit note {note.credit_note_number}",
            source_module="billing",
            source_type="credit_note",
            source_id=str(note.id),
            created_by=ctx.user_id,
            lines=[
                JournalLineInput(
                    account_id=revenue.id,
                    debit_amount=Decimal(note.total),
                    credit_amount=Decimal("0"),
                    currency=invoice.currency,
                    fx_rate_to_company_base=Decimal("1"),
                ),
                JournalLineInput(
                    account_id=ar.id,
                    debit_amount=Decimal("0"),
                    credit_amount=Decimal(note.total),
                    currency=invoice.currency,
                    fx_rate_to_company_base=Decimal("1"),
                ),
            ],
        )
        entry = ledger_service.post_entry(session, ctx, request)
        return entry.id

    @staticmethod
    def _get_ledger_account(session: Session, invoice: BillingInvoice, code: str) -> LedgerAccount:
        account = session.scalar(
            select(LedgerAccount).where(
                and_(
                    LedgerAccount.tenant_id == invoice.tenant_id,
                    LedgerAccount.company_code == invoice.company_code,
                    LedgerAccount.code == code,
                    LedgerAccount.is_active.is_(True),
                )
            )
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ledger account {code} not found")
        return account

    def _validate_invoice_write(self, payload: dict[str, object], invoice: BillingInvoice, ctx: AuthContext) -> None:
        try:
            self.invoice_repository.validate_write_security(
                payload,
                ctx,
                existing_scope={"company_code": invoice.company_code, "region_code": invoice.region_code},
                action="update",
            )
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    def _get_invoice(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID, *, with_lines: bool) -> BillingInvoice:
        stmt = select(BillingInvoice).where(BillingInvoice.id == invoice_id)
        if with_lines:
            stmt = stmt.options(selectinload(BillingInvoice.lines))
        invoice = session.scalar(self.invoice_repository.apply_scope_query(stmt, ctx))
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invoice not found")
        return invoice

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.000001"))

    def _to_invoice_read(self, invoice: BillingInvoice, ctx: AuthContext) -> InvoiceRead:
        payload = {
            "id": invoice.id,
            "tenant_id": invoice.tenant_id,
            "company_code": invoice.company_code,
            "region_code": invoice.region_code,
            "invoice_number": invoice.invoice_number,
            "account_id": invoice.account_id,
            "subscription_id": invoice.subscription_id,
            "order_id": invoice.order_id,
            "currency": invoice.currency,
            "status": invoice.status,
            "issue_date": invoice.issue_date,
            "due_date": invoice.due_date,
            "period_start": invoice.period_start,
            "period_end": invoice.period_end,
            "subtotal": invoice.subtotal,
            "discount_total": invoice.discount_total,
            "tax_total": invoice.tax_total,
            "total": invoice.total,
            "amount_due": invoice.amount_due,
            "ledger_journal_entry_id": invoice.ledger_journal_entry_id,
            "created_at": invoice.created_at,
            "updated_at": invoice.updated_at,
            "lines": [
                {
                    "id": line.id,
                    "invoice_id": line.invoice_id,
                    "product_id": line.product_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price_snapshot": line.unit_price_snapshot,
                    "line_total": line.line_total,
                    "source_type": line.source_type,
                    "source_id": line.source_id,
                }
                for line in invoice.lines
            ],
        }
        secured = self.invoice_repository.apply_read_security(payload, ctx)
        secured_lines = self.invoice_line_repository.apply_read_security_many(secured.get("lines", []), ctx)
        secured["lines"] = [InvoiceLineRead.model_validate(item) for item in secured_lines]
        return InvoiceRead.model_validate(secured)

    def _to_credit_note_read(self, note: BillingCreditNote, ctx: AuthContext) -> CreditNoteRead:
        payload = {
            "id": note.id,
            "tenant_id": note.tenant_id,
            "company_code": note.company_code,
            "region_code": note.region_code,
            "credit_note_number": note.credit_note_number,
            "invoice_id": note.invoice_id,
            "currency": note.currency,
            "status": note.status,
            "issue_date": note.issue_date,
            "subtotal": note.subtotal,
            "tax_total": note.tax_total,
            "total": note.total,
            "ledger_journal_entry_id": note.ledger_journal_entry_id,
            "created_at": note.created_at,
            "lines": [
                {
                    "id": line.id,
                    "credit_note_id": line.credit_note_id,
                    "invoice_line_id": line.invoice_line_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price_snapshot": line.unit_price_snapshot,
                    "line_total": line.line_total,
                }
                for line in note.lines
            ],
        }
        secured = self.credit_note_repository.apply_read_security(payload, ctx)
        secured_lines = self.credit_note_line_repository.apply_read_security_many(secured.get("lines", []), ctx)
        secured["lines"] = [CreditNoteLineRead.model_validate(item) for item in secured_lines]
        return CreditNoteRead.model_validate(secured)

    def _next_number(self, session: Session, model: type[BillingInvoice] | type[BillingCreditNote], company_code: str, prefix: str) -> str:
        counter = session.scalar(select(func.count()).select_from(model).where(model.company_code == company_code)) or 0
        return f"{prefix}-{company_code}-{counter + 1:05d}"


billing_service = BillingService()
