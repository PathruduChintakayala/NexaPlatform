from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select

from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact
from app.platform.security.context import AuthContext
from app.platform.security.repository import BaseRepository


class ContactRepository(BaseRepository):
    resource = "crm.contact"

    def apply_scope_query(self, query: Select[Any], ctx: AuthContext) -> Select[Any]:
        scoped = super().apply_scope_query(query, ctx)

        if not ctx.is_super_admin and ctx.entity_scope:
            legal_entity_ids: list[uuid.UUID] = []
            for value in ctx.entity_scope:
                try:
                    legal_entity_ids.append(uuid.UUID(str(value)))
                except ValueError:
                    continue

            if legal_entity_ids:
                scoped = scoped.where(
                    CRMContact.account_id.in_(
                        select(CRMAccountLegalEntity.account_id).where(
                            CRMAccountLegalEntity.legal_entity_id.in_(legal_entity_ids)
                        )
                    )
                )

        if not ctx.is_super_admin and ctx.region_scope:
            scoped = scoped.where(
                CRMContact.account_id.in_(
                    select(CRMAccount.id).where(CRMAccount.primary_region_code.in_(ctx.region_scope))
                )
            )

        return scoped

    @staticmethod
    def _normalize_write_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for field_name, value in payload.items():
            if field_name == "custom_fields" and isinstance(value, dict):
                for custom_key, custom_value in value.items():
                    normalized[f"custom_fields.{custom_key}"] = custom_value
                continue
            normalized[field_name] = value
        return normalized
