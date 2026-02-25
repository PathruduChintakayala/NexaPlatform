from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.metrics import (
    observe_ledger_entries_posted,
    observe_ledger_lines_posted,
    observe_ledger_post_failure,
)
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError
from app.platform.security.repository import BaseRepository
from app.platform.ledger.models import JournalEntry, JournalLine, LedgerAccount
from app.platform.ledger.schemas import (
    JournalEntryPostRequest,
    JournalEntryRead,
    JournalEntryReverseRequest,
    JournalLineRead,
    LedgerAccountCreate,
    LedgerAccountRead,
)


class LedgerAccountRepository(BaseRepository):
    resource = "ledger.account"


class JournalEntryRepository(BaseRepository):
    resource = "ledger.journal_entry"


class JournalLineRepository(BaseRepository):
    resource = "ledger.journal_line"


@dataclass(slots=True)
class LedgerService:
    account_repository: LedgerAccountRepository = LedgerAccountRepository()
    entry_repository: JournalEntryRepository = JournalEntryRepository()
    line_repository: JournalLineRepository = JournalLineRepository()

    def create_account(self, session: Session, ctx: AuthContext, dto: LedgerAccountCreate) -> LedgerAccountRead:
        payload = dto.model_dump(mode="python")
        try:
            self.account_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        account = LedgerAccount(**payload)
        session.add(account)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ledger account already exists")
        session.refresh(account)
        return LedgerAccountRead.model_validate(account)

    def list_accounts(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None = None,
    ) -> list[LedgerAccountRead]:
        stmt: Select[tuple[LedgerAccount]] = select(LedgerAccount).where(LedgerAccount.tenant_id == tenant_id)
        if company_code is not None:
            stmt = stmt.where(LedgerAccount.company_code == company_code)
        stmt = self.account_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(LedgerAccount.code.asc())).all()
        return [LedgerAccountRead.model_validate(item) for item in rows]

    def post_entry(self, session: Session, ctx: AuthContext, request: JournalEntryPostRequest) -> JournalEntryRead:
        payload = request.model_dump(mode="python")
        try:
            self.entry_repository.validate_write_security(payload, ctx, action="create")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            observe_ledger_post_failure("authz")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        account_ids = [line.account_id for line in request.lines]
        accounts = session.scalars(
            select(LedgerAccount).where(LedgerAccount.id.in_(account_ids))
        ).all()
        account_map = {item.id: item for item in accounts}
        if len(account_map) != len(set(account_ids)):
            observe_ledger_post_failure("account_not_found")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="one or more accounts not found")

        for account in account_map.values():
            if account.tenant_id != request.tenant_id or account.company_code != request.company_code or not account.is_active:
                observe_ledger_post_failure("account_scope_invalid")
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid account scope")

        debit_total = Decimal("0")
        credit_total = Decimal("0")
        line_rows: list[dict[str, Any]] = []

        for line in request.lines:
            debit = Decimal(line.debit_amount)
            credit = Decimal(line.credit_amount)
            if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
                observe_ledger_post_failure("invalid_line_side")
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="line must be single-sided")

            account = account_map[line.account_id]
            fx_rate = Decimal(line.fx_rate_to_company_base)
            if line.currency == account.currency:
                fx_rate = Decimal("1")
            amount = (debit if debit > 0 else credit) * fx_rate

            if debit > 0:
                debit_total += amount
            else:
                credit_total += amount

            line_rows.append(
                {
                    "account_id": line.account_id,
                    "debit_amount": debit,
                    "credit_amount": credit,
                    "currency": line.currency,
                    "fx_rate_to_company_base": fx_rate,
                    "amount_company_base": amount,
                    "memo": line.memo,
                    "dimensions_json": line.dimensions_json,
                }
            )

        if debit_total.quantize(Decimal("0.000001")) != credit_total.quantize(Decimal("0.000001")):
            observe_ledger_post_failure("unbalanced_entry")
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="journal entry is not balanced")

        entry = JournalEntry(
            tenant_id=request.tenant_id,
            company_code=request.company_code,
            entry_date=request.entry_date,
            description=request.description,
            source_module=request.source_module,
            source_type=request.source_type,
            source_id=request.source_id,
            posting_status="POSTED",
            created_by=request.created_by,
        )
        session.add(entry)
        session.flush()

        for row in line_rows:
            session.add(JournalLine(journal_entry_id=entry.id, **row))

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            observe_ledger_post_failure("db_error")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="failed to persist journal entry")

        session.refresh(entry)
        entry = session.scalar(
            select(JournalEntry)
            .where(JournalEntry.id == entry.id)
            .options(selectinload(JournalEntry.lines))
        )
        if entry is None:
            observe_ledger_post_failure("reload_error")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="entry reload failed")

        observe_ledger_entries_posted()
        observe_ledger_lines_posted(len(entry.lines))
        audit.record(
            actor_user_id=ctx.user_id,
            entity_type="ledger.journal_entry",
            entity_id=str(entry.id),
            action="ledger.posted",
            before=None,
            after={
                "tenant_id": entry.tenant_id,
                "company_code": entry.company_code,
                "source_module": entry.source_module,
                "source_type": entry.source_type,
                "source_id": entry.source_id,
                "line_count": len(entry.lines),
            },
            correlation_id=ctx.correlation_id,
        )
        return self._to_entry_read(entry, ctx)

    def reverse_entry(
        self,
        session: Session,
        ctx: AuthContext,
        entry_id: uuid.UUID,
        request: JournalEntryReverseRequest,
    ) -> JournalEntryRead:
        entry = session.scalar(
            self.entry_repository.apply_scope_query(
                select(JournalEntry)
                .where(JournalEntry.id == entry_id)
                .options(selectinload(JournalEntry.lines)),
                ctx,
            )
        )
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
        if entry.posting_status == "REVERSED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="entry already reversed")

        reverse_payload = {
            "tenant_id": entry.tenant_id,
            "company_code": entry.company_code,
            "entry_date": date.today(),
            "description": f"Reversal: {request.reason}",
            "source_module": "ledger",
            "source_type": "reversal",
            "source_id": str(entry.id),
            "created_by": request.created_by,
            "lines": [
                {
                    "account_id": line.account_id,
                    "debit_amount": line.credit_amount,
                    "credit_amount": line.debit_amount,
                    "currency": line.currency,
                    "fx_rate_to_company_base": line.fx_rate_to_company_base,
                    "memo": line.memo,
                    "dimensions_json": line.dimensions_json,
                }
                for line in entry.lines
            ],
        }
        reversed_entry = self.post_entry(
            session,
            ctx,
            JournalEntryPostRequest.model_validate(reverse_payload),
        )

        entry.posting_status = "REVERSED"
        session.add(entry)
        session.commit()

        audit.record(
            actor_user_id=ctx.user_id,
            entity_type="ledger.journal_entry",
            entity_id=str(entry.id),
            action="ledger.reversed",
            before={"posting_status": "POSTED"},
            after={"posting_status": "REVERSED", "reversal_entry_id": str(reversed_entry.id)},
            correlation_id=ctx.correlation_id,
        )
        return reversed_entry

    def get_entry(self, session: Session, ctx: AuthContext, entry_id: uuid.UUID) -> JournalEntryRead:
        entry = session.scalar(
            self.entry_repository.apply_scope_query(
                select(JournalEntry)
                .where(JournalEntry.id == entry_id)
                .options(selectinload(JournalEntry.lines)),
                ctx,
            )
        )
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
        return self._to_entry_read(entry, ctx)

    def list_entries(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        source_module: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> list[JournalEntryRead]:
        stmt: Select[tuple[JournalEntry]] = (
            select(JournalEntry)
            .where(JournalEntry.tenant_id == tenant_id)
            .options(selectinload(JournalEntry.lines))
        )
        if company_code is not None:
            stmt = stmt.where(JournalEntry.company_code == company_code)
        if start_date is not None:
            stmt = stmt.where(JournalEntry.entry_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(JournalEntry.entry_date <= end_date)
        if source_module is not None:
            stmt = stmt.where(JournalEntry.source_module == source_module)
        if source_type is not None:
            stmt = stmt.where(JournalEntry.source_type == source_type)
        if source_id is not None:
            stmt = stmt.where(JournalEntry.source_id == source_id)

        stmt = self.entry_repository.apply_scope_query(stmt, ctx)
        rows = session.scalars(stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())).all()
        return [self._to_entry_read(row, ctx) for row in rows]

    def seed_chart_of_accounts(
        self,
        session: Session,
        ctx: AuthContext,
        *,
        tenant_id: str,
        company_code: str,
        currency: str,
    ) -> list[LedgerAccountRead]:
        seed_payload = {
            "tenant_id": tenant_id,
            "company_code": company_code,
            "currency": currency,
        }
        try:
            self.account_repository.validate_write_security(seed_payload, ctx, action="seed")
        except (ForbiddenFieldError, AuthorizationError) as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        defaults = [
            ("1000", "Cash", "ASSET"),
            ("1100", "Accounts Receivable", "ASSET"),
            ("2200", "Deferred Revenue", "LIABILITY"),
            ("4000", "Revenue", "REVENUE"),
            ("2300", "Tax Payable", "LIABILITY"),
        ]

        created: list[LedgerAccount] = []
        existing_codes = set(
            session.scalars(
                select(LedgerAccount.code).where(
                    and_(LedgerAccount.tenant_id == tenant_id, LedgerAccount.company_code == company_code)
                )
            ).all()
        )

        for code, name, account_type in defaults:
            if code in existing_codes:
                continue
            account = LedgerAccount(
                tenant_id=tenant_id,
                company_code=company_code,
                name=name,
                code=code,
                type=account_type,
                currency=currency,
                is_active=True,
            )
            session.add(account)
            created.append(account)

        session.commit()
        return [LedgerAccountRead.model_validate(item) for item in created]

    def _to_entry_read(self, entry: JournalEntry, ctx: AuthContext) -> JournalEntryRead:
        payload = {
            "id": entry.id,
            "tenant_id": entry.tenant_id,
            "company_code": entry.company_code,
            "entry_date": entry.entry_date,
            "description": entry.description,
            "source_module": entry.source_module,
            "source_type": entry.source_type,
            "source_id": entry.source_id,
            "posting_status": entry.posting_status,
            "created_by": entry.created_by,
            "created_at": entry.created_at,
            "lines": [
                {
                    "id": line.id,
                    "journal_entry_id": line.journal_entry_id,
                    "account_id": line.account_id,
                    "debit_amount": line.debit_amount,
                    "credit_amount": line.credit_amount,
                    "currency": line.currency,
                    "fx_rate_to_company_base": line.fx_rate_to_company_base,
                    "amount_company_base": line.amount_company_base,
                    "memo": line.memo,
                    "dimensions_json": line.dimensions_json,
                    "created_at": line.created_at,
                }
                for line in entry.lines
            ],
        }

        secured_entry = self.entry_repository.apply_read_security(payload, ctx)
        secured_lines = self.line_repository.apply_read_security_many(secured_entry.get("lines", []), ctx)
        secured_entry["lines"] = [JournalLineRead.model_validate(item) for item in secured_lines]
        return JournalEntryRead.model_validate(secured_entry)


ledger_service = LedgerService()
