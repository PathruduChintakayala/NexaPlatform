from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from fastapi import HTTPException, status
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import get_correlation_id
from app.revenue.models import LegacyRevenueOrder, LegacyRevenueQuote


tracer = trace.get_tracer("app.revenue.client")


class RevenueClient(Protocol):
    def create_draft_quote(self, opportunity_id: uuid.UUID, idempotency_key: str) -> uuid.UUID: ...

    def create_draft_order(self, opportunity_id: uuid.UUID, idempotency_key: str) -> uuid.UUID: ...

    def get_quote(self, quote_id: uuid.UUID) -> dict[str, Any]: ...

    def get_order(self, order_id: uuid.UUID) -> dict[str, Any]: ...


class StubRevenueClient:
    quote_statuses = {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED"}
    order_statuses = {"DRAFT", "ORDERED", "FULFILLED", "CANCELLED"}

    def __init__(self, session: Session):
        self.session = session

    def create_draft_quote(self, opportunity_id: uuid.UUID, idempotency_key: str) -> uuid.UUID:
        with tracer.start_as_current_span("revenue.create_draft_quote") as span:
            span.set_attribute("opportunity_id", str(opportunity_id))
            span.set_attribute("correlation_id", get_correlation_id())
            quote = LegacyRevenueQuote(opportunity_id=opportunity_id, status="DRAFT")
            self.session.add(quote)
            self.session.flush()
            span.set_attribute("quote_id", str(quote.id))
            return quote.id

    def create_draft_order(self, opportunity_id: uuid.UUID, idempotency_key: str) -> uuid.UUID:
        with tracer.start_as_current_span("revenue.create_draft_order") as span:
            span.set_attribute("opportunity_id", str(opportunity_id))
            span.set_attribute("correlation_id", get_correlation_id())
            order = LegacyRevenueOrder(opportunity_id=opportunity_id, status="DRAFT")
            self.session.add(order)
            self.session.flush()
            span.set_attribute("order_id", str(order.id))
            return order.id

    def get_quote(self, quote_id: uuid.UUID) -> dict[str, Any]:
        with tracer.start_as_current_span("revenue.get_quote") as span:
            span.set_attribute("quote_id", str(quote_id))
            span.set_attribute("correlation_id", get_correlation_id())
            row = self.session.scalar(select(LegacyRevenueQuote).where(LegacyRevenueQuote.id == quote_id))
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="quote not found")
            if row.status not in self.quote_statuses:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid quote status")
            span.set_attribute("opportunity_id", str(row.opportunity_id))
            return self._to_payload(row.id, row.status, row.updated_at)

    def get_order(self, order_id: uuid.UUID) -> dict[str, Any]:
        with tracer.start_as_current_span("revenue.get_order") as span:
            span.set_attribute("order_id", str(order_id))
            span.set_attribute("correlation_id", get_correlation_id())
            row = self.session.scalar(select(LegacyRevenueOrder).where(LegacyRevenueOrder.id == order_id))
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order not found")
            if row.status not in self.order_statuses:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid order status")
            span.set_attribute("opportunity_id", str(row.opportunity_id))
            return self._to_payload(row.id, row.status, row.updated_at)

    def _to_payload(self, item_id: uuid.UUID, status_value: str, updated_at: datetime) -> dict[str, Any]:
        return {"id": str(item_id), "status": status_value, "updated_at": updated_at}
