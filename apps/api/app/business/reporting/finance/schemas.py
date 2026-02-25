from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ReportScopeQuery(BaseModel):
    tenant_id: str = Field(min_length=1)
    company_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ARAgingBucket(BaseModel):
    label: str
    amount: Decimal | str


class ARAgingRow(BaseModel):
    invoice_id: UUID
    invoice_number: str
    due_date: date | None
    days_overdue: int
    amount_due: Decimal | str
    currency: str
    status: str


class ARAgingReportRead(BaseModel):
    as_of_date: date
    total_amount_due: Decimal | str
    buckets: list[ARAgingBucket]
    rows: list[ARAgingRow]


class TrialBalanceRow(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    debit_total: Decimal | str
    credit_total: Decimal | str
    net_balance: Decimal | str


class TrialBalanceReportRead(BaseModel):
    start_date: date | None
    end_date: date | None
    total_debits: Decimal | str
    total_credits: Decimal | str
    rows: list[TrialBalanceRow]


class CashSummaryReportRead(BaseModel):
    start_date: date | None
    end_date: date | None
    currency: str | None
    received_total: Decimal | str
    refunded_total: Decimal | str
    net_cash_total: Decimal | str
    payment_count: int
    refund_count: int


class RevenueSummaryReportRead(BaseModel):
    start_date: date | None
    end_date: date | None
    invoiced_total: Decimal | str
    credit_note_total: Decimal | str
    net_revenue_total: Decimal | str
    invoice_count: int
    credit_note_count: int


class InvoicePaymentMismatchRow(BaseModel):
    invoice_id: UUID
    invoice_number: str
    invoice_total: Decimal | str
    allocated_total: Decimal | str
    credit_note_total: Decimal | str
    expected_amount_due: Decimal | str
    actual_amount_due: Decimal | str
    delta: Decimal | str


class LedgerLinkMismatchRow(BaseModel):
    entity_type: str
    entity_id: UUID
    reference_number: str
    ledger_journal_entry_id: UUID | None
    issue: str


class ReconciliationReportRead(BaseModel):
    start_date: date | None
    end_date: date | None
    invoice_payment_mismatches: list[InvoicePaymentMismatchRow]
    ledger_link_mismatches: list[LedgerLinkMismatchRow]


class InvoiceDrilldownRead(BaseModel):
    invoice: dict[str, object]


class PaymentDrilldownRead(BaseModel):
    payment: dict[str, object]


class JournalDrilldownRead(BaseModel):
    journal_entry: dict[str, object]
