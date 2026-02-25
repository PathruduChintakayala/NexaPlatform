from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.business.billing.models import BillingCreditNote, BillingInvoice
from app.business.billing.service import billing_service
from app.business.payments.models import Payment, PaymentAllocation, Refund
from app.business.payments.service import payments_service
from app.business.reporting.finance.repository import (
    FinanceDrilldownRepository,
    FinanceReconciliationRepository,
    FinanceReportRepository,
)
from app.business.reporting.finance.schemas import (
    ARAgingBucket,
    ARAgingReportRead,
    ARAgingRow,
    CashSummaryReportRead,
    InvoiceDrilldownRead,
    InvoicePaymentMismatchRow,
    JournalDrilldownRead,
    LedgerLinkMismatchRow,
    PaymentDrilldownRead,
    ReconciliationReportRead,
    RevenueSummaryReportRead,
    TrialBalanceReportRead,
    TrialBalanceRow,
)
from app.platform.ledger.models import JournalEntry, JournalLine, LedgerAccount
from app.platform.ledger.service import ledger_service
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError


@dataclass(slots=True)
class FinanceReportingService:
    report_repository: FinanceReportRepository = FinanceReportRepository()
    reconciliation_repository: FinanceReconciliationRepository = FinanceReconciliationRepository()
    drilldown_repository: FinanceDrilldownRepository = FinanceDrilldownRepository()

    def ar_aging(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None,
        as_of_date: date | None,
    ) -> ARAgingReportRead:
        self._validate_company_scope(ctx, company_code)
        target_date = as_of_date or date.today()

        stmt: Select[tuple[BillingInvoice]] = (
            select(BillingInvoice)
            .where(
                and_(
                    BillingInvoice.tenant_id == tenant_id,
                    BillingInvoice.amount_due > Decimal("0"),
                    BillingInvoice.status.in_(["ISSUED", "OVERDUE", "PAID"]),
                )
            )
        )
        if company_code is not None:
            stmt = stmt.where(BillingInvoice.company_code == company_code)

        stmt = self.report_repository.apply_scope_query(stmt, ctx)
        invoices = session.scalars(stmt.order_by(BillingInvoice.due_date.asc(), BillingInvoice.created_at.asc())).all()

        buckets: dict[str, Decimal] = {
            "current": Decimal("0"),
            "1_30": Decimal("0"),
            "31_60": Decimal("0"),
            "61_90": Decimal("0"),
            "90_plus": Decimal("0"),
        }
        rows: list[dict[str, object]] = []
        total_due = Decimal("0")

        for invoice in invoices:
            due = Decimal(invoice.amount_due)
            total_due += due
            days_overdue = 0
            if invoice.due_date is not None:
                days_overdue = max(0, (target_date - invoice.due_date).days)

            if days_overdue == 0:
                buckets["current"] += due
            elif days_overdue <= 30:
                buckets["1_30"] += due
            elif days_overdue <= 60:
                buckets["31_60"] += due
            elif days_overdue <= 90:
                buckets["61_90"] += due
            else:
                buckets["90_plus"] += due

            rows.append(
                {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "due_date": invoice.due_date,
                    "days_overdue": days_overdue,
                    "amount_due": self._q(due),
                    "currency": invoice.currency,
                    "status": invoice.status,
                }
            )

        secured_rows = self.report_repository.apply_read_security_many(rows, ctx)
        payload = {
            "as_of_date": target_date,
            "total_amount_due": self._q(total_due),
            "buckets": [
                {"label": "Current", "amount": self._q(buckets["current"])},
                {"label": "1-30", "amount": self._q(buckets["1_30"])},
                {"label": "31-60", "amount": self._q(buckets["31_60"])},
                {"label": "61-90", "amount": self._q(buckets["61_90"])},
                {"label": "90+", "amount": self._q(buckets["90_plus"])},
            ],
            "rows": [ARAgingRow.model_validate(item) for item in secured_rows],
        }
        secured = self.report_repository.apply_read_security(payload, ctx)
        secured["buckets"] = [ARAgingBucket.model_validate(item) for item in secured.get("buckets", [])]
        secured["rows"] = [ARAgingRow.model_validate(item) for item in secured.get("rows", [])]
        return ARAgingReportRead.model_validate(secured)

    def trial_balance(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> TrialBalanceReportRead:
        self._validate_company_scope(ctx, company_code)

        stmt = (
            select(
                LedgerAccount.id,
                LedgerAccount.code,
                LedgerAccount.name,
                func.coalesce(func.sum(JournalLine.debit_amount), 0),
                func.coalesce(func.sum(JournalLine.credit_amount), 0),
            )
            .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(JournalEntry.tenant_id == tenant_id)
            .group_by(LedgerAccount.id, LedgerAccount.code, LedgerAccount.name)
        )
        if company_code is not None:
            stmt = stmt.where(JournalEntry.company_code == company_code)
        if start_date is not None:
            stmt = stmt.where(JournalEntry.entry_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(JournalEntry.entry_date <= end_date)

        stmt = self.report_repository.apply_scope_query(stmt, ctx)
        records = session.execute(stmt.order_by(LedgerAccount.code.asc())).all()

        rows: list[dict[str, object]] = []
        debit_total = Decimal("0")
        credit_total = Decimal("0")
        for account_id, code, name, debit_amount, credit_amount in records:
            debit = self._q(Decimal(debit_amount))
            credit = self._q(Decimal(credit_amount))
            debit_total += debit
            credit_total += credit
            rows.append(
                {
                    "account_id": account_id,
                    "account_code": code,
                    "account_name": name,
                    "debit_total": debit,
                    "credit_total": credit,
                    "net_balance": self._q(debit - credit),
                }
            )

        secured_rows = self.report_repository.apply_read_security_many(rows, ctx)
        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "total_debits": self._q(debit_total),
            "total_credits": self._q(credit_total),
            "rows": [TrialBalanceRow.model_validate(item) for item in secured_rows],
        }
        secured = self.report_repository.apply_read_security(payload, ctx)
        secured["rows"] = [TrialBalanceRow.model_validate(item) for item in secured.get("rows", [])]
        return TrialBalanceReportRead.model_validate(secured)

    def cash_summary(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> CashSummaryReportRead:
        self._validate_company_scope(ctx, company_code)

        payment_stmt = select(Payment).where(Payment.tenant_id == tenant_id)
        refund_stmt = select(Refund).where(Refund.tenant_id == tenant_id)
        if company_code is not None:
            payment_stmt = payment_stmt.where(Payment.company_code == company_code)
            refund_stmt = refund_stmt.where(Refund.company_code == company_code)

        payment_stmt = self.report_repository.apply_scope_query(payment_stmt, ctx)
        refund_stmt = self.report_repository.apply_scope_query(refund_stmt, ctx)

        payments = session.scalars(payment_stmt).all()
        refunds = session.scalars(refund_stmt).all()

        def _in_range(ts: datetime | None) -> bool:
            if ts is None:
                return start_date is None and end_date is None
            value = ts.date()
            if start_date is not None and value < start_date:
                return False
            if end_date is not None and value > end_date:
                return False
            return True

        received_total = self._q(sum((Decimal(row.amount) for row in payments if _in_range(row.received_at or row.created_at)), start=Decimal("0")))
        refunded_total = self._q(sum((Decimal(row.amount) for row in refunds if _in_range(row.created_at)), start=Decimal("0")))

        selected_payments = [row for row in payments if _in_range(row.received_at or row.created_at)]
        currencies = sorted({row.currency for row in selected_payments})
        currency_value = currencies[0] if len(currencies) == 1 else None

        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "currency": currency_value,
            "received_total": received_total,
            "refunded_total": refunded_total,
            "net_cash_total": self._q(received_total - refunded_total),
            "payment_count": len(selected_payments),
            "refund_count": len([row for row in refunds if _in_range(row.created_at)]),
        }
        secured = self.report_repository.apply_read_security(payload, ctx)
        return CashSummaryReportRead.model_validate(secured)

    def revenue_summary(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> RevenueSummaryReportRead:
        self._validate_company_scope(ctx, company_code)

        invoices_stmt = select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
        credits_stmt = select(BillingCreditNote).where(BillingCreditNote.tenant_id == tenant_id)
        if company_code is not None:
            invoices_stmt = invoices_stmt.where(BillingInvoice.company_code == company_code)
            credits_stmt = credits_stmt.where(BillingCreditNote.company_code == company_code)

        invoices_stmt = self.report_repository.apply_scope_query(invoices_stmt, ctx)
        credits_stmt = self.report_repository.apply_scope_query(credits_stmt, ctx)

        invoices = session.scalars(invoices_stmt).all()
        credit_notes = session.scalars(credits_stmt).all()

        def _date_in_range(value: date | None) -> bool:
            if value is None:
                return start_date is None and end_date is None
            if start_date is not None and value < start_date:
                return False
            if end_date is not None and value > end_date:
                return False
            return True

        selected_invoices = [row for row in invoices if _date_in_range(row.issue_date)]
        selected_credits = [row for row in credit_notes if _date_in_range(row.issue_date)]

        invoiced_total = self._q(sum((Decimal(row.total) for row in selected_invoices), start=Decimal("0")))
        credit_note_total = self._q(sum((Decimal(row.total) for row in selected_credits), start=Decimal("0")))

        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "invoiced_total": invoiced_total,
            "credit_note_total": credit_note_total,
            "net_revenue_total": self._q(invoiced_total - credit_note_total),
            "invoice_count": len(selected_invoices),
            "credit_note_count": len(selected_credits),
        }
        secured = self.report_repository.apply_read_security(payload, ctx)
        return RevenueSummaryReportRead.model_validate(secured)

    def reconciliation(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> ReconciliationReportRead:
        self._validate_company_scope(ctx, company_code)

        invoice_stmt = select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id)
        if company_code is not None:
            invoice_stmt = invoice_stmt.where(BillingInvoice.company_code == company_code)
        if start_date is not None:
            invoice_stmt = invoice_stmt.where(BillingInvoice.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date is not None:
            invoice_stmt = invoice_stmt.where(BillingInvoice.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))

        invoice_stmt = self.reconciliation_repository.apply_scope_query(invoice_stmt, ctx)
        invoices = session.scalars(invoice_stmt).all()
        invoice_ids = [item.id for item in invoices]

        allocation_sums: dict[uuid.UUID, Decimal] = {}
        if invoice_ids:
            for invoice_id, total in session.execute(
                select(PaymentAllocation.invoice_id, func.coalesce(func.sum(PaymentAllocation.amount_allocated), 0))
                .where(PaymentAllocation.invoice_id.in_(invoice_ids))
                .group_by(PaymentAllocation.invoice_id)
            ).all():
                allocation_sums[invoice_id] = self._q(Decimal(total))

        credit_sums: dict[uuid.UUID, Decimal] = {}
        if invoice_ids:
            for invoice_id, total in session.execute(
                select(BillingCreditNote.invoice_id, func.coalesce(func.sum(BillingCreditNote.total), 0))
                .where(BillingCreditNote.invoice_id.in_(invoice_ids))
                .group_by(BillingCreditNote.invoice_id)
            ).all():
                credit_sums[invoice_id] = self._q(Decimal(total))

        invoice_mismatch_rows: list[dict[str, object]] = []
        for invoice in invoices:
            allocated_total = allocation_sums.get(invoice.id, Decimal("0"))
            credit_total = credit_sums.get(invoice.id, Decimal("0"))
            expected_due = self._q(max(Decimal("0"), Decimal(invoice.total) - allocated_total - credit_total))
            actual_due = self._q(Decimal(invoice.amount_due))
            delta = self._q(actual_due - expected_due)
            if delta != Decimal("0"):
                invoice_mismatch_rows.append(
                    {
                        "invoice_id": invoice.id,
                        "invoice_number": invoice.invoice_number,
                        "invoice_total": self._q(Decimal(invoice.total)),
                        "allocated_total": allocated_total,
                        "credit_note_total": credit_total,
                        "expected_amount_due": expected_due,
                        "actual_amount_due": actual_due,
                        "delta": delta,
                    }
                )

        ledger_rows: list[dict[str, object]] = []
        ledger_rows.extend(self._invoice_ledger_mismatches(session, invoices))
        ledger_rows.extend(self._payment_ledger_mismatches(session, ctx, tenant_id, company_code, start_date, end_date))
        ledger_rows.extend(self._refund_ledger_mismatches(session, ctx, tenant_id, company_code, start_date, end_date))

        secured_invoice_rows = self.reconciliation_repository.apply_read_security_many(invoice_mismatch_rows, ctx)
        secured_ledger_rows = self.reconciliation_repository.apply_read_security_many(ledger_rows, ctx)

        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "invoice_payment_mismatches": [InvoicePaymentMismatchRow.model_validate(item) for item in secured_invoice_rows],
            "ledger_link_mismatches": [LedgerLinkMismatchRow.model_validate(item) for item in secured_ledger_rows],
        }
        secured = self.reconciliation_repository.apply_read_security(payload, ctx)
        secured["invoice_payment_mismatches"] = [
            InvoicePaymentMismatchRow.model_validate(item) for item in secured.get("invoice_payment_mismatches", [])
        ]
        secured["ledger_link_mismatches"] = [
            LedgerLinkMismatchRow.model_validate(item) for item in secured.get("ledger_link_mismatches", [])
        ]
        return ReconciliationReportRead.model_validate(secured)

    def invoice_drilldown(self, session: Session, ctx: AuthContext, invoice_id: uuid.UUID) -> InvoiceDrilldownRead:
        invoice = billing_service.get_invoice(session, ctx, invoice_id)
        payload = {"invoice": invoice.model_dump(mode="python")}
        secured = self.drilldown_repository.apply_read_security(payload, ctx)
        return InvoiceDrilldownRead.model_validate(secured)

    def payment_drilldown(self, session: Session, ctx: AuthContext, payment_id: uuid.UUID) -> PaymentDrilldownRead:
        payment = payments_service.get_payment(session, ctx, payment_id)
        payload = {"payment": payment.model_dump(mode="python")}
        secured = self.drilldown_repository.apply_read_security(payload, ctx)
        return PaymentDrilldownRead.model_validate(secured)

    def journal_drilldown(self, session: Session, ctx: AuthContext, entry_id: uuid.UUID) -> JournalDrilldownRead:
        entry = ledger_service.get_entry(session, ctx, entry_id)
        payload = {"journal_entry": entry.model_dump(mode="python")}
        secured = self.drilldown_repository.apply_read_security(payload, ctx)
        return JournalDrilldownRead.model_validate(secured)

    def _invoice_ledger_mismatches(self, session: Session, invoices: list[BillingInvoice]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        entry_cache: dict[uuid.UUID, JournalEntry | None] = {}

        for invoice in invoices:
            if invoice.status in {"ISSUED", "OVERDUE", "PAID", "VOID"} and invoice.ledger_journal_entry_id is None:
                rows.append(
                    {
                        "entity_type": "invoice",
                        "entity_id": invoice.id,
                        "reference_number": invoice.invoice_number,
                        "ledger_journal_entry_id": None,
                        "issue": "missing_ledger_link",
                    }
                )
                continue

            if invoice.ledger_journal_entry_id is None:
                continue

            entry = entry_cache.get(invoice.ledger_journal_entry_id)
            if entry is None and invoice.ledger_journal_entry_id not in entry_cache:
                entry = session.scalar(select(JournalEntry).where(JournalEntry.id == invoice.ledger_journal_entry_id))
                entry_cache[invoice.ledger_journal_entry_id] = entry

            if entry is None:
                rows.append(
                    {
                        "entity_type": "invoice",
                        "entity_id": invoice.id,
                        "reference_number": invoice.invoice_number,
                        "ledger_journal_entry_id": invoice.ledger_journal_entry_id,
                        "issue": "linked_entry_not_found",
                    }
                )
            elif entry.source_type not in {"invoice", "credit_note"}:
                rows.append(
                    {
                        "entity_type": "invoice",
                        "entity_id": invoice.id,
                        "reference_number": invoice.invoice_number,
                        "ledger_journal_entry_id": invoice.ledger_journal_entry_id,
                        "issue": "linked_entry_source_mismatch",
                    }
                )

        return rows

    def _payment_ledger_mismatches(
        self,
        session: Session,
        ctx: AuthContext,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[dict[str, object]]:
        stmt = select(Payment).where(Payment.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(Payment.company_code == company_code)
        if start_date is not None:
            stmt = stmt.where(Payment.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date is not None:
            stmt = stmt.where(Payment.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))
        stmt = self.reconciliation_repository.apply_scope_query(stmt, ctx)

        rows: list[dict[str, object]] = []
        payments = session.scalars(stmt).all()
        for payment in payments:
            if payment.status in {"CONFIRMED", "REFUNDED"} and payment.ledger_journal_entry_id is None:
                rows.append(
                    {
                        "entity_type": "payment",
                        "entity_id": payment.id,
                        "reference_number": payment.payment_number,
                        "ledger_journal_entry_id": None,
                        "issue": "missing_ledger_link",
                    }
                )
        return rows

    def _refund_ledger_mismatches(
        self,
        session: Session,
        ctx: AuthContext,
        tenant_id: str,
        company_code: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[dict[str, object]]:
        stmt = select(Refund).where(Refund.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(Refund.company_code == company_code)
        if start_date is not None:
            stmt = stmt.where(Refund.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
        if end_date is not None:
            stmt = stmt.where(Refund.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))
        stmt = self.reconciliation_repository.apply_scope_query(stmt, ctx)

        rows: list[dict[str, object]] = []
        refunds = session.scalars(stmt).all()
        for refund in refunds:
            if refund.status == "CONFIRMED" and refund.ledger_journal_entry_id is None:
                rows.append(
                    {
                        "entity_type": "refund",
                        "entity_id": refund.id,
                        "reference_number": str(refund.payment_id),
                        "ledger_journal_entry_id": None,
                        "issue": "missing_ledger_link",
                    }
                )
        return rows

    def _validate_company_scope(self, ctx: AuthContext, company_code: str | None) -> None:
        if company_code is None:
            return
        try:
            self.report_repository.validate_read_scope(ctx, company_code=company_code, region_code=None, action="read")
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    @staticmethod
    def _q(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.000001"))


finance_reporting_service = FinanceReportingService()
