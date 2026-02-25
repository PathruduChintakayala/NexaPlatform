from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.authz.models import Permission, Role, RolePermission, UserRole
from app.core.database import SessionLocal
from app.metrics import observe_authz_db_queries_count, observe_authz_policy_cache_hit, observe_authz_policy_cache_miss
from app.platform.security.context import AuthContext


class ResourceAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class FieldAction(StrEnum):
    READ = "field.read"
    MASK = "field.mask"
    EDIT = "field.edit"


class FieldDecision(StrEnum):
    ALLOW = "ALLOW"
    MASK = "MASK"
    DENY = "DENY"


@dataclass(slots=True)
class FieldEvaluationResult:
    field: str
    decision: FieldDecision


class PolicyBackend(Protocol):
    """Pluggable policy backend interface for RBAC/policy checks."""

    def is_resource_allowed(self, resource: str, action: ResourceAction, ctx: AuthContext) -> bool:
        ...

    def evaluate_field_read(self, resource: str, field: str, ctx: AuthContext) -> FieldDecision:
        ...

    def can_edit_field(self, resource: str, field: str, ctx: AuthContext) -> bool:
        ...


class InMemoryPolicyBackend:
    """Role + direct-permission policy backend with wildcard support."""

    def __init__(self, role_permissions: dict[str, set[str]] | None = None, *, default_allow: bool = True) -> None:
        self._role_permissions = role_permissions or {}
        self._default_allow = default_allow

    def is_resource_allowed(self, resource: str, action: ResourceAction, ctx: AuthContext) -> bool:
        if self._default_allow:
            return True
        required = f"{resource}.{action.value}"
        return self._has_permission(required, ctx)

    def evaluate_field_read(self, resource: str, field: str, ctx: AuthContext) -> FieldDecision:
        if self._default_allow:
            return FieldDecision.ALLOW

        mask_permission = f"{resource}.{FieldAction.MASK.value}:{field}"
        allow_permission = f"{resource}.{FieldAction.READ.value}:{field}"

        if self._has_permission(mask_permission, ctx):
            return FieldDecision.MASK
        if self._has_permission(allow_permission, ctx):
            return FieldDecision.ALLOW
        return FieldDecision.DENY

    def can_edit_field(self, resource: str, field: str, ctx: AuthContext) -> bool:
        if self._default_allow:
            return True

        edit_permission = f"{resource}.{FieldAction.EDIT.value}:{field}"
        return self._has_permission(edit_permission, ctx)

    def _has_permission(self, required: str, ctx: AuthContext) -> bool:
        grants = set(ctx.permissions)
        for role in ctx.roles:
            grants.update(self._role_permissions.get(role, set()))

        return any(self._matches(grant, required) for grant in grants)

    @staticmethod
    def _matches(grant: str, required: str) -> bool:
        if grant in {"*", required}:
            return True

        if grant.endswith(".*"):
            return required.startswith(grant[:-1])

        if ":" in grant and grant.endswith(":*"):
            return required.startswith(grant[:-1])

        return False


@dataclass(slots=True)
class _DbPermissionRule:
    resource: str
    action: str
    field: str | None
    effect: str


