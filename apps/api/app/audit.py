from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.context import get_correlation_id

audit_entries: list[dict[str, Any]] = []


def record(
    actor_user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    correlation_id: str | None = None,
) -> None:
    resolved_correlation_id = correlation_id or get_correlation_id()
    audit_entries.append(
        {
            "id": str(uuid.uuid4()),
            "actor_user_id": actor_user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "before": before,
            "after": after,
            "correlation_id": resolved_correlation_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
    )
