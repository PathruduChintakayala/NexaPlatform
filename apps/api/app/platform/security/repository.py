from __future__ import annotations

from typing import Any

from sqlalchemy.sql import Select

from app.platform.security.context import AuthContext
from app.platform.security.fls import apply_fls_read, apply_fls_read_many, validate_fls_write
from app.platform.security.rls import apply_rls_filter, validate_rls_read_scope, validate_rls_write


class BaseRepository:
    resource = ""

    def apply_scope_query(self, query: Select[Any], ctx: AuthContext) -> Select[Any]:
        return apply_rls_filter(query, self.resource, ctx)

    def apply_read_security(self, record: dict[str, Any], ctx: AuthContext) -> dict[str, Any]:
        return apply_fls_read(self.resource, record, ctx)

    def apply_read_security_many(self, records: list[dict[str, Any]], ctx: AuthContext) -> list[dict[str, Any]]:
        return apply_fls_read_many(self.resource, records, ctx)

    def validate_write_security(
        self,
        payload: dict[str, Any],
        ctx: AuthContext,
        *,
        existing_scope: dict[str, str | None] | None = None,
        action: str = "write",
    ) -> None:
        validate_rls_write(self.resource, payload, ctx, existing_scope=existing_scope, action=action)
        validate_fls_write(self.resource, self._normalize_write_payload(payload), ctx)

    def validate_read_scope(
        self,
        ctx: AuthContext,
        *,
        company_code: str | None,
        region_code: str | None,
        action: str = "read",
    ) -> None:
        validate_rls_read_scope(
            self.resource,
            ctx,
            company_code=company_code,
            region_code=region_code,
            action=action,
        )

    @staticmethod
    def _normalize_write_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return payload
