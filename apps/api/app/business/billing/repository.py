from __future__ import annotations

from app.platform.security.repository import BaseRepository


class InvoiceRepository(BaseRepository):
    resource = "billing.invoice"


class InvoiceLineRepository(BaseRepository):
    resource = "billing.invoice_line"


class CreditNoteRepository(BaseRepository):
    resource = "billing.credit_note"


class CreditNoteLineRepository(BaseRepository):
    resource = "billing.credit_note_line"


class DunningCaseRepository(BaseRepository):
    resource = "billing.dunning_case"
