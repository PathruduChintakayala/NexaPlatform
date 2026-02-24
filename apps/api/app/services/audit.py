from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.models.audit import AuditLog


def write_audit_log(
    db: Session,
    context: RequestContext,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict | None = None,
) -> AuditLog:
    event = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata or {},
        legal_entity=context.legal_entity,
        region=context.region,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