class DbPolicyBackend:
    """Policy backend that resolves role permissions from the database."""

    CACHE_KEY = "authz.db_policy"

    def __init__(self, session_factory: sessionmaker[Session] | None = None, *, default_allow: bool = True) -> None:
        self._session_factory = session_factory or SessionLocal
        self._default_allow = default_allow

    def is_resource_allowed(self, resource: str, action: ResourceAction, ctx: AuthContext) -> bool:
        grants = self._load_grants(ctx)
        if grants["empty"]:
            return self._default_allow

        decision = self._evaluate_action_rules(grants["rules"], resource=resource, action=action.value)
        if decision == "deny":
            return False
        if decision == "allow":
            return True
        return False

    def evaluate_field_read(self, resource: str, field: str, ctx: AuthContext) -> FieldDecision:
        grants = self._load_grants(ctx)
        if grants["empty"]:
            return FieldDecision.ALLOW if self._default_allow else FieldDecision.DENY

        read_decision = self._evaluate_field_rules(grants["rules"], resource=resource, action=FieldAction.READ.value, field=field)
        if read_decision == "deny":
            return FieldDecision.DENY

        mask_decision = self._evaluate_field_rules(grants["rules"], resource=resource, action=FieldAction.MASK.value, field=field)
        if mask_decision == "deny":
            return FieldDecision.DENY
        if mask_decision == "allow":
            return FieldDecision.MASK

        if read_decision == "allow":
            return FieldDecision.ALLOW
        return FieldDecision.DENY

    def can_edit_field(self, resource: str, field: str, ctx: AuthContext) -> bool:
        grants = self._load_grants(ctx)
        if grants["empty"]:
            return self._default_allow

        decision = self._evaluate_field_rules(grants["rules"], resource=resource, action=FieldAction.EDIT.value, field=field)
        if decision == "deny":
            return False
        if decision == "allow":
            return True
        return False

    def _load_grants(self, ctx: AuthContext) -> dict[str, Any]:
        cache = ctx._cache.get(self.CACHE_KEY)
        if isinstance(cache, dict):
            observe_authz_policy_cache_hit()
            return cache

        observe_authz_policy_cache_miss()
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    Role.id,
                    Role.name,
                    Permission.resource,
                    Permission.action,
                    Permission.field,
                    Permission.effect,
                )
                .select_from(UserRole)
                .join(Role, UserRole.role_id == Role.id)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(UserRole.user_id == ctx.user_id)
            ).all()
            observe_authz_db_queries_count(1)

        rules = [
            _DbPermissionRule(
                resource=str(row.resource),
                action=str(row.action),
                field=str(row.field) if row.field is not None else None,
                effect=str(row.effect).lower(),
            )
            for row in rows
        ]

        role_names = sorted({str(row.name) for row in rows})
        role_ids = sorted({str(row.id) for row in rows})
        if role_names and not ctx.roles:
            ctx.roles = role_names
        ctx._cache["authz.role_names"] = role_names
        ctx._cache["authz.role_ids"] = role_ids

        payload: dict[str, Any] = {
            "rules": rules,
            "empty": len(rules) == 0,
            "role_names": role_names,
            "role_ids": role_ids,
        }
        ctx._cache[self.CACHE_KEY] = payload
        return payload

    @staticmethod
    def _resource_matches(rule_resource: str, resource: str) -> bool:
        return rule_resource in {"*", resource}

    def _evaluate_action_rules(self, rules: list[_DbPermissionRule], *, resource: str, action: str) -> str | None:
        matched = [rule for rule in rules if self._resource_matches(rule.resource, resource) and rule.action == action]
        if not matched:
            return None
        if any(rule.effect == "deny" for rule in matched):
            return "deny"
        if any(rule.effect == "allow" for rule in matched):
            return "allow"
        return None

    def _evaluate_field_rules(self, rules: list[_DbPermissionRule], *, resource: str, action: str, field: str) -> str | None:
        relevant = [rule for rule in rules if self._resource_matches(rule.resource, resource) and rule.action == action]
        if not relevant:
            return None

        explicit = [rule for rule in relevant if rule.field == field]
        wildcard = [rule for rule in relevant if rule.field == "*"]

        for candidates in (explicit, wildcard):
            if not candidates:
                continue
            if any(rule.effect == "deny" for rule in candidates):
                return "deny"
            if any(rule.effect == "allow" for rule in candidates):
                return "allow"
        return None


_POLICY_BACKEND: PolicyBackend = InMemoryPolicyBackend(default_allow=True)
_POLICY_LOCK = Lock()


def get_policy_backend() -> PolicyBackend:
    """Get the active policy backend instance."""

    return _POLICY_BACKEND


def set_policy_backend(backend: PolicyBackend) -> None:
    """Set the active policy backend instance."""

    global _POLICY_BACKEND
    with _POLICY_LOCK:
        _POLICY_BACKEND = backend
