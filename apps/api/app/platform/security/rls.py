from __future__ import annotations

from typing import Any

from sqlalchemy.sql import Select

from app import audit
from app.metrics import observe_rls_denied_read, observe_rls_denied_write
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError


_ENTITY_ALIASES = ("company_code", "selling_legal_entity_id", "legal_entity_id")
_REGION_ALIASES = ("region_code", "region")


def is_admin_bypass(ctx: AuthContext) -> bool:
    if ctx.is_super_admin:
        return True
    role_set = {item.lower() for item in ctx.roles}
    permission_set = {item.lower() for item in ctx.permissions}
    return "admin" in role_set or "admin" in permission_set or "system.admin" in permission_set


def apply_rls_filter(query: Select[Any], resource: str, ctx: AuthContext) -> Select[Any]:
    """Apply generic RLS filters for models exposing company_code/region_code columns."""

    if is_admin_bypass(ctx):
        return query

    entity_scope = [value for value in ctx.entity_scope if value]
    region_scope = [value for value in ctx.region_scope if value]
    if not entity_scope and not region_scope:
        return query

    for description in query.column_descriptions:
        model = description.get("entity")
        if model is None:
            continue
        if entity_scope and hasattr(model, "company_code"):
            query = query.where(getattr(model, "company_code").in_(entity_scope))
        if region_scope and hasattr(model, "region_code"):
            query = query.where(getattr(model, "region_code").in_(region_scope))

    return query


def validate_rls_write(
    resource: str,
    payload: dict[str, Any],
    ctx: AuthContext,
    *,
    action: str = "write",
    existing_scope: dict[str, str | None] | None = None,
) -> None:
    """Validate write scope constraints for company/entity and region."""

    if is_admin_bypass(ctx):
        return

    entity_scope = [value for value in ctx.entity_scope if value]
    region_scope = [value for value in ctx.region_scope if value]
    if not entity_scope and not region_scope:
        return

    company_value = _resolve_scope_value(payload, existing_scope, _ENTITY_ALIASES)
    region_value = _resolve_scope_value(payload, existing_scope, _REGION_ALIASES)

    if entity_scope and company_value is not None and str(company_value) not in set(entity_scope):
        _emit_rls_denied(
            resource=resource,
            action=action,
            scope_type="entity",
            scope_value=str(company_value),
            ctx=ctx,
            is_read=False,
        )
        raise AuthorizationError(f"Out-of-scope company_code for resource '{resource}'")

    if region_scope and region_value is not None and str(region_value) not in set(region_scope):
        _emit_rls_denied(
            resource=resource,
            action=action,
            scope_type="region",
            scope_value=str(region_value),
            ctx=ctx,
            is_read=False,
        )
        raise AuthorizationError(f"Out-of-scope region_code for resource '{resource}'")


def validate_rls_read_scope(
    resource: str,
    ctx: AuthContext,
    *,
    company_code: str | None,
    region_code: str | None,
    action: str = "read",
) -> None:
    """Validate record-level read scope for records loaded by id/detail APIs."""

    if is_admin_bypass(ctx):
        return

    entity_scope = [value for value in ctx.entity_scope if value]
    region_scope = [value for value in ctx.region_scope if value]
    if not entity_scope and not region_scope:
        return

    if entity_scope and company_code is not None and company_code not in set(entity_scope):
        _emit_rls_denied(
            resource=resource,
            action=action,
            scope_type="entity",
            scope_value=company_code,
            ctx=ctx,
            is_read=True,
        )
        raise AuthorizationError(f"Out-of-scope company_code for resource '{resource}'")

    if region_scope and region_code is not None and region_code not in set(region_scope):
        _emit_rls_denied(
            resource=resource,
            action=action,
            scope_type="region",
            scope_value=region_code,
            ctx=ctx,
            is_read=True,
        )
        raise AuthorizationError(f"Out-of-scope region_code for resource '{resource}'")


def _resolve_scope_value(
    payload: dict[str, Any],
    existing_scope: dict[str, str | None] | None,
    aliases: tuple[str, ...],
) -> str | None:
    for key in aliases:
        if key in payload and payload.get(key) is not None:
            return str(payload.get(key))
    if existing_scope is not None:
        for key in aliases:
            value = existing_scope.get(key)
            if value is not None:
                return str(value)
    return None


def _emit_rls_denied(
    *,
    resource: str,
    action: str,
    scope_type: str,
    scope_value: str,
    ctx: AuthContext,
    is_read: bool,
) -> None:
    if is_read:
        observe_rls_denied_read(resource=resource, scope_type=scope_type)
    else:
        observe_rls_denied_write(resource=resource, scope_type=scope_type)

    audit.record(
        actor_user_id=ctx.user_id,
        entity_type="security.rls",
        entity_id="scope",
        action="rls.denied",
        before=None,
        after={
            "resource": resource,
            "action": action,
            "scope_type": scope_type,
            "scope_value": scope_value,
            "correlation_id": ctx.correlation_id,
            "user_id": ctx.user_id,
        },
        correlation_id=ctx.correlation_id,
    )
