from __future__ import annotations

from typing import Any

from app.context import get_correlation_id, get_workflow_depth
from app.core.events import event_bus

published_events: list[dict[str, Any]] = []


def publish(envelope: dict[str, Any]) -> None:
    if envelope.get("correlation_id") is None:
        envelope["correlation_id"] = get_correlation_id()

    existing_meta = envelope.get("meta")
    meta: dict[str, Any] = existing_meta.copy() if isinstance(existing_meta, dict) else {}
    workflow_depth = get_workflow_depth()
    if workflow_depth is not None and "workflow_depth" not in meta:
        meta["workflow_depth"] = workflow_depth
    if meta:
        envelope["meta"] = meta

    published_events.append(envelope)
    event_type = envelope.get("event_type")
    if isinstance(event_type, str) and event_type:
        event_bus.publish(event_type, envelope)
