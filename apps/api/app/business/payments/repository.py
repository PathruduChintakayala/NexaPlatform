from __future__ import annotations

from app.platform.security.repository import BaseRepository


class PaymentRepository(BaseRepository):
    resource = "payments.payment"


class PaymentAllocationRepository(BaseRepository):
    resource = "payments.allocation"


class RefundRepository(BaseRepository):
    resource = "payments.refund"
