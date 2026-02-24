from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app import events
from app.crm.models import CRMAccount, CRMAccountLegalEntity, CRMContact, CRMLead, CRMOpportunity


class SearchActor(Protocol):
    user_id: str
    allowed_legal_entity_ids: list[uuid.UUID]
    permissions: set[str]
    correlation_id: str | None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def build_search_doc_for_account(account: CRMAccount, custom_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = {
        "title": account.name,
        "subtitle": account.status,
        "name": account.name,
        "status": account.status,
        "owner_user_id": _string_or_none(account.owner_user_id),
        "primary_region_code": account.primary_region_code,
        "default_currency_code": account.default_currency_code,
        "external_reference": account.external_reference,
    }
    if custom_fields:
        doc["custom_fields"] = custom_fields
    return doc


def build_search_doc_for_contact(contact: CRMContact, custom_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    full_name = " ".join(part for part in [contact.first_name, contact.last_name] if part)
    doc = {
        "title": full_name,
        "subtitle": contact.email,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "full_name": full_name,
        "email": contact.email,
        "phone": contact.phone,
        "title_text": contact.title,
        "department": contact.department,
        "account_id": str(contact.account_id),
    }
    if custom_fields:
        doc["custom_fields"] = custom_fields
    return doc


def build_search_doc_for_lead(lead: CRMLead, custom_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    full_name = " ".join(part for part in [lead.contact_first_name, lead.contact_last_name] if part)
    doc = {
        "title": lead.company_name or full_name or "Lead",
        "subtitle": lead.status,
        "company_name": lead.company_name,
        "contact_name": full_name or None,
        "email": lead.email,
        "phone": lead.phone,
        "status": lead.status,
        "source": lead.source,
        "owner_user_id": _string_or_none(lead.owner_user_id),
    }
    if custom_fields:
        doc["custom_fields"] = custom_fields
    return doc


def build_search_doc_for_opportunity(
    opportunity: CRMOpportunity,
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = {
        "title": opportunity.name,
        "subtitle": opportunity.forecast_category,
        "name": opportunity.name,
        "amount": float(opportunity.amount),
        "currency_code": opportunity.currency_code,
        "forecast_category": opportunity.forecast_category,
        "account_id": str(opportunity.account_id),
        "owner_user_id": _string_or_none(opportunity.owner_user_id),
        "expected_close_date": opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else None,
    }
    if custom_fields:
        doc["custom_fields"] = custom_fields
    return doc


def publish_index_requested(
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    operation: str,
    fields: dict[str, Any],
    legal_entity_id: uuid.UUID | None,
    actor_user_id: str,
    correlation_id: str | None,
) -> None:
    events.publish(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "crm.search.index_requested",
            "occurred_at": _utcnow_iso(),
            "actor_user_id": actor_user_id,
            "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
            "correlation_id": correlation_id,
            "version": 1,
            "payload": {
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "operation": operation,
                "fields": fields,
            },
        }
    )


def search_entities(
    session: Session,
    actor_user: SearchActor,
    query: str,
    types: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    normalized = query.strip().lower()
    if not normalized:
        return []

    pattern = f"%{normalized}%"
    read_all = {
        "account": "crm.accounts.read_all" in actor_user.permissions,
        "contact": "crm.contacts.read_all" in actor_user.permissions,
        "lead": "crm.leads.read_all" in actor_user.permissions,
        "opportunity": "crm.opportunities.read_all" in actor_user.permissions,
    }
    allowed = set(actor_user.allowed_legal_entity_ids)

    results: list[dict[str, Any]] = []

    if "account" in types:
        stmt: Select[tuple[CRMAccount, uuid.UUID | None]] = (
            select(CRMAccount, CRMAccountLegalEntity.legal_entity_id)
            .join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id)
            .where(
                and_(
                    CRMAccount.deleted_at.is_(None),
                    or_(
                        func.lower(CRMAccount.name).like(pattern),
                        func.lower(func.coalesce(CRMAccount.external_reference, "")).like(pattern),
                    ),
                )
            )
        )
        if not read_all["account"]:
            if not allowed:
                stmt = stmt.where(False)
            else:
                stmt = stmt.where(CRMAccountLegalEntity.legal_entity_id.in_(allowed))

        rows = session.execute(stmt.order_by(CRMAccount.updated_at.desc()).limit(limit)).all()
        for account, legal_entity_id in rows:
            results.append(
                {
                    "entity_type": "account",
                    "entity_id": str(account.id),
                    "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
                    "title": account.name,
                    "subtitle": account.status,
                    "updated_at": account.updated_at.isoformat(),
                }
            )

    if "contact" in types:
        stmt_c: Select[tuple[CRMContact, uuid.UUID | None]] = (
            select(CRMContact, CRMAccountLegalEntity.legal_entity_id)
            .join(CRMAccount, CRMAccount.id == CRMContact.account_id)
            .join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id)
            .where(
                and_(
                    CRMContact.deleted_at.is_(None),
                    CRMAccount.deleted_at.is_(None),
                    or_(
                        func.lower(CRMContact.first_name).like(pattern),
                        func.lower(CRMContact.last_name).like(pattern),
                        func.lower(func.coalesce(CRMContact.email, "")).like(pattern),
                    ),
                )
            )
        )
        if not read_all["contact"]:
            if not allowed:
                stmt_c = stmt_c.where(False)
            else:
                stmt_c = stmt_c.where(CRMAccountLegalEntity.legal_entity_id.in_(allowed))

        rows_c = session.execute(stmt_c.order_by(CRMContact.updated_at.desc()).limit(limit)).all()
        for contact, legal_entity_id in rows_c:
            full_name = " ".join(part for part in [contact.first_name, contact.last_name] if part)
            results.append(
                {
                    "entity_type": "contact",
                    "entity_id": str(contact.id),
                    "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
                    "title": full_name,
                    "subtitle": contact.email,
                    "updated_at": contact.updated_at.isoformat(),
                }
            )

    if "lead" in types:
        stmt_l: Select[tuple[CRMLead]] = select(CRMLead).where(
            and_(
                CRMLead.deleted_at.is_(None),
                or_(
                    func.lower(func.coalesce(CRMLead.company_name, "")).like(pattern),
                    func.lower(func.coalesce(CRMLead.email, "")).like(pattern),
                    func.lower(func.coalesce(CRMLead.contact_first_name, "")).like(pattern),
                    func.lower(func.coalesce(CRMLead.contact_last_name, "")).like(pattern),
                ),
            )
        )
        if not read_all["lead"]:
            if not allowed:
                stmt_l = stmt_l.where(False)
            else:
                stmt_l = stmt_l.where(CRMLead.selling_legal_entity_id.in_(allowed))

        rows_l = session.scalars(stmt_l.order_by(CRMLead.updated_at.desc()).limit(limit)).all()
        for lead in rows_l:
            results.append(
                {
                    "entity_type": "lead",
                    "entity_id": str(lead.id),
                    "legal_entity_id": str(lead.selling_legal_entity_id),
                    "title": lead.company_name or "Lead",
                    "subtitle": lead.status,
                    "updated_at": lead.updated_at.isoformat(),
                }
            )

    if "opportunity" in types:
        stmt_o: Select[tuple[CRMOpportunity, uuid.UUID | None]] = (
            select(CRMOpportunity, CRMAccountLegalEntity.legal_entity_id)
            .join(CRMAccount, CRMAccount.id == CRMOpportunity.account_id)
            .join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id)
            .where(
                and_(
                    CRMOpportunity.deleted_at.is_(None),
                    CRMAccount.deleted_at.is_(None),
                    func.lower(CRMOpportunity.name).like(pattern),
                )
            )
        )
        if not read_all["opportunity"]:
            if not allowed:
                stmt_o = stmt_o.where(False)
            else:
                stmt_o = stmt_o.where(CRMOpportunity.selling_legal_entity_id.in_(allowed))
                stmt_o = stmt_o.where(CRMAccountLegalEntity.legal_entity_id.in_(allowed))

        rows_o = session.execute(stmt_o.order_by(CRMOpportunity.updated_at.desc()).limit(limit)).all()
        for opportunity, legal_entity_id in rows_o:
            results.append(
                {
                    "entity_type": "opportunity",
                    "entity_id": str(opportunity.id),
                    "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
                    "title": opportunity.name,
                    "subtitle": opportunity.forecast_category,
                    "updated_at": opportunity.updated_at.isoformat(),
                }
            )

    results.sort(key=lambda item: item["updated_at"], reverse=True)
    return results[:limit]
