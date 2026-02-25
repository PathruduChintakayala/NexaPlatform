from __future__ import annotations

from app.platform.security.repository import BaseRepository


class FinanceReportRepository(BaseRepository):
    resource = "reports.finance.summary"


class FinanceReconciliationRepository(BaseRepository):
    resource = "reports.finance.reconciliation"


class FinanceDrilldownRepository(BaseRepository):
    resource = "reports.finance.drilldown"
