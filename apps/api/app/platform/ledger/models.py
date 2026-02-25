from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LedgerAccount(Base):
    __tablename__ = "ledger_account"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    lines: Mapped[list[JournalLine]] = relationship("JournalLine", back_populates="account")

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_code", "code", name="uq_ledger_account_code"),
        Index("ix_ledger_account_scope", "tenant_id", "company_code"),
    )


class JournalEntry(Base):
    __tablename__ = "ledger_journal_entry"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    company_code: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date(), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_module: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    posting_status: Mapped[str] = mapped_column(String(32), nullable=False, default="POSTED", server_default="POSTED")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    lines: Mapped[list[JournalLine]] = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_ledger_entry_scope_date", "tenant_id", "company_code", "entry_date"),
        Index("ix_ledger_entry_source", "source_module", "source_type", "source_id"),
    )


class JournalLine(Base):
    __tablename__ = "ledger_journal_line"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ledger_journal_entry.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ledger_account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0")
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    fx_rate_to_company_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        default=Decimal("1"),
        server_default="1",
    )
    amount_company_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    entry: Mapped[JournalEntry] = relationship("JournalEntry", back_populates="lines")
    account: Mapped[LedgerAccount] = relationship("LedgerAccount", back_populates="lines")

    __table_args__ = (
        CheckConstraint("debit_amount >= 0", name="ck_ledger_line_debit_nonnegative"),
        CheckConstraint("credit_amount >= 0", name="ck_ledger_line_credit_nonnegative"),
        CheckConstraint(
            "((debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0))",
            name="ck_ledger_line_single_sided",
        ),
        CheckConstraint("fx_rate_to_company_base > 0", name="ck_ledger_line_fx_positive"),
    )
