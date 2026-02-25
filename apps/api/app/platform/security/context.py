from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AuthContext:
    """Authorization context used by policy evaluation and FLS checks."""

    user_id: str
    tenant_id: str | None = None
    correlation_id: str | None = None
    is_super_admin: bool = False
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    entity_scope: list[str] = field(default_factory=list)
    region_scope: list[str] = field(default_factory=list)
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)
