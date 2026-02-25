from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app import audit
from app.metrics import observe_fls_field_counts
from app.platform.security.context import AuthContext
from app.platform.security.errors import ForbiddenFieldError
from app.platform.security.policies import FieldDecision, get_policy_backend


MASKED_FIELD_VALUE = "***"


def apply_fls_read(resource: str, record: dict[str, Any], ctx: AuthContext) -> dict[str, Any]:
    """Apply field-level read policy to a single record."""

    policy = get_policy_backend()
    output: dict[str, Any] = {}
    masked_fields: list[str] = []
    denied_fields: list[str] = []

    for field_name, value in record.items():
        decision = policy.evaluate_field_read(resource, field_name, ctx)
        if decision == FieldDecision.ALLOW:
            output[field_name] = value
            continue
        if decision == FieldDecision.MASK:
            output[field_name] = MASKED_FIELD_VALUE
            masked_fields.append(field_name)
            continue
        denied_fields.append(field_name)

    _emit_fls_observability(
        resource=resource,
        operation="read",
        ctx=ctx,
        record=record,
        masked_fields=masked_fields,
        denied_fields=denied_fields,
    )
    return output


def apply_fls_read_many(resource: str, records: Iterable[dict[str, Any]], ctx: AuthContext) -> list[dict[str, Any]]:
    """Apply field-level read policy to a sequence of records."""

    return [apply_fls_read(resource, record, ctx) for record in records]


def validate_fls_write(resource: str, payload: dict[str, Any], ctx: AuthContext) -> None:
    """Validate field-level write policy for a payload and raise on forbidden fields."""

    policy = get_policy_backend()
    denied_fields = [field_name for field_name in payload if not policy.can_edit_field(resource, field_name, ctx)]
    if not denied_fields:
        return

    _emit_fls_observability(
        resource=resource,
        operation="write",
        ctx=ctx,
        record=payload,
        masked_fields=[],
        denied_fields=denied_fields,
    )
    raise ForbiddenFieldError(resource=resource, fields=denied_fields)


def _emit_fls_observability(
    *,
    resource: str,
    operation: str,
    ctx: AuthContext,
    record: dict[str, Any],
    masked_fields: list[str],
    denied_fields: list[str],
) -> None:
    masked_count = len(masked_fields)
    denied_count = len(denied_fields)
    if masked_count == 0 and denied_count == 0:
        return

    observe_fls_field_counts(resource=resource, operation=operation, masked_count=masked_count, denied_count=denied_count)
    audit.record(
        actor_user_id=ctx.user_id,
        entity_type="security.fls",
        entity_id=str(record.get("id", "unknown")),
        action=f"fls.{operation}",
        before=None,
        after={
            "resource": resource,
            "tenant_id": ctx.tenant_id,
            "role_names": ctx._cache.get("authz.role_names", ctx.roles),
            "role_ids": ctx._cache.get("authz.role_ids", []),
            "masked_fields": masked_fields,
            "denied_fields": denied_fields,
            "masked_count": masked_count,
            "denied_count": denied_count,
        },
        correlation_id=None,
    )
