from __future__ import annotations

from app.platform.security.repository import BaseRepository


class RevenueQuoteRepository(BaseRepository):
    resource = "revenue.quote"


class RevenueQuoteLineRepository(BaseRepository):
    resource = "revenue.quote_line"


class RevenueOrderRepository(BaseRepository):
    resource = "revenue.order"


class RevenueOrderLineRepository(BaseRepository):
    resource = "revenue.order_line"


class RevenueContractRepository(BaseRepository):
    resource = "revenue.contract"
