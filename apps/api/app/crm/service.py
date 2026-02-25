from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import Select, and_, func, inspect, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import audit, events
from app.context import reset_correlation_id, reset_workflow_depth, set_correlation_id, set_workflow_depth
from app.metrics import observe_job, observe_workflow_guardrail_block
from app.core.config import get_settings
from app.crm.repositories import ContactRepository
from app.crm.models import (
    CRMAccount,
    CRMAccountLegalEntity,
    CRMActivity,
    CRMAttachmentLink,
    CRMContact,
    CRMCustomFieldDefinition,
    CRMCustomFieldValue,
    CRMIdempotencyKey,
    CRMLead,
    CRMNote,
    CRMNotificationIntent,
    CRMOpportunity,
    CRMPipeline,
    CRMPipelineStage,
    CRMJob,
    CRMJobArtifact,
    CRMRevOrder,
    CRMRevQuote,
    CRMWorkflowRule,
)
from app.revenue.client import RevenueClient, StubRevenueClient
from app.platform.security.context import AuthContext
from app.platform.security.errors import AuthorizationError, ForbiddenFieldError
from app.platform.security.fls import validate_fls_write
from app.platform.security.rls import validate_rls_write
from app.crm.search import (
    build_search_doc_for_account,
    build_search_doc_for_contact,
    build_search_doc_for_lead,
    build_search_doc_for_opportunity,
    publish_index_requested,
)
from app.crm.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionRead,
    CustomFieldDefinitionUpdate,
    LeadConvertRequest,
    LeadCreate,
    LeadDisqualifyRequest,
    LeadRead,
    LeadUpdate,
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    AttachmentLinkCreate,
    AttachmentLinkRead,
    CompleteActivityRequest,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    OpportunityChangeStageRequest,
    OpportunityCloseLostRequest,
    OpportunityCloseWonRequest,
    OpportunityCreate,
    OpportunityRead,
    OpportunityReopenRequest,
    OpportunityUpdate,
    PipelineCreate,
    PipelineRead,
    PipelineStageCreate,
    PipelineStageRead,
    AuditRead,
    RevenueDocStatusRead,
    OpportunityRevenueRead,
    WorkflowAction,
    WorkflowActionCreateTask,
    WorkflowActionNotify,
    WorkflowActionSetField,
    WorkflowCondition,
    WorkflowConditionAll,
    WorkflowConditionAny,
    WorkflowConditionLeaf,
    WorkflowConditionNot,
    WorkflowDryRunResponse,
    WorkflowEntityRef,
    WorkflowRuleCreate,
    WorkflowRuleRead,
    WorkflowRuleUpdate,
)


logger = logging.getLogger("app.crm.jobs")
tracer = trace.get_tracer("app.crm.jobs")


class WorkflowLimitExceededError(Exception):
    def __init__(self, code: str, summary: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.summary = summary


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_user_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"nexa-actor:{value}")


@dataclass
class ActorUser:
    user_id: str
    allowed_legal_entity_ids: list[uuid.UUID]
    current_legal_entity_id: uuid.UUID | None
    permissions: set[str]
    allowed_region_codes: list[str] = field(default_factory=list)
    is_super_admin: bool = False
    correlation_id: str | None = None


def _to_auth_context(actor_user: ActorUser, *, tenant_id: str | None = None) -> AuthContext:
    resolved_tenant = tenant_id
    if resolved_tenant is None and actor_user.current_legal_entity_id is not None:
        resolved_tenant = str(actor_user.current_legal_entity_id)

    cache_key = actor_user.correlation_id or "request"
    cached = getattr(actor_user, "_authz_cache", None)
    cached_key = getattr(actor_user, "_authz_cache_key", None)
    if not isinstance(cached, dict) or cached_key != cache_key:
        cached = {}
        setattr(actor_user, "_authz_cache", cached)
        setattr(actor_user, "_authz_cache_key", cache_key)

    return AuthContext(
        user_id=actor_user.user_id,
        tenant_id=resolved_tenant,
        correlation_id=actor_user.correlation_id,
        is_super_admin=actor_user.is_super_admin,
        roles=[],
        permissions=sorted(actor_user.permissions),
        entity_scope=[str(item) for item in actor_user.allowed_legal_entity_ids],
        region_scope=sorted(set(actor_user.allowed_region_codes)),
        _cache=cached,
    )


def _actor_with_correlation_id(actor_user: ActorUser, correlation_id: str | None) -> ActorUser:
    return ActorUser(
        user_id=actor_user.user_id,
        allowed_legal_entity_ids=actor_user.allowed_legal_entity_ids,
        current_legal_entity_id=actor_user.current_legal_entity_id,
        permissions=actor_user.permissions,
        allowed_region_codes=actor_user.allowed_region_codes,
        is_super_admin=actor_user.is_super_admin,
        correlation_id=correlation_id,
    )


VALID_CUSTOM_FIELD_ENTITY_TYPES = {"account", "contact", "lead", "opportunity"}
VALID_CUSTOM_FIELD_DATA_TYPES = {"text", "number", "bool", "date", "select"}
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CustomFieldService:
    def list_definitions(
        self,
        session: Session,
        entity_type: str,
        actor_user: ActorUser,
        legal_entity_id: uuid.UUID | None = None,
        include_inactive: bool = False,
    ) -> list[CustomFieldDefinitionRead]:
        self._validate_entity_type(entity_type)
        if legal_entity_id is not None:
            self._enforce_legal_entity_access(actor_user, legal_entity_id)

        stmt: Select[tuple[CRMCustomFieldDefinition]] = select(CRMCustomFieldDefinition).where(
            CRMCustomFieldDefinition.entity_type == entity_type
        )
        if not include_inactive:
            stmt = stmt.where(CRMCustomFieldDefinition.is_active.is_(True))

        if legal_entity_id is None:
            stmt = stmt.where(CRMCustomFieldDefinition.legal_entity_id.is_(None))
        else:
            stmt = stmt.where(
                or_(
                    CRMCustomFieldDefinition.legal_entity_id.is_(None),
                    CRMCustomFieldDefinition.legal_entity_id == legal_entity_id,
                )
            )

        definitions = session.scalars(stmt.order_by(CRMCustomFieldDefinition.field_key.asc())).all()
        resolved = self._resolve_definition_priority(definitions, legal_entity_id)
        return [self._to_definition_read(item) for item in sorted(resolved.values(), key=lambda row: row.field_key)]

    def create_definition(
        self,
        session: Session,
        entity_type: str,
        dto: CustomFieldDefinitionCreate,
        actor_user: ActorUser,
    ) -> CustomFieldDefinitionRead:
        self._validate_entity_type(entity_type)
        self._enforce_manage_permission(actor_user)

        field_key = dto.field_key.strip()
        if not FIELD_KEY_RE.match(field_key):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="field_key must be snake_case")
        if dto.data_type not in VALID_CUSTOM_FIELD_DATA_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid data_type")
        self._validate_allowed_values(dto.data_type, dto.allowed_values)
        if dto.legal_entity_id is not None:
            self._enforce_legal_entity_access(actor_user, dto.legal_entity_id)

        existing = session.scalar(
            select(CRMCustomFieldDefinition).where(
                and_(
                    CRMCustomFieldDefinition.entity_type == entity_type,
                    CRMCustomFieldDefinition.field_key == field_key,
                    CRMCustomFieldDefinition.legal_entity_id == dto.legal_entity_id,
                )
            )
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="custom field definition already exists")

        definition = CRMCustomFieldDefinition(
            entity_type=entity_type,
            field_key=field_key,
            label=dto.label.strip(),
            data_type=dto.data_type,
            is_required=dto.is_required,
            allowed_values=dto.allowed_values,
            legal_entity_id=dto.legal_entity_id,
            is_active=dto.is_active,
        )
        session.add(definition)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="custom field definition already exists")
        session.refresh(definition)
        return self._to_definition_read(definition)

    def update_definition(
        self,
        session: Session,
        definition_id: uuid.UUID,
        dto: CustomFieldDefinitionUpdate,
        actor_user: ActorUser,
    ) -> CustomFieldDefinitionRead:
        self._enforce_manage_permission(actor_user)
        definition = session.scalar(select(CRMCustomFieldDefinition).where(CRMCustomFieldDefinition.id == definition_id))
        if definition is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="custom field definition not found")

        payload = dto.model_dump(exclude_unset=True)
        if "allowed_values" in payload:
            self._validate_allowed_values(definition.data_type, payload["allowed_values"])

        for key in ["label", "is_required", "allowed_values", "is_active"]:
            if key in payload:
                setattr(definition, key, payload[key])
        definition.updated_at = utcnow()
        session.add(definition)
        session.commit()
        session.refresh(definition)
        return self._to_definition_read(definition)

    def set_values_for_entity(
        self,
        session: Session,
        entity_type: str,
        entity_id: uuid.UUID,
        custom_fields_dict: dict[str, Any],
        legal_entity_context: uuid.UUID | None,
        *,
        enforce_required: bool,
    ) -> dict[str, Any]:
        self._validate_entity_type(entity_type)
        provided = custom_fields_dict or {}
        definitions = self._load_active_definitions(session, entity_type, legal_entity_context)

        unknown = [key for key in provided.keys() if key not in definitions]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown custom fields: {', '.join(sorted(unknown))}",
            )

        existing_rows = session.scalars(
            select(CRMCustomFieldValue).where(
                and_(
                    CRMCustomFieldValue.entity_type == entity_type,
                    CRMCustomFieldValue.entity_id == entity_id,
                )
            )
        ).all()
        existing_map = {row.field_key: row for row in existing_rows}

        for key, value in provided.items():
            definition = definitions[key]
            existing = existing_map.get(key)

            if value is None:
                if existing is not None:
                    session.delete(existing)
                continue

            validated = self._validate_custom_value(definition, value)
            if existing is None:
                existing = CRMCustomFieldValue(entity_type=entity_type, entity_id=entity_id, field_key=key)
            existing.value_text = validated.get("value_text")
            existing.value_number = validated.get("value_number")
            existing.value_bool = validated.get("value_bool")
            existing.value_date = validated.get("value_date")
            existing.updated_at = utcnow()
            session.add(existing)

        session.flush()
        if enforce_required:
            self._enforce_required_values(session, entity_type, entity_id, definitions)
        return self.get_values_for_entity(session, entity_type, entity_id)

    def get_values_for_entity(self, session: Session, entity_type: str, entity_id: uuid.UUID) -> dict[str, Any]:
        self._validate_entity_type(entity_type)
        rows = session.scalars(
            select(CRMCustomFieldValue).where(
                and_(CRMCustomFieldValue.entity_type == entity_type, CRMCustomFieldValue.entity_id == entity_id)
            )
        ).all()
        output: dict[str, Any] = {}
        for row in rows:
            output[row.field_key] = self._deserialize_value(row)
        return output

    def get_search_values_for_entity(self, session: Session, entity_type: str, entity_id: uuid.UUID) -> dict[str, str]:
        values = self.get_values_for_entity(session, entity_type, entity_id)
        search_values: dict[str, str] = {}
        for key, value in values.items():
            if isinstance(value, str):
                search_values[key] = value
            else:
                search_values[key] = str(value)
        return search_values

    def ensure_required_fields(
        self,
        session: Session,
        entity_type: str,
        entity_id: uuid.UUID,
        legal_entity_context: uuid.UUID | None,
    ) -> None:
        definitions = self._load_active_definitions(session, entity_type, legal_entity_context)
        self._enforce_required_values(session, entity_type, entity_id, definitions)

    def _load_active_definitions(
        self,
        session: Session,
        entity_type: str,
        legal_entity_id: uuid.UUID | None,
    ) -> dict[str, CRMCustomFieldDefinition]:
        stmt: Select[tuple[CRMCustomFieldDefinition]] = select(CRMCustomFieldDefinition).where(
            and_(
                CRMCustomFieldDefinition.entity_type == entity_type,
                CRMCustomFieldDefinition.is_active.is_(True),
            )
        )
        if legal_entity_id is None:
            stmt = stmt.where(CRMCustomFieldDefinition.legal_entity_id.is_(None))
        else:
            stmt = stmt.where(
                or_(
                    CRMCustomFieldDefinition.legal_entity_id.is_(None),
                    CRMCustomFieldDefinition.legal_entity_id == legal_entity_id,
                )
            )

        definitions = session.scalars(stmt).all()
        return self._resolve_definition_priority(definitions, legal_entity_id)

    def _resolve_definition_priority(
        self,
        definitions: list[CRMCustomFieldDefinition],
        legal_entity_id: uuid.UUID | None,
    ) -> dict[str, CRMCustomFieldDefinition]:
        resolved: dict[str, CRMCustomFieldDefinition] = {}
        for definition in definitions:
            existing = resolved.get(definition.field_key)
            if existing is None:
                resolved[definition.field_key] = definition
                continue

            existing_specific = existing.legal_entity_id == legal_entity_id and legal_entity_id is not None
            candidate_specific = definition.legal_entity_id == legal_entity_id and legal_entity_id is not None
            if candidate_specific and not existing_specific:
                resolved[definition.field_key] = definition
        return resolved

    def _enforce_required_values(
        self,
        session: Session,
        entity_type: str,
        entity_id: uuid.UUID,
        definitions: dict[str, CRMCustomFieldDefinition],
    ) -> None:
        required_keys = [key for key, definition in definitions.items() if definition.is_required]
        if not required_keys:
            return

        existing_values = self.get_values_for_entity(session, entity_type, entity_id)
        missing = [key for key in required_keys if key not in existing_values or existing_values[key] in (None, "")]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"missing required custom fields: {', '.join(sorted(missing))}",
            )

    def _validate_custom_value(self, definition: CRMCustomFieldDefinition, value: Any) -> dict[str, Any]:
        data_type = definition.data_type
        if data_type == "text":
            if not isinstance(value, str):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{definition.field_key} must be text")
            return {"value_text": value}

        if data_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{definition.field_key} must be number")
            return {"value_number": Decimal(str(value))}

        if data_type == "bool":
            if not isinstance(value, bool):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{definition.field_key} must be bool")
            return {"value_bool": value}

        if data_type == "date":
            if isinstance(value, date):
                return {"value_date": value}
            if isinstance(value, str):
                try:
                    return {"value_date": date.fromisoformat(value)}
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"{definition.field_key} must be ISO date",
                    )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{definition.field_key} must be date")

        if data_type == "select":
            if not isinstance(value, str):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{definition.field_key} must be text")
            allowed = definition.allowed_values or []
            if value not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{definition.field_key} must be one of: {', '.join(allowed)}",
                )
            return {"value_text": value}

        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported custom field data_type")

    def _deserialize_value(self, value_row: CRMCustomFieldValue) -> Any:
        if value_row.value_text is not None:
            return value_row.value_text
        if value_row.value_number is not None:
            return float(value_row.value_number)
        if value_row.value_bool is not None:
            return value_row.value_bool
        if value_row.value_date is not None:
            return value_row.value_date.isoformat()
        return None

    def _validate_entity_type(self, entity_type: str) -> None:
        if entity_type not in VALID_CUSTOM_FIELD_ENTITY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid entity_type")

    def _validate_allowed_values(self, data_type: str, allowed_values: list[str] | None) -> None:
        if data_type == "select":
            if not allowed_values:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="allowed_values required for select",
                )
            if any(not isinstance(item, str) or not item.strip() for item in allowed_values):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="allowed_values must be non-empty strings",
                )
            return
        if allowed_values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="allowed_values only supported for select",
            )

    def _enforce_manage_permission(self, actor_user: ActorUser) -> None:
        if "crm.custom_fields.manage" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: crm.custom_fields.manage")

    def _enforce_legal_entity_access(self, actor_user: ActorUser, legal_entity_id: uuid.UUID) -> None:
        if legal_entity_id not in set(actor_user.allowed_legal_entity_ids) and "crm.custom_fields.manage" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="legal entity not allowed")

    def _to_definition_read(self, definition: CRMCustomFieldDefinition) -> CustomFieldDefinitionRead:
        return CustomFieldDefinitionRead.model_validate(definition)


custom_field_service = CustomFieldService()
contact_repository = ContactRepository()


class AccountService:
    entity_type = "crm.account"

    def create_account(
        self,
        session: Session,
        actor_user_id: str,
        dto: AccountCreate,
        *,
        legal_entity_ids: list[uuid.UUID] | None = None,
        current_legal_entity_id: uuid.UUID | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> AccountRead:
        if not dto.name.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required")

        selected_legal_entity_ids = legal_entity_ids if legal_entity_ids is not None else dto.legal_entity_ids
        if not selected_legal_entity_ids:
            if current_legal_entity_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="At least one legal_entity_id is required",
                )
            selected_legal_entity_ids = [current_legal_entity_id]

        unique_legal_entity_ids = list(dict.fromkeys(selected_legal_entity_ids))

        account = CRMAccount(
            name=dto.name.strip(),
            status="Active",
            owner_user_id=dto.owner_user_id,
            primary_region_code=dto.primary_region_code,
            default_currency_code=dto.default_currency_code,
            external_reference=dto.external_reference,
        )
        session.add(account)
        session.flush()

        for index, legal_entity_id in enumerate(unique_legal_entity_ids):
            session.add(
                CRMAccountLegalEntity(
                    account_id=account.id,
                    legal_entity_id=legal_entity_id,
                    relationship_type="customer",
                    is_default=index == 0,
                )
            )

        session.flush()
        session.refresh(account)
        scope_legal_entity = current_legal_entity_id or unique_legal_entity_ids[0]
        custom_fields = custom_field_service.set_values_for_entity(
            session,
            "account",
            account.id,
            dto.custom_fields,
            scope_legal_entity,
            enforce_required=True,
        )

        after_payload = {
            "name": account.name,
            "status": account.status,
            "owner_user_id": str(account.owner_user_id) if account.owner_user_id else None,
            "primary_region_code": account.primary_region_code,
            "default_currency_code": account.default_currency_code,
            "external_reference": account.external_reference,
            "legal_entity_ids": [str(item) for item in unique_legal_entity_ids],
            "custom_fields": custom_fields,
            "idempotency_key": idempotency_key,
        }
        audit.record(
            actor_user_id=actor_user_id,
            entity_type=self.entity_type,
            entity_id=str(account.id),
            action="create",
            before=None,
            after=after_payload,
            correlation_id=correlation_id,
        )

        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": "crm.account.created",
            "occurred_at": utcnow().isoformat(),
            "actor_user_id": actor_user_id,
            "legal_entity_id": str(unique_legal_entity_ids[0]),
            "payload": {
                "account_id": str(account.id),
                "name": account.name,
                "status": account.status,
            },
        }
        events.publish(envelope)
        publish_index_requested(
            entity_type="account",
            entity_id=account.id,
            operation="upsert",
            fields=build_search_doc_for_account(
                account,
                custom_field_service.get_search_values_for_entity(session, "account", account.id),
            ),
            legal_entity_id=unique_legal_entity_ids[0],
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        session.commit()

        return self._to_read_model(session, account.id)

    def list_accounts(
        self,
        session: Session,
        actor_user: ActorUser,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> list[AccountRead]:
        stmt: Select[tuple[CRMAccount]] = select(CRMAccount).where(CRMAccount.deleted_at.is_(None))
        stmt = stmt.options(selectinload(CRMAccount.legal_entities)).distinct()

        name_filter = filters.get("name")
        if name_filter:
            stmt = stmt.where(CRMAccount.name.ilike(f"%{name_filter}%"))
        if filters.get("status"):
            stmt = stmt.where(CRMAccount.status == filters["status"])
        if filters.get("owner_user_id"):
            stmt = stmt.where(CRMAccount.owner_user_id == filters["owner_user_id"])

        if "crm.accounts.read_all" not in actor_user.permissions:
            if not actor_user.allowed_legal_entity_ids:
                return []
            stmt = stmt.join(CRMAccountLegalEntity, CRMAccountLegalEntity.account_id == CRMAccount.id).where(
                CRMAccountLegalEntity.legal_entity_id.in_(actor_user.allowed_legal_entity_ids)
            )

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        stmt = stmt.order_by(CRMAccount.created_at.desc()).offset(offset).limit(limit)

        accounts = session.scalars(stmt).all()
        return [self._to_read_model(session, account.id) for account in accounts]

    def get_account(self, session: Session, actor_user: ActorUser, account_id: uuid.UUID) -> AccountRead:
        account = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == account_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

        if not self._can_view(actor_user, account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

        return self._to_read_model(session, account.id)

    def update_account(
        self,
        session: Session,
        actor_user: ActorUser,
        account_id: uuid.UUID,
        dto: AccountUpdate,
    ) -> AccountRead:
        existing = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == account_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if existing is None or not self._can_view(actor_user, existing):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

        before = self._to_read(
            existing,
            custom_field_service.get_values_for_entity(session, "account", existing.id),
        ).model_dump(mode="json")

        changes: dict[str, Any] = {}
        if dto.name is not None:
            if not dto.name.strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name cannot be empty")
            changes["name"] = dto.name.strip()
        if dto.status is not None:
            changes["status"] = dto.status
        if dto.owner_user_id is not None:
            changes["owner_user_id"] = dto.owner_user_id
        if dto.primary_region_code is not None:
            changes["primary_region_code"] = dto.primary_region_code
        if dto.default_currency_code is not None:
            changes["default_currency_code"] = dto.default_currency_code
        if dto.external_reference is not None:
            changes["external_reference"] = dto.external_reference

        custom_fields_provided = "custom_fields" in dto.model_fields_set
        if not changes and not custom_fields_provided:
            return self._to_read_model(session, existing.id)

        changes["updated_at"] = utcnow()
        changes["row_version"] = CRMAccount.row_version + 1

        result = session.execute(
            update(CRMAccount)
            .where(
                and_(
                    CRMAccount.id == account_id,
                    CRMAccount.row_version == dto.row_version,
                    CRMAccount.deleted_at.is_(None),
                )
            )
            .values(**changes)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated = session.scalar(
            select(CRMAccount)
            .where(CRMAccount.id == account_id)
            .options(selectinload(CRMAccount.legal_entities))
        )
        if updated is None:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

        if custom_fields_provided:
            account_scope = actor_user.current_legal_entity_id
            if account_scope is None and updated.legal_entities:
                account_scope = updated.legal_entities[0].legal_entity_id
            custom_field_service.set_values_for_entity(
                session,
                "account",
                updated.id,
                dto.custom_fields,
                account_scope,
                enforce_required=False,
            )

        updated_custom_fields = custom_field_service.get_values_for_entity(session, "account", updated.id)
        after = self._to_read(updated, updated_custom_fields).model_dump(mode="json")
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(updated.id),
            action="update",
            before=before,
            after=after,
            correlation_id=actor_user.correlation_id,
        )

        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.account.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(updated.legal_entities[0].legal_entity_id),
                "payload": {
                    "account_id": str(updated.id),
                    "row_version": updated.row_version,
                },
            }
        )
        publish_index_requested(
            entity_type="account",
            entity_id=updated.id,
            operation="upsert",
            fields=build_search_doc_for_account(
                updated,
                custom_field_service.get_search_values_for_entity(session, "account", updated.id),
            ),
            legal_entity_id=updated.legal_entities[0].legal_entity_id if updated.legal_entities else None,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()

        return self._to_read_model(session, account_id)

    def soft_delete_account(
        self,
        session: Session,
        actor_user: ActorUser,
        account_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> None:
        account = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == account_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None or not self._can_view(actor_user, account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")

        dependencies = self._count_dependencies(session, account_id)
        if not force and (dependencies["contacts"] > 0 or dependencies["opportunities"] > 0):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Account has dependencies", "dependencies": dependencies},
            )

        account.deleted_at = utcnow()
        account.updated_at = utcnow()
        account.row_version = account.row_version + 1
        session.add(account)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(account.id),
            action="soft_delete",
            before={"deleted_at": None},
            after={"deleted_at": account.deleted_at.isoformat()},
            correlation_id=actor_user.correlation_id,
        )

        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.account.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(account.legal_entities[0].legal_entity_id),
                "payload": {
                    "account_id": str(account.id),
                    "deleted_at": account.deleted_at.isoformat(),
                },
            }
        )
        publish_index_requested(
            entity_type="account",
            entity_id=account.id,
            operation="delete",
            fields={},
            legal_entity_id=account.legal_entities[0].legal_entity_id if account.legal_entities else None,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()

    def _to_read_model(self, session: Session, account_id: uuid.UUID) -> AccountRead:
        account = session.scalar(
            select(CRMAccount).where(CRMAccount.id == account_id).options(selectinload(CRMAccount.legal_entities))
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
        custom_fields = custom_field_service.get_values_for_entity(session, "account", account.id)
        return self._to_read(account, custom_fields)

    def _to_read(self, account: CRMAccount, custom_fields: dict[str, Any] | None = None) -> AccountRead:
        return AccountRead.model_validate(
            {
                "id": account.id,
                "name": account.name,
                "status": account.status,
                "owner_user_id": account.owner_user_id,
                "primary_region_code": account.primary_region_code,
                "default_currency_code": account.default_currency_code,
                "external_reference": account.external_reference,
                "created_at": account.created_at,
                "updated_at": account.updated_at,
                "deleted_at": account.deleted_at,
                "row_version": account.row_version,
                "legal_entity_ids": [item.legal_entity_id for item in account.legal_entities],
                "custom_fields": custom_fields or {},
            }
        )

    def _can_view(self, actor_user: ActorUser, account: CRMAccount) -> bool:
        if "crm.accounts.read_all" in actor_user.permissions:
            return True
        allowed = set(actor_user.allowed_legal_entity_ids)
        return any(link.legal_entity_id in allowed for link in account.legal_entities)

    def _count_dependencies(self, session: Session, account_id: uuid.UUID) -> dict[str, int]:
        bind = session.get_bind()
        if bind is None:
            return {"contacts": 0, "opportunities": 0}

        inspector = inspect(bind)
        counts = {"contacts": 0, "opportunities": 0}
        table_map = {
            "crm_contact": "contacts",
            "crm_opportunity": "opportunities",
        }

        for table_name, key in table_map.items():
            if inspector.has_table(table_name):
                query = text(f"SELECT count(*) FROM {table_name} WHERE account_id = :account_id")
                counts[key] = int(session.execute(query, {"account_id": account_id}).scalar() or 0)

        return counts


class ContactService:
    entity_type = "crm.contact"

    def create_contact(self, session: Session, actor_user: ActorUser, dto: ContactCreate) -> ContactRead:
        account = self._get_visible_account(session, actor_user, dto.account_id)
        if account.deleted_at is not None or account.status != "Active":
            # TODO: Add feature flag to allow contact creation for inactive accounts with warning.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact cannot be created for deleted or inactive account",
            )

        auth_ctx = _to_auth_context(actor_user)
        existing_scope = {
            "company_code": str(self._first_legal_entity_id(account)),
            "region_code": account.primary_region_code,
        }
        try:
            contact_repository.validate_write_security(
                dto.model_dump(exclude={"account_id"}),
                auth_ctx,
                existing_scope=existing_scope,
                action="create",
            )
        except ForbiddenFieldError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"forbidden_fields": exc.fields})
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        try:
            if dto.is_primary:
                session.execute(
                    update(CRMContact)
                    .where(
                        and_(
                            CRMContact.account_id == account.id,
                            CRMContact.deleted_at.is_(None),
                            CRMContact.is_primary.is_(True),
                        )
                    )
                    .values(is_primary=False, updated_at=utcnow(), row_version=CRMContact.row_version + 1)
                )

            contact = CRMContact(
                account_id=account.id,
                first_name=dto.first_name.strip(),
                last_name=dto.last_name.strip(),
                email=str(dto.email) if dto.email is not None else None,
                phone=dto.phone,
                title=dto.title,
                department=dto.department,
                locale=dto.locale,
                timezone=dto.timezone,
                owner_user_id=dto.owner_user_id,
                is_primary=dto.is_primary,
            )
            session.add(contact)
            session.flush()
            session.refresh(contact)
            contact_scope = actor_user.current_legal_entity_id or self._first_legal_entity_id(account)
            custom_fields = custom_field_service.set_values_for_entity(
                session,
                "contact",
                contact.id,
                dto.custom_fields,
                contact_scope,
                enforce_required=True,
            )
            read_model = self._to_read(contact, custom_fields)

            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type=self.entity_type,
                entity_id=str(contact.id),
                action="create",
                before=None,
                after=read_model.model_dump(mode="json"),
                correlation_id=actor_user.correlation_id,
            )
            events.publish(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "crm.contact.created",
                    "occurred_at": utcnow().isoformat(),
                    "actor_user_id": actor_user.user_id,
                    "legal_entity_id": str(self._first_legal_entity_id(account)),
                    "payload": {
                        "contact_id": str(contact.id),
                        "account_id": str(account.id),
                    },
                }
            )
            publish_index_requested(
                entity_type="contact",
                entity_id=contact.id,
                operation="upsert",
                fields=build_search_doc_for_contact(
                    contact,
                    custom_field_service.get_search_values_for_entity(session, "contact", contact.id),
                ),
                legal_entity_id=self._first_legal_entity_id(account),
                actor_user_id=actor_user.user_id,
                correlation_id=actor_user.correlation_id,
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Primary contact conflict for account",
            )

        return self._to_read_model(session, contact.id, actor_user=actor_user)

    def list_contacts_for_account(
        self,
        session: Session,
        actor_user: ActorUser,
        account_id: uuid.UUID,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
        *,
        include_deleted: bool = False,
    ) -> list[ContactRead]:
        account = self._get_visible_account(session, actor_user, account_id)

        stmt: Select[tuple[CRMContact]] = select(CRMContact).where(CRMContact.account_id == account.id)
        if not include_deleted:
            stmt = stmt.where(CRMContact.deleted_at.is_(None))

        name_filter = filters.get("name")
        if name_filter:
            stmt = stmt.where(
                (CRMContact.first_name.ilike(f"%{name_filter}%")) | (CRMContact.last_name.ilike(f"%{name_filter}%"))
            )
        if filters.get("email"):
            stmt = stmt.where(CRMContact.email.ilike(f"%{filters['email']}%"))
        if filters.get("is_primary") is not None:
            stmt = stmt.where(CRMContact.is_primary.is_(bool(filters["is_primary"])))
        if filters.get("owner_user_id"):
            stmt = stmt.where(CRMContact.owner_user_id == filters["owner_user_id"])

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        stmt = contact_repository.apply_scope_query(stmt, _to_auth_context(actor_user))
        stmt = stmt.order_by(CRMContact.created_at.desc()).offset(offset).limit(limit)
        contacts = session.scalars(stmt).all()
        return [self._to_read_model(session, contact.id, actor_user=actor_user) for contact in contacts]

    def get_contact(self, session: Session, actor_user: ActorUser, contact_id: uuid.UUID) -> ContactRead:
        auth_ctx = _to_auth_context(actor_user)
        query = (
            select(CRMContact)
            .where(and_(CRMContact.id == contact_id, CRMContact.deleted_at.is_(None)))
            .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
        )
        contact = session.scalar(contact_repository.apply_scope_query(query, auth_ctx))
        if contact is None or not self._can_view_account(actor_user, contact.account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")
        return self._to_read_model(session, contact.id, actor_user=actor_user)

    def update_contact(
        self,
        session: Session,
        actor_user: ActorUser,
        contact_id: uuid.UUID,
        dto: ContactUpdate,
    ) -> ContactRead:
        auth_ctx = _to_auth_context(actor_user)
        query = (
            select(CRMContact)
            .where(and_(CRMContact.id == contact_id, CRMContact.deleted_at.is_(None)))
            .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
        )
        contact = session.scalar(contact_repository.apply_scope_query(query, auth_ctx))
        if contact is None or not self._can_view_account(actor_user, contact.account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")

        before = self._to_read(
            contact,
            custom_field_service.get_values_for_entity(session, "contact", contact.id),
        ).model_dump(mode="json")
        changes: dict[str, Any] = {}
        payload = dto.model_dump(exclude_unset=True)
        custom_fields_provided = "custom_fields" in dto.model_fields_set
        custom_fields_payload = payload.pop("custom_fields", {})

        if "first_name" in payload:
            if payload["first_name"] is None or not str(payload["first_name"]).strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="first_name cannot be empty")
            changes["first_name"] = str(payload["first_name"]).strip()
        if "last_name" in payload:
            if payload["last_name"] is None or not str(payload["last_name"]).strip():
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="last_name cannot be empty")
            changes["last_name"] = str(payload["last_name"]).strip()

        for field in ["phone", "title", "department", "locale", "timezone", "owner_user_id", "is_primary"]:
            if field in payload:
                changes[field] = payload[field]
        if "email" in payload:
            changes["email"] = str(payload["email"]) if payload["email"] is not None else None

        write_payload_for_validation = dict(changes)
        if custom_fields_provided:
            write_payload_for_validation["custom_fields"] = custom_fields_payload
        existing_scope = {
            "company_code": str(self._first_legal_entity_id(contact.account)),
            "region_code": contact.account.primary_region_code,
        }
        try:
            contact_repository.validate_write_security(
                write_payload_for_validation,
                auth_ctx,
                existing_scope=existing_scope,
                action="update",
            )
        except ForbiddenFieldError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"forbidden_fields": exc.fields})
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        if not changes and not custom_fields_provided:
            return self._to_read_model(session, contact.id, actor_user=actor_user)

        changes["updated_at"] = utcnow()
        changes["row_version"] = CRMContact.row_version + 1

        try:
            if payload.get("is_primary") is True:
                session.execute(
                    update(CRMContact)
                    .where(
                        and_(
                            CRMContact.account_id == contact.account_id,
                            CRMContact.id != contact.id,
                            CRMContact.deleted_at.is_(None),
                            CRMContact.is_primary.is_(True),
                        )
                    )
                    .values(is_primary=False, updated_at=utcnow(), row_version=CRMContact.row_version + 1)
                )

            result = session.execute(
                update(CRMContact)
                .where(
                    and_(
                        CRMContact.id == contact.id,
                        CRMContact.row_version == dto.row_version,
                        CRMContact.deleted_at.is_(None),
                    )
                )
                .values(**changes)
            )
            if result.rowcount == 0:
                session.rollback()
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

            updated_contact = session.scalar(
                select(CRMContact)
                .where(CRMContact.id == contact.id)
                .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
            )
            if updated_contact is None:
                session.rollback()
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")
            if custom_fields_provided:
                contact_scope = actor_user.current_legal_entity_id or self._first_legal_entity_id(updated_contact.account)
                custom_field_service.set_values_for_entity(
                    session,
                    "contact",
                    updated_contact.id,
                    custom_fields_payload,
                    contact_scope,
                    enforce_required=False,
                )
            updated_custom_fields = custom_field_service.get_values_for_entity(session, "contact", updated_contact.id)
            updated = self._to_read(updated_contact, updated_custom_fields)
            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type=self.entity_type,
                entity_id=str(contact.id),
                action="update",
                before=before,
                after=updated.model_dump(mode="json"),
                correlation_id=actor_user.correlation_id,
            )
            events.publish(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "crm.contact.updated",
                    "occurred_at": utcnow().isoformat(),
                    "actor_user_id": actor_user.user_id,
                    "legal_entity_id": str(self._first_legal_entity_id(contact.account)),
                    "payload": {
                        "contact_id": str(contact.id),
                        "account_id": str(contact.account_id),
                        "row_version": updated.row_version,
                    },
                }
            )
            publish_index_requested(
                entity_type="contact",
                entity_id=contact.id,
                operation="upsert",
                fields=build_search_doc_for_contact(
                    updated_contact,
                    custom_field_service.get_search_values_for_entity(session, "contact", updated_contact.id),
                ),
                legal_entity_id=self._first_legal_entity_id(contact.account),
                actor_user_id=actor_user.user_id,
                correlation_id=actor_user.correlation_id,
            )
            session.commit()
            return self._to_read_model(session, contact.id, actor_user=actor_user)
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Primary contact conflict for account",
            )

    def soft_delete_contact(self, session: Session, actor_user: ActorUser, contact_id: uuid.UUID) -> None:
        contact = session.scalar(
            select(CRMContact)
            .where(and_(CRMContact.id == contact_id, CRMContact.deleted_at.is_(None)))
            .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
        )
        if contact is None or not self._can_view_account(actor_user, contact.account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")

        contact.deleted_at = utcnow()
        contact.updated_at = utcnow()
        contact.is_primary = False
        contact.row_version = contact.row_version + 1
        session.add(contact)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(contact.id),
            action="soft_delete",
            before={"deleted_at": None},
            after={"deleted_at": contact.deleted_at.isoformat()},
            correlation_id=actor_user.correlation_id,
        )
        publish_index_requested(
            entity_type="contact",
            entity_id=contact.id,
            operation="delete",
            fields={},
            legal_entity_id=self._first_legal_entity_id(contact.account),
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()

    def _to_read_model(self, session: Session, contact_id: uuid.UUID, actor_user: ActorUser | None = None) -> ContactRead:
        contact = session.scalar(
            select(CRMContact)
            .where(CRMContact.id == contact_id)
            .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
        )
        if contact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")
        custom_fields = custom_field_service.get_values_for_entity(session, "contact", contact.id)
        read_model = self._to_read(contact, custom_fields)
        if actor_user is None:
            return read_model

        auth_ctx = _to_auth_context(actor_user)
        try:
            contact_repository.validate_read_scope(
                auth_ctx,
                company_code=str(self._first_legal_entity_id(contact.account)),
                region_code=contact.account.primary_region_code,
                action="read",
            )
        except AuthorizationError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")

        secured_payload = contact_repository.apply_read_security(
            read_model.model_dump(mode="json"),
            auth_ctx,
        )
        return ContactRead.model_validate(secured_payload)

    def _to_read(self, contact: CRMContact, custom_fields: dict[str, Any] | None = None) -> ContactRead:
        return ContactRead.model_validate(
            {
                "id": contact.id,
                "account_id": contact.account_id,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email,
                "phone": contact.phone,
                "title": contact.title,
                "department": contact.department,
                "locale": contact.locale,
                "timezone": contact.timezone,
                "owner_user_id": contact.owner_user_id,
                "is_primary": contact.is_primary,
                "created_at": contact.created_at,
                "updated_at": contact.updated_at,
                "deleted_at": contact.deleted_at,
                "row_version": contact.row_version,
                "custom_fields": custom_fields or {},
            }
        )

    def _get_visible_account(self, session: Session, actor_user: ActorUser, account_id: uuid.UUID) -> CRMAccount:
        account = session.scalar(
            select(CRMAccount)
            .where(CRMAccount.id == account_id)
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None or not self._can_view_account(actor_user, account):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
        return account

    def _can_view_account(self, actor_user: ActorUser, account: CRMAccount) -> bool:
        if "crm.contacts.read_all" in actor_user.permissions:
            return True
        if actor_user.allowed_region_codes and account.primary_region_code not in set(actor_user.allowed_region_codes):
            return False
        if not actor_user.allowed_legal_entity_ids:
            return True
        allowed = set(actor_user.allowed_legal_entity_ids)
        return any(link.legal_entity_id in allowed for link in account.legal_entities)

    def _first_legal_entity_id(self, account: CRMAccount) -> uuid.UUID:
        if not account.legal_entities:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Account has no legal-entity mappings",
            )
        sorted_links = sorted(account.legal_entities, key=lambda item: (not item.is_default, str(item.id)))
        return sorted_links[0].legal_entity_id


class LeadService:
    entity_type = "crm.lead"
    valid_statuses = {"New", "Working", "Qualified", "Disqualified", "Converted"}

    def create_lead(self, session: Session, actor_user: ActorUser, dto: LeadCreate) -> LeadRead:
        if dto.selling_legal_entity_id not in actor_user.allowed_legal_entity_ids and "crm.leads.create_all" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="selling legal entity not allowed")
        if dto.status not in self.valid_statuses:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid lead status")

        lead = CRMLead(
            status=dto.status,
            source=dto.source,
            owner_user_id=dto.owner_user_id,
            selling_legal_entity_id=dto.selling_legal_entity_id,
            region_code=dto.region_code,
            company_name=dto.company_name,
            contact_first_name=dto.contact_first_name,
            contact_last_name=dto.contact_last_name,
            email=str(dto.email) if dto.email is not None else None,
            phone=dto.phone,
            qualification_notes=dto.qualification_notes,
        )
        session.add(lead)
        session.flush()
        custom_fields = custom_field_service.set_values_for_entity(
            session,
            "lead",
            lead.id,
            dto.custom_fields,
            dto.selling_legal_entity_id,
            enforce_required=True,
        )
        lead_read = self._to_read(lead, custom_fields)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(lead.id),
            action="create",
            before=None,
            after=lead_read.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.lead.created",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(lead.selling_legal_entity_id),
                "version": 1,
                "payload": {"lead_id": str(lead.id), "status": lead.status},
            }
        )
        publish_index_requested(
            entity_type="lead",
            entity_id=lead.id,
            operation="upsert",
            fields=build_search_doc_for_lead(
                lead,
                custom_field_service.get_search_values_for_entity(session, "lead", lead.id),
            ),
            legal_entity_id=lead.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_read_model(session, lead.id)

    def list_leads(
        self,
        session: Session,
        actor_user: ActorUser,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> list[LeadRead]:
        stmt: Select[tuple[CRMLead]] = select(CRMLead).where(CRMLead.deleted_at.is_(None))
        if "crm.leads.read_all" not in actor_user.permissions:
            if not actor_user.allowed_legal_entity_ids:
                return []
            stmt = stmt.where(CRMLead.selling_legal_entity_id.in_(actor_user.allowed_legal_entity_ids))

        if filters.get("status"):
            stmt = stmt.where(CRMLead.status == filters["status"])
        if filters.get("owner_user_id"):
            stmt = stmt.where(CRMLead.owner_user_id == filters["owner_user_id"])
        if filters.get("source"):
            stmt = stmt.where(CRMLead.source == filters["source"])
        if filters.get("created_from"):
            stmt = stmt.where(CRMLead.created_at >= filters["created_from"])
        if filters.get("created_to"):
            stmt = stmt.where(CRMLead.created_at <= filters["created_to"])
        if filters.get("q"):
            q = str(filters["q"])
            stmt = stmt.where((CRMLead.company_name.ilike(f"%{q}%")) | (CRMLead.email.ilike(f"%{q}%")))

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        leads = session.scalars(stmt.order_by(CRMLead.created_at.desc()).offset(offset).limit(limit)).all()
        return [self._to_read_model(session, item.id) for item in leads]

    def get_lead(self, session: Session, actor_user: ActorUser, lead_id: uuid.UUID) -> LeadRead:
        lead = session.scalar(select(CRMLead).where(and_(CRMLead.id == lead_id, CRMLead.deleted_at.is_(None))))
        if lead is None or not self._can_view(actor_user, lead):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
        return self._to_read_model(session, lead.id)

    def update_lead(self, session: Session, actor_user: ActorUser, lead_id: uuid.UUID, dto: LeadUpdate) -> LeadRead:
        lead = session.scalar(select(CRMLead).where(and_(CRMLead.id == lead_id, CRMLead.deleted_at.is_(None))))
        if lead is None or not self._can_view(actor_user, lead):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")

        if lead.status == "Converted":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="converted lead cannot be updated")

        payload = dto.model_dump(exclude_unset=True)
        custom_fields_provided = "custom_fields" in dto.model_fields_set
        custom_fields_payload = payload.pop("custom_fields", {})
        requested_status = payload.get("status")
        if lead.status == "Disqualified" and requested_status in {"Working", "Qualified"}:
            if "crm.leads.requalify" not in actor_user.permissions:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing requalify permission")
            payload["disqualify_reason_code"] = None
            payload["disqualify_notes"] = None

        if requested_status is not None and requested_status not in self.valid_statuses:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid lead status")

        if "email" in payload:
            payload["email"] = str(payload["email"]) if payload["email"] is not None else None
        if not payload and not custom_fields_provided:
            return self._to_read_model(session, lead.id)

        payload["updated_at"] = utcnow()
        payload["row_version"] = CRMLead.row_version + 1

        before = self._to_read(
            lead,
            custom_field_service.get_values_for_entity(session, "lead", lead.id),
        ).model_dump(mode="json")
        result = session.execute(
            update(CRMLead)
            .where(and_(CRMLead.id == lead.id, CRMLead.row_version == dto.row_version, CRMLead.deleted_at.is_(None)))
            .values(**payload)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated_lead = session.scalar(select(CRMLead).where(CRMLead.id == lead.id))
        if updated_lead is None:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
        if custom_fields_provided:
            custom_field_service.set_values_for_entity(
                session,
                "lead",
                updated_lead.id,
                custom_fields_payload,
                updated_lead.selling_legal_entity_id,
                enforce_required=False,
            )
        updated_custom_fields = custom_field_service.get_values_for_entity(session, "lead", updated_lead.id)
        updated = self._to_read(updated_lead, updated_custom_fields)
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(lead.id),
            action="update",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.lead.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(updated.selling_legal_entity_id),
                "version": 1,
                "payload": {"lead_id": str(updated.id), "status": updated.status},
            }
        )
        publish_index_requested(
            entity_type="lead",
            entity_id=updated.id,
            operation="upsert",
            fields=build_search_doc_for_lead(
                updated_lead,
                custom_field_service.get_search_values_for_entity(session, "lead", updated_lead.id),
            ),
            legal_entity_id=updated.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_read_model(session, lead.id)

    def disqualify_lead(
        self,
        session: Session,
        actor_user: ActorUser,
        lead_id: uuid.UUID,
        dto: LeadDisqualifyRequest,
    ) -> LeadRead:
        lead = session.scalar(select(CRMLead).where(and_(CRMLead.id == lead_id, CRMLead.deleted_at.is_(None))))
        if lead is None or not self._can_view(actor_user, lead):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
        if lead.status == "Converted":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="converted lead cannot be disqualified")

        before = self._to_read(
            lead,
            custom_field_service.get_values_for_entity(session, "lead", lead.id),
        ).model_dump(mode="json")
        result = session.execute(
            update(CRMLead)
            .where(and_(CRMLead.id == lead.id, CRMLead.row_version == dto.row_version, CRMLead.deleted_at.is_(None)))
            .values(
                status="Disqualified",
                disqualify_reason_code=dto.reason_code,
                disqualify_notes=dto.notes,
                updated_at=utcnow(),
                row_version=CRMLead.row_version + 1,
            )
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated_lead = session.scalar(select(CRMLead).where(CRMLead.id == lead.id))
        if updated_lead is None:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
        updated = self._to_read(
            updated_lead,
            custom_field_service.get_values_for_entity(session, "lead", updated_lead.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(lead.id),
            action="disqualify",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        publish_index_requested(
            entity_type="lead",
            entity_id=updated.id,
            operation="upsert",
            fields=build_search_doc_for_lead(
                updated_lead,
                custom_field_service.get_search_values_for_entity(session, "lead", updated_lead.id),
            ),
            legal_entity_id=updated.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return updated

    def convert_lead(
        self,
        session: Session,
        actor_user: ActorUser,
        lead_id: uuid.UUID,
        dto: LeadConvertRequest,
        idempotency_key: str | None,
    ) -> LeadRead:
        endpoint = f"crm.lead.convert:{lead_id}"
        request_hash = hashlib.sha256(
            json.dumps(dto.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()

        if idempotency_key:
            existing_key = session.scalar(
                select(CRMIdempotencyKey).where(
                    and_(CRMIdempotencyKey.endpoint == endpoint, CRMIdempotencyKey.key == idempotency_key)
                )
            )
            if existing_key is not None:
                if existing_key.request_hash != request_hash:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key payload mismatch")
                stored = json.loads(existing_key.response_json)
                return LeadRead.model_validate(stored)

        lead = session.scalar(select(CRMLead).where(and_(CRMLead.id == lead_id, CRMLead.deleted_at.is_(None))))
        if lead is None or not self._can_view(actor_user, lead):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")

        if lead.converted_at is not None:
            return self._to_read(lead)

        if lead.status == "Disqualified" and "crm.leads.convert_disqualified" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="disqualified lead cannot be converted")

        if lead.row_version != dto.row_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        before_status = lead.status
        account = self._resolve_account_for_conversion(session, actor_user, lead, dto)
        contact = self._resolve_contact_for_conversion(session, actor_user, lead, account, dto)
        converted_opportunity_id: uuid.UUID | None = None
        if dto.create_opportunity:
            # TODO: Create CRM opportunity record when opportunity module/table is implemented.
            converted_opportunity_id = None

        lead.status = "Converted"
        lead.converted_account_id = account.id
        lead.converted_contact_id = contact.id
        lead.converted_opportunity_id = converted_opportunity_id
        lead.converted_at = utcnow()
        lead.updated_at = utcnow()
        lead.row_version = lead.row_version + 1
        session.add(lead)

        result = self._to_read(
            lead,
            custom_field_service.get_values_for_entity(session, "lead", lead.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(lead.id),
            action="convert",
            before={"status": before_status, "converted_at": None},
            after={
                "status": "Converted",
                "converted_account_id": str(account.id),
                "converted_contact_id": str(contact.id),
                "converted_opportunity_id": str(converted_opportunity_id) if converted_opportunity_id else None,
            },
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.lead.converted",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(lead.selling_legal_entity_id),
                "version": 1,
                "payload": {
                    "lead_id": str(lead.id),
                    "account_id": str(account.id),
                    "contact_id": str(contact.id),
                    "opportunity_id": str(converted_opportunity_id) if converted_opportunity_id else None,
                },
            }
        )
        publish_index_requested(
            entity_type="lead",
            entity_id=lead.id,
            operation="upsert",
            fields=build_search_doc_for_lead(
                lead,
                custom_field_service.get_search_values_for_entity(session, "lead", lead.id),
            ),
            legal_entity_id=lead.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )

        if idempotency_key:
            session.add(
                CRMIdempotencyKey(
                    endpoint=endpoint,
                    key=idempotency_key,
                    request_hash=request_hash,
                    response_json=json.dumps(result.model_dump(mode="json")),
                )
            )

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if idempotency_key:
                existing_key = session.scalar(
                    select(CRMIdempotencyKey).where(
                        and_(CRMIdempotencyKey.endpoint == endpoint, CRMIdempotencyKey.key == idempotency_key)
                    )
                )
                if existing_key is not None and existing_key.request_hash == request_hash:
                    return LeadRead.model_validate(json.loads(existing_key.response_json))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="lead conversion conflict")

        return self._to_read_model(session, lead.id)

    def _resolve_account_for_conversion(
        self,
        session: Session,
        actor_user: ActorUser,
        lead: CRMLead,
        dto: LeadConvertRequest,
    ) -> CRMAccount:
        if dto.account.mode == "existing":
            if dto.account.account_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account_id is required")
            account = session.scalar(
                select(CRMAccount)
                .where(and_(CRMAccount.id == dto.account.account_id, CRMAccount.deleted_at.is_(None)))
                .options(selectinload(CRMAccount.legal_entities))
            )
            if account is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
            if not any(link.legal_entity_id == lead.selling_legal_entity_id for link in account.legal_entities):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="existing account is not mapped to lead selling legal entity",
                )
            if "crm.leads.read_all" not in actor_user.permissions and not any(
                link.legal_entity_id in actor_user.allowed_legal_entity_ids for link in account.legal_entities
            ):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
            return account

        if dto.account.mode != "new":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account.mode must be existing or new")

        account_name = dto.account.name or lead.company_name
        if not account_name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account name is required")

        account = CRMAccount(
            name=account_name,
            status="Active",
            owner_user_id=dto.account.owner_user_id or lead.owner_user_id,
            primary_region_code=dto.account.primary_region_code or lead.region_code,
        )
        session.add(account)
        session.flush()

        legal_entities = dto.account.legal_entity_ids or [lead.selling_legal_entity_id]
        legal_entities = list(dict.fromkeys(legal_entities))
        if lead.selling_legal_entity_id not in legal_entities:
            legal_entities.append(lead.selling_legal_entity_id)

        for index, legal_entity_id in enumerate(legal_entities):
            session.add(
                CRMAccountLegalEntity(
                    account_id=account.id,
                    legal_entity_id=legal_entity_id,
                    relationship_type="customer",
                    is_default=index == 0,
                )
            )
        session.flush()
        session.refresh(account)
        session.refresh(account, attribute_names=["legal_entities"])
        return account

    def _resolve_contact_for_conversion(
        self,
        session: Session,
        actor_user: ActorUser,
        lead: CRMLead,
        account: CRMAccount,
        dto: LeadConvertRequest,
    ) -> CRMContact:
        if dto.contact.mode == "existing":
            if dto.contact.contact_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="contact_id is required")
            contact = session.scalar(
                select(CRMContact).where(and_(CRMContact.id == dto.contact.contact_id, CRMContact.deleted_at.is_(None)))
            )
            if contact is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact not found")
            if contact.account_id != account.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="existing contact does not belong to selected account",
                )
            return contact

        if dto.contact.mode != "new":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="contact.mode must be existing or new")

        first_name = dto.contact.first_name or lead.contact_first_name
        last_name = dto.contact.last_name or lead.contact_last_name
        if not first_name or not last_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="new contact requires first_name and last_name",
            )

        is_primary = dto.contact.is_primary if dto.contact.is_primary is not None else True
        if is_primary:
            session.execute(
                update(CRMContact)
                .where(
                    and_(
                        CRMContact.account_id == account.id,
                        CRMContact.deleted_at.is_(None),
                        CRMContact.is_primary.is_(True),
                    )
                )
                .values(is_primary=False, updated_at=utcnow(), row_version=CRMContact.row_version + 1)
            )

        contact = CRMContact(
            account_id=account.id,
            first_name=first_name,
            last_name=last_name,
            email=str(dto.contact.email) if dto.contact.email is not None else lead.email,
            phone=dto.contact.phone or lead.phone,
            owner_user_id=dto.contact.owner_user_id or lead.owner_user_id,
            is_primary=is_primary,
        )
        session.add(contact)
        session.flush()
        return contact

    def _to_read_model(self, session: Session, lead_id: uuid.UUID) -> LeadRead:
        lead = session.scalar(select(CRMLead).where(CRMLead.id == lead_id))
        if lead is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
        custom_fields = custom_field_service.get_values_for_entity(session, "lead", lead.id)
        return self._to_read(lead, custom_fields)

    def _to_read(self, lead: CRMLead, custom_fields: dict[str, Any] | None = None) -> LeadRead:
        return LeadRead.model_validate(
            {
                "id": lead.id,
                "status": lead.status,
                "source": lead.source,
                "owner_user_id": lead.owner_user_id,
                "selling_legal_entity_id": lead.selling_legal_entity_id,
                "region_code": lead.region_code,
                "company_name": lead.company_name,
                "contact_first_name": lead.contact_first_name,
                "contact_last_name": lead.contact_last_name,
                "email": lead.email,
                "phone": lead.phone,
                "qualification_notes": lead.qualification_notes,
                "disqualify_reason_code": lead.disqualify_reason_code,
                "disqualify_notes": lead.disqualify_notes,
                "converted_account_id": lead.converted_account_id,
                "converted_contact_id": lead.converted_contact_id,
                "converted_opportunity_id": lead.converted_opportunity_id,
                "converted_at": lead.converted_at,
                "created_at": lead.created_at,
                "updated_at": lead.updated_at,
                "deleted_at": lead.deleted_at,
                "row_version": lead.row_version,
                "custom_fields": custom_fields or {},
            }
        )

    def _can_view(self, actor_user: ActorUser, lead: CRMLead) -> bool:
        if "crm.leads.read_all" in actor_user.permissions:
            return True
        return lead.selling_legal_entity_id in set(actor_user.allowed_legal_entity_ids)


class PipelineService:
    entity_type = "crm.pipeline"
    valid_stage_types = {"Open", "ClosedWon", "ClosedLost"}

    def create_pipeline(self, session: Session, actor_user: ActorUser, dto: PipelineCreate) -> PipelineRead:
        pipeline = CRMPipeline(
            name=dto.name.strip(),
            selling_legal_entity_id=dto.selling_legal_entity_id,
            is_default=dto.is_default,
        )
        session.add(pipeline)
        session.flush()

        if dto.is_default:
            self._unset_other_defaults(session, pipeline.id, dto.selling_legal_entity_id)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(pipeline.id),
            action="create",
            before=None,
            after={
                "name": pipeline.name,
                "selling_legal_entity_id": str(pipeline.selling_legal_entity_id) if pipeline.selling_legal_entity_id else None,
                "is_default": pipeline.is_default,
            },
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_pipeline_read(pipeline)

    def add_stage(
        self,
        session: Session,
        actor_user: ActorUser,
        pipeline_id: uuid.UUID,
        dto: PipelineStageCreate,
    ) -> PipelineStageRead:
        pipeline = session.scalar(
            select(CRMPipeline).where(and_(CRMPipeline.id == pipeline_id, CRMPipeline.deleted_at.is_(None)))
        )
        if pipeline is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")
        if dto.stage_type not in self.valid_stage_types:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid stage_type")

        stage = CRMPipelineStage(
            pipeline_id=pipeline_id,
            name=dto.name.strip(),
            position=dto.position,
            stage_type=dto.stage_type,
            default_probability=dto.default_probability,
            requires_amount=dto.requires_amount,
            requires_expected_close_date=dto.requires_expected_close_date,
            is_active=dto.is_active,
        )
        session.add(stage)
        session.flush()

        self._validate_terminal_stages(session, pipeline_id)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=f"{self.entity_type}.stage",
            entity_id=str(stage.id),
            action="create",
            before=None,
            after={
                "pipeline_id": str(stage.pipeline_id),
                "name": stage.name,
                "position": stage.position,
                "stage_type": stage.stage_type,
            },
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_stage_read(stage)

    def get_default_pipeline_for_legal_entity(
        self,
        session: Session,
        selling_legal_entity_id: uuid.UUID,
    ) -> CRMPipeline:
        pipeline = session.scalar(
            select(CRMPipeline)
            .where(
                and_(
                    CRMPipeline.deleted_at.is_(None),
                    CRMPipeline.is_default.is_(True),
                    CRMPipeline.selling_legal_entity_id == selling_legal_entity_id,
                )
            )
            .options(selectinload(CRMPipeline.stages))
        )
        if pipeline is not None:
            return pipeline

        global_default = session.scalar(
            select(CRMPipeline)
            .where(
                and_(
                    CRMPipeline.deleted_at.is_(None),
                    CRMPipeline.is_default.is_(True),
                    CRMPipeline.selling_legal_entity_id.is_(None),
                )
            )
            .options(selectinload(CRMPipeline.stages))
        )
        if global_default is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="default pipeline not configured")
        return global_default

    def get_pipeline(
        self,
        session: Session,
        actor_user: ActorUser,
        pipeline_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> PipelineRead:
        pipeline = session.scalar(
            select(CRMPipeline)
            .where(and_(CRMPipeline.id == pipeline_id, CRMPipeline.deleted_at.is_(None)))
            .options(selectinload(CRMPipeline.stages))
        )
        if pipeline is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")

        self._enforce_pipeline_visibility(actor_user, pipeline)
        stages = self._sorted_stages(pipeline.stages, include_inactive=include_inactive)
        return self._to_pipeline_read(pipeline, stages)

    def list_stages(
        self,
        session: Session,
        actor_user: ActorUser,
        pipeline_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> list[PipelineStageRead]:
        pipeline = session.scalar(
            select(CRMPipeline)
            .where(and_(CRMPipeline.id == pipeline_id, CRMPipeline.deleted_at.is_(None)))
            .options(selectinload(CRMPipeline.stages))
        )
        if pipeline is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")

        self._enforce_pipeline_visibility(actor_user, pipeline)
        stages = self._sorted_stages(pipeline.stages, include_inactive=include_inactive)
        return [self._to_stage_read(stage) for stage in stages]

    def get_default_pipeline_with_stages(
        self,
        session: Session,
        actor_user: ActorUser,
        selling_legal_entity_id: uuid.UUID | None,
        include_inactive: bool = False,
    ) -> PipelineRead:
        resolved_legal_entity_id = selling_legal_entity_id or actor_user.current_legal_entity_id

        pipeline: CRMPipeline | None = None
        if resolved_legal_entity_id is not None:
            pipeline = session.scalar(
                select(CRMPipeline)
                .where(
                    and_(
                        CRMPipeline.deleted_at.is_(None),
                        CRMPipeline.is_default.is_(True),
                        CRMPipeline.selling_legal_entity_id == resolved_legal_entity_id,
                    )
                )
                .options(selectinload(CRMPipeline.stages))
            )

        if pipeline is None:
            pipeline = session.scalar(
                select(CRMPipeline)
                .where(
                    and_(
                        CRMPipeline.deleted_at.is_(None),
                        CRMPipeline.is_default.is_(True),
                        CRMPipeline.selling_legal_entity_id.is_(None),
                    )
                )
                .options(selectinload(CRMPipeline.stages))
            )

        if pipeline is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="default pipeline not configured")

        self._enforce_pipeline_visibility(actor_user, pipeline)
        stages = self._sorted_stages(pipeline.stages, include_inactive=include_inactive)
        return self._to_pipeline_read(pipeline, stages)

    def get_default_open_stage(self, session: Session, selling_legal_entity_id: uuid.UUID) -> CRMPipelineStage:
        pipeline = self.get_default_pipeline_for_legal_entity(session, selling_legal_entity_id)
        open_stages = [s for s in pipeline.stages if s.deleted_at is None and s.is_active and s.stage_type == "Open"]
        if not open_stages:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pipeline has no active open stage")
        return sorted(open_stages, key=lambda item: item.position)[0]

    def _unset_other_defaults(self, session: Session, pipeline_id: uuid.UUID, legal_entity_id: uuid.UUID | None) -> None:
        session.execute(
            update(CRMPipeline)
            .where(
                and_(
                    CRMPipeline.id != pipeline_id,
                    CRMPipeline.deleted_at.is_(None),
                    CRMPipeline.selling_legal_entity_id == legal_entity_id,
                    CRMPipeline.is_default.is_(True),
                )
            )
            .values(is_default=False, updated_at=utcnow(), row_version=CRMPipeline.row_version + 1)
        )

    def _validate_terminal_stages(self, session: Session, pipeline_id: uuid.UUID) -> None:
        stages = session.scalars(
            select(CRMPipelineStage).where(
                and_(CRMPipelineStage.pipeline_id == pipeline_id, CRMPipelineStage.deleted_at.is_(None))
            )
        ).all()
        won_count = sum(1 for stage in stages if stage.stage_type == "ClosedWon")
        lost_count = sum(1 for stage in stages if stage.stage_type == "ClosedLost")
        if won_count > 1 or lost_count > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="pipeline can have at most one ClosedWon and one ClosedLost stage",
            )

    def _to_pipeline_read(self, pipeline: CRMPipeline, stages: list[CRMPipelineStage] | None = None) -> PipelineRead:
        stage_rows = stages if stages is not None else self._sorted_stages(pipeline.stages, include_inactive=False)
        return PipelineRead.model_validate(
            {
                "id": pipeline.id,
                "name": pipeline.name,
                "selling_legal_entity_id": pipeline.selling_legal_entity_id,
                "is_default": pipeline.is_default,
                "created_at": pipeline.created_at,
                "updated_at": pipeline.updated_at,
                "deleted_at": pipeline.deleted_at,
                "row_version": pipeline.row_version,
                "stages": [self._to_stage_read(stage).model_dump(mode="json") for stage in stage_rows],
            }
        )

    def _to_stage_read(self, stage: CRMPipelineStage) -> PipelineStageRead:
        return PipelineStageRead.model_validate(stage)

    def _sorted_stages(self, stages: list[CRMPipelineStage], include_inactive: bool) -> list[CRMPipelineStage]:
        if include_inactive:
            filtered = [stage for stage in stages]
        else:
            filtered = [stage for stage in stages if stage.deleted_at is None and stage.is_active]
        return sorted(filtered, key=lambda item: (item.position, str(item.id)))

    def _enforce_pipeline_visibility(self, actor_user: ActorUser, pipeline: CRMPipeline) -> None:
        if "crm.pipelines.read_all" in actor_user.permissions:
            return
        if pipeline.selling_legal_entity_id is None:
            return
        if pipeline.selling_legal_entity_id not in set(actor_user.allowed_legal_entity_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pipeline not found")


class OpportunityService:
    entity_type = "crm.opportunity"

    def __init__(self) -> None:
        self.pipeline_service = PipelineService()

    def create_opportunity(self, session: Session, actor_user: ActorUser, dto: OpportunityCreate) -> OpportunityRead:
        self._validate_scope(actor_user, dto.selling_legal_entity_id, "crm.opportunities.create_all")

        account = self._get_visible_account(session, actor_user, dto.account_id)
        if account.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="account is deleted")

        account_links = {link.legal_entity_id for link in account.legal_entities}
        if dto.selling_legal_entity_id not in account_links:
            session.add(
                CRMAccountLegalEntity(
                    account_id=account.id,
                    legal_entity_id=dto.selling_legal_entity_id,
                    relationship_type="opportunity",
                    is_default=False,
                )
            )
            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type="crm.account_legal_entity",
                entity_id=str(account.id),
                action="auto_associate",
                before=None,
                after={
                    "account_id": str(account.id),
                    "legal_entity_id": str(dto.selling_legal_entity_id),
                    "reason": "opportunity_create",
                },
                correlation_id=actor_user.correlation_id,
            )

        stage = self._resolve_create_stage(session, dto)
        self._validate_stage_rules(stage, Decimal(str(dto.amount)), dto.expected_close_date)

        opportunity = CRMOpportunity(
            account_id=dto.account_id,
            name=dto.name.strip(),
            stage_id=stage.id,
            selling_legal_entity_id=dto.selling_legal_entity_id,
            region_code=dto.region_code,
            currency_code=dto.currency_code,
            amount=dto.amount,
            owner_user_id=dto.owner_user_id,
            expected_close_date=dto.expected_close_date,
            probability=dto.probability,
            forecast_category=dto.forecast_category,
            primary_contact_id=dto.primary_contact_id,
        )
        session.add(opportunity)
        session.flush()
        custom_fields = custom_field_service.set_values_for_entity(
            session,
            "opportunity",
            opportunity.id,
            dto.custom_fields,
            dto.selling_legal_entity_id,
            enforce_required=True,
        )
        opportunity_read = self._to_read(opportunity, custom_fields)

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="create",
            before=None,
            after=opportunity_read.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.created",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(opportunity.selling_legal_entity_id),
                "version": 1,
                "payload": {
                    "opportunity_id": str(opportunity.id),
                    "account_id": str(opportunity.account_id),
                    "stage_id": str(opportunity.stage_id),
                },
            }
        )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=opportunity.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", opportunity.id),
            ),
            legal_entity_id=opportunity.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_read_model(session, opportunity.id)

    def list_opportunities(
        self,
        session: Session,
        actor_user: ActorUser,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> list[OpportunityRead]:
        stmt: Select[tuple[CRMOpportunity]] = select(CRMOpportunity).where(CRMOpportunity.deleted_at.is_(None))

        if "crm.opportunities.read_all" not in actor_user.permissions:
            if not actor_user.allowed_legal_entity_ids:
                return []
            stmt = stmt.where(CRMOpportunity.selling_legal_entity_id.in_(actor_user.allowed_legal_entity_ids))

        if filters.get("stage_id"):
            stmt = stmt.where(CRMOpportunity.stage_id == filters["stage_id"])
        if filters.get("owner_user_id"):
            stmt = stmt.where(CRMOpportunity.owner_user_id == filters["owner_user_id"])
        if filters.get("forecast_category"):
            stmt = stmt.where(CRMOpportunity.forecast_category == filters["forecast_category"])
        if filters.get("expected_close_from"):
            stmt = stmt.where(CRMOpportunity.expected_close_date >= filters["expected_close_from"])
        if filters.get("expected_close_to"):
            stmt = stmt.where(CRMOpportunity.expected_close_date <= filters["expected_close_to"])
        if filters.get("account_id"):
            stmt = stmt.where(CRMOpportunity.account_id == filters["account_id"])

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        opportunities = session.scalars(stmt.order_by(CRMOpportunity.created_at.desc()).offset(offset).limit(limit)).all()

        visible: list[OpportunityRead] = []
        for opportunity in opportunities:
            if self._can_view_opportunity(session, actor_user, opportunity):
                visible.append(self._to_read_model(session, opportunity.id))
        return visible

    def get_opportunity(self, session: Session, actor_user: ActorUser, opportunity_id: uuid.UUID) -> OpportunityRead:
        opportunity = session.scalar(
            select(CRMOpportunity).where(and_(CRMOpportunity.id == opportunity_id, CRMOpportunity.deleted_at.is_(None)))
        )
        if opportunity is None or not self._can_view_opportunity(session, actor_user, opportunity):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
        return self._to_read_model(session, opportunity.id)

    def update_opportunity(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        dto: OpportunityUpdate,
    ) -> OpportunityRead:
        opportunity = session.scalar(
            select(CRMOpportunity).where(and_(CRMOpportunity.id == opportunity_id, CRMOpportunity.deleted_at.is_(None)))
        )
        if opportunity is None or not self._can_view_opportunity(session, actor_user, opportunity):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")

        payload = dto.model_dump(exclude_unset=True)
        payload.pop("row_version", None)
        custom_fields_provided = "custom_fields" in dto.model_fields_set
        custom_fields_payload = payload.pop("custom_fields", {})
        if not payload and not custom_fields_provided:
            return self._to_read_model(session, opportunity.id)

        restricted_when_closed = {"amount", "currency_code", "selling_legal_entity_id", "expected_close_date"}
        if (opportunity.closed_won_at or opportunity.closed_lost_at) and restricted_when_closed.intersection(payload.keys()):
            if "crm.opportunities.edit_closed" not in actor_user.permissions:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="cannot edit closed opportunity financial/stage fields",
                )

        if "selling_legal_entity_id" in payload and payload["selling_legal_entity_id"] is not None:
            self._validate_scope(actor_user, payload["selling_legal_entity_id"], "crm.opportunities.update_all")

        if "amount" in payload and payload["amount"] is not None:
            payload["amount"] = float(payload["amount"])

        payload["updated_at"] = utcnow()
        payload["row_version"] = CRMOpportunity.row_version + 1

        before = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        ).model_dump(mode="json")
        result = session.execute(
            update(CRMOpportunity)
            .where(
                and_(
                    CRMOpportunity.id == opportunity.id,
                    CRMOpportunity.row_version == dto.row_version,
                    CRMOpportunity.deleted_at.is_(None),
                )
            )
            .values(**payload)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated_opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity.id))
        if updated_opportunity is None:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
        if custom_fields_provided:
            opportunity_scope = updated_opportunity.selling_legal_entity_id
            custom_field_service.set_values_for_entity(
                session,
                "opportunity",
                updated_opportunity.id,
                custom_fields_payload,
                opportunity_scope,
                enforce_required=False,
            )
        updated_custom_fields = custom_field_service.get_values_for_entity(session, "opportunity", updated_opportunity.id)
        updated = self._to_read(updated_opportunity, updated_custom_fields)
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="update",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(updated.selling_legal_entity_id),
                "version": 1,
                "payload": {"opportunity_id": str(updated.id), "row_version": updated.row_version},
            }
        )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=updated.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                updated_opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", updated_opportunity.id),
            ),
            legal_entity_id=updated.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_read_model(session, opportunity.id)

    def change_stage(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        dto: OpportunityChangeStageRequest,
        idempotency_key: str | None,
    ) -> OpportunityRead:
        endpoint = f"crm.opportunity.change_stage:{opportunity_id}"
        request_hash = self._request_hash(dto.model_dump(mode="json"))
        stored = self._load_idempotent(session, endpoint, idempotency_key, request_hash)
        if stored is not None:
            return stored

        opportunity = self._get_visible_opportunity(session, actor_user, opportunity_id)
        stage = session.scalar(
            select(CRMPipelineStage)
            .where(and_(CRMPipelineStage.id == dto.stage_id, CRMPipelineStage.deleted_at.is_(None)))
            .options(selectinload(CRMPipelineStage.pipeline))
        )
        if stage is None or stage.pipeline is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stage not found")

        current_stage = session.scalar(
            select(CRMPipelineStage)
            .where(and_(CRMPipelineStage.id == opportunity.stage_id, CRMPipelineStage.deleted_at.is_(None)))
            .options(selectinload(CRMPipelineStage.pipeline))
        )
        if current_stage is None or current_stage.pipeline_id != stage.pipeline_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="stage must be in same pipeline")
        if stage.stage_type in {"ClosedWon", "ClosedLost"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="use close-won or close-lost endpoints for terminal stages",
            )

        self._validate_stage_rules(stage, Decimal(str(opportunity.amount)), opportunity.expected_close_date)
        before = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        ).model_dump(mode="json")

        result = session.execute(
            update(CRMOpportunity)
            .where(
                and_(
                    CRMOpportunity.id == opportunity.id,
                    CRMOpportunity.row_version == dto.row_version,
                    CRMOpportunity.deleted_at.is_(None),
                )
            )
            .values(stage_id=stage.id, updated_at=utcnow(), row_version=CRMOpportunity.row_version + 1)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated_opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity.id))
        if updated_opportunity is None:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
        updated = self._to_read(
            updated_opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", updated_opportunity.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="change_stage",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.stage_changed",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(updated.selling_legal_entity_id),
                "version": 1,
                "payload": {"opportunity_id": str(updated.id), "stage_id": str(updated.stage_id)},
            }
        )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=updated.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                updated_opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", updated_opportunity.id),
            ),
            legal_entity_id=updated.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        self._store_idempotent(session, endpoint, idempotency_key, request_hash, updated)
        session.commit()
        return self._to_read_model(session, opportunity.id)

    def close_won(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        dto: OpportunityCloseWonRequest,
        idempotency_key: str | None,
        *,
        sync: bool = False,
    ) -> OpportunityRead:
        endpoint = f"crm.opportunity.close_won:{opportunity_id}"
        request_hash = self._request_hash(dto.model_dump(mode="json"))
        stored = self._load_idempotent(session, endpoint, idempotency_key, request_hash)
        if stored is not None:
            return stored

        opportunity = self._get_visible_opportunity(session, actor_user, opportunity_id)
        if opportunity.closed_won_at is not None:
            return self._to_read(opportunity)
        if opportunity.row_version != dto.row_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        stage = self._get_terminal_stage(session, opportunity.stage_id, "ClosedWon")
        before = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        ).model_dump(mode="json")

        custom_field_service.ensure_required_fields(
            session,
            "opportunity",
            opportunity.id,
            opportunity.selling_legal_entity_id,
        )

        opportunity.stage_id = stage.id
        opportunity.closed_won_at = utcnow()
        opportunity.closed_lost_at = None
        opportunity.close_reason = None
        opportunity.forecast_category = "Closed"
        opportunity.revenue_handoff_last_error = None
        opportunity.updated_at = utcnow()
        opportunity.row_version = opportunity.row_version + 1
        session.add(opportunity)

        handoff_requested, handoff_mode = self._resolve_revenue_handoff_request(dto)
        queued_job_id: uuid.UUID | None = None
        if handoff_requested:
            opportunity.revenue_handoff_status = "Queued"
            opportunity.revenue_handoff_mode = handoff_mode
            opportunity.revenue_handoff_requested_at = utcnow()
            opportunity.revenue_handoff_completed_at = None
            job_key = idempotency_key or str(uuid.uuid4())
            queued_job = RevenueHandoffService().create_handoff_job(
                session,
                actor_user,
                opportunity.id,
                handoff_mode,
                job_key,
            )
            queued_job_id = queued_job.id
        else:
            opportunity.revenue_handoff_status = "NotRequested"
            opportunity.revenue_handoff_mode = None
            opportunity.revenue_handoff_requested_at = None
            opportunity.revenue_handoff_completed_at = None

        updated = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="close_won",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.closed_won",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(opportunity.selling_legal_entity_id),
                "version": 1,
                "payload": {
                    "opportunity_id": str(opportunity.id),
                    "account_id": str(opportunity.account_id),
                    "amount": float(opportunity.amount),
                    "currency_code": opportunity.currency_code,
                    "expected_close_date": (
                        opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else None
                    ),
                    "primary_contact_id": str(opportunity.primary_contact_id) if opportunity.primary_contact_id else None,
                    "revenue_handoff_mode": handoff_mode,
                    "revenue_handoff_requested": handoff_requested,
                },
            }
        )
        if queued_job_id is not None:
            events.publish(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "crm.opportunity.revenue_handoff_queued",
                    "occurred_at": utcnow().isoformat(),
                    "actor_user_id": actor_user.user_id,
                    "legal_entity_id": str(opportunity.selling_legal_entity_id),
                    "version": 1,
                    "payload": {
                        "opportunity_id": str(opportunity.id),
                        "mode": handoff_mode,
                        "job_id": str(queued_job_id),
                    },
                }
            )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=opportunity.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", opportunity.id),
            ),
            legal_entity_id=opportunity.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        self._store_idempotent(session, endpoint, idempotency_key, request_hash, updated)
        session.commit()

        if queued_job_id is not None and (sync or get_settings().auto_run_jobs):
            runner = RevenueHandoffJobRunner()
            runner.run_revenue_handoff_job(session, actor_user, queued_job_id)

        return self._to_read_model(session, opportunity.id)

    def close_lost(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        dto: OpportunityCloseLostRequest,
        idempotency_key: str | None,
    ) -> OpportunityRead:
        endpoint = f"crm.opportunity.close_lost:{opportunity_id}"
        request_hash = self._request_hash(dto.model_dump(mode="json"))
        stored = self._load_idempotent(session, endpoint, idempotency_key, request_hash)
        if stored is not None:
            return stored

        opportunity = self._get_visible_opportunity(session, actor_user, opportunity_id)
        if opportunity.closed_lost_at is not None and opportunity.close_reason == dto.close_reason:
            return self._to_read(opportunity)
        if opportunity.row_version != dto.row_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        stage = self._get_terminal_stage(session, opportunity.stage_id, "ClosedLost")
        before = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        ).model_dump(mode="json")

        opportunity.stage_id = stage.id
        opportunity.closed_lost_at = utcnow()
        opportunity.closed_won_at = None
        opportunity.close_reason = dto.close_reason
        opportunity.forecast_category = "Closed"
        opportunity.updated_at = utcnow()
        opportunity.row_version = opportunity.row_version + 1
        session.add(opportunity)

        updated = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="close_lost",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.closed_lost",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(opportunity.selling_legal_entity_id),
                "version": 1,
                "payload": {
                    "opportunity_id": str(opportunity.id),
                    "account_id": str(opportunity.account_id),
                    "close_reason": opportunity.close_reason,
                },
            }
        )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=opportunity.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", opportunity.id),
            ),
            legal_entity_id=opportunity.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        self._store_idempotent(session, endpoint, idempotency_key, request_hash, updated)
        session.commit()
        return self._to_read_model(session, opportunity.id)

    def reopen(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        dto: OpportunityReopenRequest,
    ) -> OpportunityRead:
        if "crm.opportunities.reopen" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing reopen permission")

        opportunity = self._get_visible_opportunity(session, actor_user, opportunity_id)
        if opportunity.row_version != dto.row_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        if dto.new_stage_id is not None:
            stage = session.scalar(
                select(CRMPipelineStage).where(and_(CRMPipelineStage.id == dto.new_stage_id, CRMPipelineStage.deleted_at.is_(None)))
            )
            if stage is None or stage.stage_type != "Open":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="new_stage_id must be an open stage")
            target_stage = stage
        else:
            target_stage = self.pipeline_service.get_default_open_stage(session, opportunity.selling_legal_entity_id)

        before = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        ).model_dump(mode="json")
        opportunity.stage_id = target_stage.id
        opportunity.closed_won_at = None
        opportunity.closed_lost_at = None
        opportunity.close_reason = None
        opportunity.forecast_category = "Pipeline"
        opportunity.updated_at = utcnow()
        opportunity.row_version = opportunity.row_version + 1
        session.add(opportunity)

        updated = self._to_read(
            opportunity,
            custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id),
        )
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type=self.entity_type,
            entity_id=str(opportunity.id),
            action="reopen",
            before=before,
            after=updated.model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.reopened",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(opportunity.selling_legal_entity_id),
                "version": 1,
                "payload": {"opportunity_id": str(opportunity.id), "stage_id": str(target_stage.id)},
            }
        )
        publish_index_requested(
            entity_type="opportunity",
            entity_id=opportunity.id,
            operation="upsert",
            fields=build_search_doc_for_opportunity(
                opportunity,
                custom_field_service.get_search_values_for_entity(session, "opportunity", opportunity.id),
            ),
            legal_entity_id=opportunity.selling_legal_entity_id,
            actor_user_id=actor_user.user_id,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._to_read_model(session, opportunity.id)

    def _resolve_create_stage(self, session: Session, dto: OpportunityCreate) -> CRMPipelineStage:
        if dto.stage_id is not None:
            stage = session.scalar(
                select(CRMPipelineStage)
                .where(and_(CRMPipelineStage.id == dto.stage_id, CRMPipelineStage.deleted_at.is_(None)))
                .options(selectinload(CRMPipelineStage.pipeline))
            )
            if stage is None or stage.pipeline is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stage not found")
            if stage.pipeline.selling_legal_entity_id not in {None, dto.selling_legal_entity_id}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="stage pipeline does not match selling legal entity",
                )
            return stage
        return self.pipeline_service.get_default_open_stage(session, dto.selling_legal_entity_id)

    def _validate_stage_rules(
        self,
        stage: CRMPipelineStage,
        amount: Decimal,
        expected_close_date: date | None,
    ) -> None:
        if stage.requires_amount and amount <= Decimal("0"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="stage requires amount > 0")
        if stage.requires_expected_close_date and expected_close_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="stage requires expected_close_date",
            )

    def _get_terminal_stage(
        self,
        session: Session,
        current_stage_id: uuid.UUID,
        stage_type: str,
    ) -> CRMPipelineStage:
        current_stage = session.scalar(
            select(CRMPipelineStage).where(and_(CRMPipelineStage.id == current_stage_id, CRMPipelineStage.deleted_at.is_(None)))
        )
        if current_stage is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="current stage not found")
        stage = session.scalar(
            select(CRMPipelineStage).where(
                and_(
                    CRMPipelineStage.pipeline_id == current_stage.pipeline_id,
                    CRMPipelineStage.stage_type == stage_type,
                    CRMPipelineStage.deleted_at.is_(None),
                )
            )
        )
        if stage is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"pipeline missing {stage_type} stage",
            )
        return stage

    def _validate_scope(self, actor_user: ActorUser, legal_entity_id: uuid.UUID, elevate_permission: str) -> None:
        if legal_entity_id not in actor_user.allowed_legal_entity_ids and elevate_permission not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="selling legal entity not allowed")

    def _can_view_opportunity(self, session: Session, actor_user: ActorUser, opportunity: CRMOpportunity) -> bool:
        if "crm.opportunities.read_all" in actor_user.permissions:
            return True
        if opportunity.selling_legal_entity_id not in set(actor_user.allowed_legal_entity_ids):
            return False
        account = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == opportunity.account_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None:
            return False
        allowed = set(actor_user.allowed_legal_entity_ids)
        return any(link.legal_entity_id in allowed for link in account.legal_entities)

    def _get_visible_account(self, session: Session, actor_user: ActorUser, account_id: uuid.UUID) -> CRMAccount:
        account = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == account_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
        if "crm.opportunities.read_all" in actor_user.permissions:
            return account
        allowed = set(actor_user.allowed_legal_entity_ids)
        if not any(link.legal_entity_id in allowed for link in account.legal_entities):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
        return account

    def _get_visible_opportunity(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
    ) -> CRMOpportunity:
        opportunity = session.scalar(
            select(CRMOpportunity).where(and_(CRMOpportunity.id == opportunity_id, CRMOpportunity.deleted_at.is_(None)))
        )
        if opportunity is None or not self._can_view_opportunity(session, actor_user, opportunity):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
        return opportunity

    def _to_read_model(self, session: Session, opportunity_id: uuid.UUID) -> OpportunityRead:
        opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity_id))
        if opportunity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
        custom_fields = custom_field_service.get_values_for_entity(session, "opportunity", opportunity.id)
        return self._to_read(opportunity, custom_fields)

    def _to_read(self, opportunity: CRMOpportunity, custom_fields: dict[str, Any] | None = None) -> OpportunityRead:
        return OpportunityRead.model_validate(
            {
                "id": opportunity.id,
                "account_id": opportunity.account_id,
                "name": opportunity.name,
                "stage_id": opportunity.stage_id,
                "selling_legal_entity_id": opportunity.selling_legal_entity_id,
                "region_code": opportunity.region_code,
                "currency_code": opportunity.currency_code,
                "amount": float(opportunity.amount),
                "owner_user_id": opportunity.owner_user_id,
                "expected_close_date": opportunity.expected_close_date,
                "probability": opportunity.probability,
                "forecast_category": opportunity.forecast_category,
                "primary_contact_id": opportunity.primary_contact_id,
                "close_reason": opportunity.close_reason,
                "revenue_quote_id": opportunity.revenue_quote_id,
                "revenue_order_id": opportunity.revenue_order_id,
                "revenue_handoff_status": opportunity.revenue_handoff_status,
                "revenue_handoff_mode": opportunity.revenue_handoff_mode,
                "revenue_handoff_last_error": opportunity.revenue_handoff_last_error,
                "revenue_handoff_requested_at": opportunity.revenue_handoff_requested_at,
                "revenue_handoff_completed_at": opportunity.revenue_handoff_completed_at,
                "closed_won_at": opportunity.closed_won_at,
                "closed_lost_at": opportunity.closed_lost_at,
                "created_at": opportunity.created_at,
                "updated_at": opportunity.updated_at,
                "deleted_at": opportunity.deleted_at,
                "row_version": opportunity.row_version,
                "custom_fields": custom_fields or {},
            }
        )

    def _request_hash(self, payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _resolve_revenue_handoff_request(self, dto: OpportunityCloseWonRequest) -> tuple[bool, str]:
        default_mode = "CREATE_DRAFT_QUOTE"
        if dto.revenue_handoff is not None:
            requested = bool(dto.revenue_handoff.requested)
            mode = dto.revenue_handoff.mode or default_mode
            return requested, mode

        requested = bool(dto.revenue_handoff_requested)
        mode = dto.revenue_handoff_mode or default_mode
        return requested, mode

    def _load_idempotent(
        self,
        session: Session,
        endpoint: str,
        key: str | None,
        request_hash: str,
    ) -> OpportunityRead | None:
        if not key:
            return None
        record = session.scalar(
            select(CRMIdempotencyKey).where(and_(CRMIdempotencyKey.endpoint == endpoint, CRMIdempotencyKey.key == key))
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key payload mismatch")
        return OpportunityRead.model_validate(json.loads(record.response_json))

    def _store_idempotent(
        self,
        session: Session,
        endpoint: str,
        key: str | None,
        request_hash: str,
        response: OpportunityRead,
    ) -> None:
        if not key:
            return
        session.add(
            CRMIdempotencyKey(
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                response_json=json.dumps(response.model_dump(mode="json")),
            )
        )


class RevenueHandoffService:
    valid_modes = {"CREATE_DRAFT_QUOTE", "CREATE_DRAFT_ORDER"}

    def __init__(self) -> None:
        self.opportunity_service = OpportunityService()

    def create_handoff_job(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        mode: str,
        idempotency_key: str,
    ) -> CRMJob:
        if mode not in self.valid_modes:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid handoff mode")

        job = CRMJob(
            job_type="REVENUE_HANDOFF",
            entity_type="opportunity",
            status="Queued",
            requested_by_user_id=_coerce_user_uuid(actor_user.user_id),
            legal_entity_id=actor_user.current_legal_entity_id,
            correlation_id=actor_user.correlation_id,
            params_json=json.dumps(
                {
                    "opportunity_id": str(opportunity_id),
                    "mode": mode,
                    "idempotency_key": idempotency_key,
                }
            ),
        )
        session.add(job)
        session.flush()
        return job

    def retry_handoff(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        *,
        sync: bool = False,
    ) -> CRMJob:
        opportunity = self.opportunity_service._get_visible_opportunity(session, actor_user, opportunity_id)
        if opportunity.closed_won_at is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "OPPORTUNITY_NOT_CLOSED_WON", "message": "Opportunity must be ClosedWon"},
            )
        if opportunity.revenue_handoff_status != "Failed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "REVENUE_HANDOFF_NOT_FAILED", "message": "Revenue handoff status is not Failed"},
            )

        mode = opportunity.revenue_handoff_mode or "CREATE_DRAFT_QUOTE"
        key = self._latest_handoff_key(session, opportunity_id) or str(uuid.uuid4())
        job = self.create_handoff_job(session, actor_user, opportunity_id, mode, key)
        opportunity.revenue_handoff_status = "Queued"
        opportunity.revenue_handoff_last_error = None
        opportunity.revenue_handoff_requested_at = utcnow()
        opportunity.updated_at = utcnow()
        opportunity.row_version = opportunity.row_version + 1
        session.add(opportunity)
        session.commit()

        if sync or get_settings().auto_run_jobs:
            RevenueHandoffJobRunner().run_revenue_handoff_job(session, actor_user, job.id)
            job = session.scalar(select(CRMJob).where(CRMJob.id == job.id)) or job

        return job

    def trigger_handoff(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
        mode: str,
        idempotency_key: str | None,
    ) -> OpportunityRevenueRead:
        if mode not in self.valid_modes:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid handoff mode")

        endpoint = "crm.opportunity.revenue_handoff"
        request_hash = self._request_hash({"opportunity_id": str(opportunity_id), "mode": mode})
        stored = self._load_idempotent(session, endpoint, idempotency_key, request_hash)
        if stored is not None:
            return stored

        opportunity = self.opportunity_service._get_visible_opportunity(session, actor_user, opportunity_id)
        stage = session.scalar(
            select(CRMPipelineStage).where(and_(CRMPipelineStage.id == opportunity.stage_id, CRMPipelineStage.deleted_at.is_(None)))
        )
        is_closed_won = opportunity.closed_won_at is not None or (stage is not None and stage.stage_type == "ClosedWon")
        if not is_closed_won:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "OPPORTUNITY_NOT_CLOSED_WON", "message": "Opportunity must be ClosedWon"},
            )

        before = self.opportunity_service._to_read(opportunity).model_dump(mode="json")
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.opportunity.revenue_handoff_requested",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(opportunity.selling_legal_entity_id),
                "version": 1,
                "payload": {"opportunity_id": str(opportunity.id), "mode": mode},
            }
        )

        if mode == "CREATE_DRAFT_QUOTE" and opportunity.revenue_quote_id is not None:
            response = self.get_revenue_status(session, actor_user, opportunity.id)
            self._store_idempotent(session, endpoint, idempotency_key, request_hash, response)
            session.commit()
            return response

        if mode == "CREATE_DRAFT_ORDER" and opportunity.revenue_order_id is not None:
            response = self.get_revenue_status(session, actor_user, opportunity.id)
            self._store_idempotent(session, endpoint, idempotency_key, request_hash, response)
            session.commit()
            return response

        revenue_client = self._get_client(session)
        try:
            if mode == "CREATE_DRAFT_QUOTE":
                if not idempotency_key:
                    idempotency_key = f"{uuid.uuid4()}"
                quote_id = revenue_client.create_draft_quote(opportunity.id, idempotency_key)
                opportunity.revenue_quote_id = quote_id
            else:
                if not idempotency_key:
                    idempotency_key = f"{uuid.uuid4()}"
                order_id = revenue_client.create_draft_order(opportunity.id, idempotency_key)
                opportunity.revenue_order_id = order_id

            opportunity.updated_at = utcnow()
            opportunity.row_version = opportunity.row_version + 1
            session.add(opportunity)

            response = self.get_revenue_status(session, actor_user, opportunity.id)

            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type="crm.opportunity",
                entity_id=str(opportunity.id),
                action="revenue_handoff",
                before=before,
                after=response.model_dump(mode="json"),
                correlation_id=actor_user.correlation_id,
            )
            events.publish(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "crm.opportunity.revenue_handoff_succeeded",
                    "occurred_at": utcnow().isoformat(),
                    "actor_user_id": actor_user.user_id,
                    "legal_entity_id": str(opportunity.selling_legal_entity_id),
                    "version": 1,
                    "payload": {
                        "opportunity_id": str(opportunity.id),
                        "mode": mode,
                        "quote_id": str(opportunity.revenue_quote_id) if opportunity.revenue_quote_id else None,
                        "order_id": str(opportunity.revenue_order_id) if opportunity.revenue_order_id else None,
                    },
                }
            )
            self._store_idempotent(session, endpoint, idempotency_key, request_hash, response)
            session.commit()
            return response
        except Exception as exc:
            session.rollback()
            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type="crm.opportunity",
                entity_id=str(opportunity.id),
                action="revenue_handoff",
                before=before,
                after={"mode": mode, "error": str(exc)},
                correlation_id=actor_user.correlation_id,
            )
            events.publish(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "crm.opportunity.revenue_handoff_failed",
                    "occurred_at": utcnow().isoformat(),
                    "actor_user_id": actor_user.user_id,
                    "legal_entity_id": str(opportunity.selling_legal_entity_id),
                    "version": 1,
                    "payload": {
                        "opportunity_id": str(opportunity.id),
                        "mode": mode,
                        "error": str(exc),
                    },
                }
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "REVENUE_UNAVAILABLE", "message": "Revenue module unavailable"},
            )

    def get_revenue_status(
        self,
        session: Session,
        actor_user: ActorUser,
        opportunity_id: uuid.UUID,
    ) -> OpportunityRevenueRead:
        opportunity = self.opportunity_service._get_visible_opportunity(session, actor_user, opportunity_id)
        revenue_client = self._get_client(session)

        quote_payload: RevenueDocStatusRead | None = None
        order_payload: RevenueDocStatusRead | None = None
        if opportunity.revenue_quote_id is not None:
            quote_payload = RevenueDocStatusRead.model_validate(revenue_client.get_quote(opportunity.revenue_quote_id))
        if opportunity.revenue_order_id is not None:
            order_payload = RevenueDocStatusRead.model_validate(revenue_client.get_order(opportunity.revenue_order_id))

        return OpportunityRevenueRead(quote=quote_payload, order=order_payload)

    def _get_client(self, session: Session) -> RevenueClient:
        return StubRevenueClient(session)

    def _latest_handoff_key(self, session: Session, opportunity_id: uuid.UUID) -> str | None:
        jobs = session.scalars(
            select(CRMJob)
            .where(and_(CRMJob.job_type == "REVENUE_HANDOFF", CRMJob.entity_type == "opportunity"))
            .order_by(CRMJob.created_at.desc())
        ).all()
        for job in jobs:
            try:
                payload = json.loads(job.params_json)
            except json.JSONDecodeError:
                continue
            if payload.get("opportunity_id") == str(opportunity_id):
                key = payload.get("idempotency_key")
                if isinstance(key, str) and key:
                    return key
        return None

    def _request_hash(self, payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _load_idempotent(
        self,
        session: Session,
        endpoint: str,
        key: str | None,
        request_hash: str,
    ) -> OpportunityRevenueRead | None:
        if not key:
            return None
        record = session.scalar(
            select(CRMIdempotencyKey).where(and_(CRMIdempotencyKey.endpoint == endpoint, CRMIdempotencyKey.key == key))
        )
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotency key payload mismatch")
        return OpportunityRevenueRead.model_validate(json.loads(record.response_json))

    def _store_idempotent(
        self,
        session: Session,
        endpoint: str,
        key: str | None,
        request_hash: str,
        response: OpportunityRevenueRead,
    ) -> None:
        if not key:
            return
        existing = session.scalar(
            select(CRMIdempotencyKey).where(and_(CRMIdempotencyKey.endpoint == endpoint, CRMIdempotencyKey.key == key))
        )
        if existing is not None:
            return
        session.add(
            CRMIdempotencyKey(
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                response_json=json.dumps(response.model_dump(mode="json")),
            )
        )


class RevenueHandoffJobRunner:
    def run_revenue_handoff_job(self, session: Session, actor_user: ActorUser, job_id: uuid.UUID) -> CRMJob:
        job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.job_type != "REVENUE_HANDOFF":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid job type")
        if job.status == "Succeeded":
            return job

        params = json.loads(job.params_json)
        opportunity_id = uuid.UUID(str(params["opportunity_id"]))
        mode = str(params["mode"])
        idempotency_key = str(params["idempotency_key"])
        correlation_id = str(job.correlation_id or actor_user.correlation_id or "") or None
        runtime_actor = _actor_with_correlation_id(actor_user, correlation_id)
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        final_status = "Failed"

        with tracer.start_as_current_span("crm.job.run") as job_span:
            job_span.set_attribute("job_id", str(job.id))
            job_span.set_attribute("job_type", job.job_type)
            job_span.set_attribute("correlation_id", correlation_id)
            job_span.set_attribute("opportunity_id", str(opportunity_id))

            logger.info(
                "job.started",
                extra={
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "status": "Running",
                    "duration_ms": 0.0,
                    "opportunity_id": str(opportunity_id),
                    "user_id": runtime_actor.user_id,
                },
            )

            opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity_id))
            if opportunity is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")

            job.status = "Running"
            job.started_at = utcnow()
            session.add(job)
            session.commit()

            handoff_service = RevenueHandoffService()
            try:
                with tracer.start_as_current_span("crm.revenue_handoff") as handoff_span:
                    handoff_span.set_attribute("job_id", str(job.id))
                    handoff_span.set_attribute("opportunity_id", str(opportunity_id))
                    handoff_span.set_attribute("correlation_id", correlation_id)
                    payload = handoff_service.trigger_handoff(session, runtime_actor, opportunity_id, mode, idempotency_key)

                opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity_id))
                if opportunity is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")

                opportunity.revenue_handoff_status = "Succeeded"
                opportunity.revenue_handoff_completed_at = utcnow()
                opportunity.revenue_handoff_last_error = None
                opportunity.updated_at = utcnow()
                opportunity.row_version = opportunity.row_version + 1
                session.add(opportunity)

                job.status = "Succeeded"
                job.result_json = json.dumps(payload.model_dump(mode="json"))
                job.finished_at = utcnow()
                session.add(job)

                audit.record(
                    actor_user_id=runtime_actor.user_id,
                    entity_type="crm.job",
                    entity_id=str(job.id),
                    action="revenue_handoff_job",
                    before={"status": "Running"},
                    after={"status": "Succeeded", "opportunity_id": str(opportunity_id)},
                    correlation_id=runtime_actor.correlation_id,
                )
                session.commit()
                logger.info(
                    "job.finished",
                    extra={
                        "job_id": str(job.id),
                        "job_type": job.job_type,
                        "status": "Succeeded",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "opportunity_id": str(opportunity_id),
                        "user_id": runtime_actor.user_id,
                    },
                )
                final_status = "Succeeded"
            except Exception as exc:
                session.rollback()
                job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
                opportunity = session.scalar(select(CRMOpportunity).where(CRMOpportunity.id == opportunity_id))
                if job is None or opportunity is None:
                    raise

                opportunity.revenue_handoff_status = "Failed"
                opportunity.revenue_handoff_last_error = str(exc)[:2000]
                opportunity.updated_at = utcnow()
                opportunity.row_version = opportunity.row_version + 1
                session.add(opportunity)

                job.status = "Failed"
                job.result_json = json.dumps({"error": str(exc)[:2000]})
                job.finished_at = utcnow()
                session.add(job)

                audit.record(
                    actor_user_id=runtime_actor.user_id,
                    entity_type="crm.job",
                    entity_id=str(job.id),
                    action="revenue_handoff_job",
                    before={"status": "Running"},
                    after={"status": "Failed", "error": str(exc)[:2000], "opportunity_id": str(opportunity_id)},
                    correlation_id=runtime_actor.correlation_id,
                )
                session.commit()
                job_span.record_exception(exc)
                job_span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.info(
                    "job.finished",
                    extra={
                        "job_id": str(job.id),
                        "job_type": job.job_type,
                        "status": "Failed",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "error": str(exc)[:500],
                        "opportunity_id": str(opportunity_id),
                        "user_id": runtime_actor.user_id,
                    },
                )
                final_status = "Failed"
            finally:
                duration = time.perf_counter() - started
                observe_job(job_type=job.job_type, status=final_status, duration=duration)
                reset_correlation_id(token)

        final_job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
        if final_job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return final_job


class ImportExportService:
    valid_job_types = {"CSV_IMPORT", "CSV_EXPORT"}
    valid_entity_types = {"account", "contact"}
    valid_statuses = {"Queued", "Running", "Succeeded", "Failed", "PartiallySucceeded"}

    def __init__(self) -> None:
        self.account_service = AccountService()
        self.contact_service = ContactService()

    def create_job(
        self,
        session: Session,
        actor_user: ActorUser,
        *,
        job_type: str,
        entity_type: str,
        params: dict[str, Any],
    ) -> CRMJob:
        if job_type not in self.valid_job_types:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid job_type")
        if entity_type not in self.valid_entity_types:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid entity_type")

        params_with_correlation = {**params}
        job = CRMJob(
            job_type=job_type,
            entity_type=entity_type,
            status="Queued",
            requested_by_user_id=_coerce_user_uuid(actor_user.user_id),
            legal_entity_id=actor_user.current_legal_entity_id,
            correlation_id=actor_user.correlation_id,
            params_json=json.dumps(params_with_correlation, default=str),
        )
        session.add(job)
        session.flush()

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm_job",
            entity_id=str(job.id),
            action="create",
            before=None,
            after={
                "job_type": job.job_type,
                "entity_type": job.entity_type,
                "status": job.status,
            },
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        return self._load_job(session, job.id)

    def run_job_sync(self, session: Session, actor_user: ActorUser, job_id: uuid.UUID) -> CRMJob:
        job = self._load_job(session, job_id)
        self._assert_job_access(actor_user, job)
        correlation_id = str(job.correlation_id or actor_user.correlation_id or "") or None
        runtime_actor = _actor_with_correlation_id(actor_user, correlation_id)
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        final_status = "Failed"
        with tracer.start_as_current_span("crm.job.run") as job_span:
            job_span.set_attribute("job_id", str(job.id))
            job_span.set_attribute("job_type", job.job_type)
            job_span.set_attribute("correlation_id", correlation_id)

            logger.info(
                "job.started",
                extra={
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "status": "Running",
                    "duration_ms": 0.0,
                    "user_id": runtime_actor.user_id,
                },
            )

            try:
                job.status = "Running"
                job.started_at = utcnow()
                job.finished_at = None
                session.add(job)
                session.commit()

                try:
                    from app.crm.import_export import execute_job

                    result = execute_job(
                        session,
                        runtime_actor,
                        job,
                        account_service=self.account_service,
                        contact_service=self.contact_service,
                    )
                    created_count = int(result.get("created_count", 0))
                    updated_count = int(result.get("updated_count", 0))
                    error_count = int(result.get("error_count", 0))

                    if error_count > 0 and (created_count + updated_count) > 0:
                        job.status = "PartiallySucceeded"
                    elif error_count > 0:
                        job.status = "Failed"
                    else:
                        job.status = "Succeeded"

                    job.result_json = json.dumps(result, default=str)
                    job.finished_at = utcnow()
                    session.add(job)
                    session.commit()
                    logger.info(
                        "job.finished",
                        extra={
                            "job_id": str(job.id),
                            "job_type": job.job_type,
                            "status": job.status,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                            "user_id": runtime_actor.user_id,
                        },
                    )
                    final_status = job.status
                except Exception as exc:
                    session.rollback()
                    job = self._load_job(session, job_id)
                    job.status = "Failed"
                    job.finished_at = utcnow()
                    job.result_json = json.dumps({"error": str(exc)})
                    session.add(job)
                    session.commit()
                    job_span.record_exception(exc)
                    job_span.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.info(
                        "job.finished",
                        extra={
                            "job_id": str(job.id),
                            "job_type": job.job_type,
                            "status": "Failed",
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                            "error": str(exc)[:500],
                            "user_id": runtime_actor.user_id,
                        },
                    )
                    final_status = "Failed"
            finally:
                duration = time.perf_counter() - started
                observe_job(job_type=job.job_type, status=final_status, duration=duration)
                reset_correlation_id(token)

        return self._load_job(session, job_id)

    def get_job(self, session: Session, actor_user: ActorUser, job_id: uuid.UUID) -> CRMJob:
        job = self._load_job(session, job_id)
        self._assert_job_access(actor_user, job)
        return job

    def list_workflow_execution_jobs(
        self,
        session: Session,
        actor_user: ActorUser,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        rule_id: uuid.UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> list[CRMJob]:
        stmt: Select[tuple[CRMJob]] = select(CRMJob).where(CRMJob.job_type == "WORKFLOW_EXECUTION")

        if entity_type:
            stmt = stmt.where(CRMJob.entity_type == entity_type)

        if "crm.jobs.read_all" not in actor_user.permissions:
            allowed = set(actor_user.allowed_legal_entity_ids)
            if allowed:
                stmt = stmt.where(or_(CRMJob.legal_entity_id.is_(None), CRMJob.legal_entity_id.in_(allowed)))
            else:
                stmt = stmt.where(CRMJob.legal_entity_id.is_(None))

        rows = session.scalars(stmt.order_by(CRMJob.created_at.desc())).all()
        if rule_id is not None:
            rows = [
                item
                for item in rows
                if str((json.loads(item.params_json or "{}")).get("rule_id")) == str(rule_id)
            ]
        if entity_id is not None:
            rows = [
                item
                for item in rows
                if str((json.loads(item.params_json or "{}")).get("entity_id")) == str(entity_id)
            ]

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        return rows[offset : offset + limit]

    def get_workflow_execution_job(self, session: Session, actor_user: ActorUser, job_id: uuid.UUID) -> CRMJob:
        job = self._load_job(session, job_id)
        if job.job_type != "WORKFLOW_EXECUTION":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

        if "crm.jobs.read_all" in actor_user.permissions:
            return job

        allowed = set(actor_user.allowed_legal_entity_ids)
        if job.legal_entity_id is None or job.legal_entity_id in allowed:
            return job
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    def get_job_artifact(
        self,
        session: Session,
        actor_user: ActorUser,
        job_id: uuid.UUID,
        artifact_type: str,
    ) -> CRMJobArtifact:
        job = self.get_job(session, actor_user, job_id)
        artifact = session.scalar(
            select(CRMJobArtifact).where(
                and_(CRMJobArtifact.job_id == job.id, CRMJobArtifact.artifact_type == artifact_type)
            )
        )
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        return artifact

    def to_response(self, job: CRMJob) -> dict[str, Any]:
        result_data: dict[str, Any] | None = None
        if job.result_json:
            result_data = json.loads(job.result_json)

        artifacts = [
            {
                "artifact_type": artifact.artifact_type,
                "file_id": str(artifact.file_id),
                "created_at": artifact.created_at.isoformat(),
            }
            for artifact in sorted(job.artifacts, key=lambda item: item.created_at)
        ]
        return {
            "id": str(job.id),
            "job_type": job.job_type,
            "entity_type": job.entity_type,
            "status": job.status,
            "requested_by_user_id": str(job.requested_by_user_id),
            "legal_entity_id": str(job.legal_entity_id) if job.legal_entity_id else None,
            "correlation_id": job.correlation_id,
            "params": json.loads(job.params_json),
            "result": result_data,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "created_at": job.created_at.isoformat(),
            "artifacts": artifacts,
        }

    def _load_job(self, session: Session, job_id: uuid.UUID) -> CRMJob:
        job = session.scalar(
            select(CRMJob)
            .where(CRMJob.id == job_id)
            .options(selectinload(CRMJob.artifacts))
        )
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return job

    def _assert_job_access(self, actor_user: ActorUser, job: CRMJob) -> None:
        if "crm.jobs.read_all" in actor_user.permissions:
            return
        if job.requested_by_user_id != _coerce_user_uuid(actor_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")


class WorkflowService:
    _entity_models = {
        "account": CRMAccount,
        "contact": CRMContact,
        "lead": CRMLead,
        "opportunity": CRMOpportunity,
    }

    _set_field_allowlist: dict[str, set[str]] = {
        "account": {"name", "status", "owner_user_id", "primary_region_code", "default_currency_code", "external_reference"},
        "contact": {
            "first_name",
            "last_name",
            "email",
            "phone",
            "title",
            "department",
            "locale",
            "timezone",
            "owner_user_id",
            "is_primary",
        },
        "lead": {
            "status",
            "source",
            "owner_user_id",
            "region_code",
            "company_name",
            "contact_first_name",
            "contact_last_name",
            "email",
            "phone",
            "qualification_notes",
            "disqualify_reason_code",
            "disqualify_notes",
        },
        "opportunity": {
            "name",
            "stage_id",
            "region_code",
            "currency_code",
            "amount",
            "owner_user_id",
            "expected_close_date",
            "probability",
            "forecast_category",
            "primary_contact_id",
            "close_reason",
        },
    }

    def list_rules(
        self,
        session: Session,
        actor_user: ActorUser,
        *,
        legal_entity_id: uuid.UUID | None = None,
        trigger_event: str | None = None,
    ) -> list[WorkflowRuleRead]:
        self._require_permission(actor_user, "crm.workflows.read")
        if legal_entity_id is not None:
            self._enforce_legal_entity_access(actor_user, legal_entity_id)

        stmt: Select[tuple[CRMWorkflowRule]] = select(CRMWorkflowRule).where(CRMWorkflowRule.deleted_at.is_(None))
        if trigger_event:
            stmt = stmt.where(CRMWorkflowRule.trigger_event == trigger_event)

        if legal_entity_id is not None:
            stmt = stmt.where(
                or_(
                    CRMWorkflowRule.legal_entity_id.is_(None),
                    CRMWorkflowRule.legal_entity_id == legal_entity_id,
                )
            )
        elif actor_user.allowed_legal_entity_ids:
            stmt = stmt.where(
                or_(
                    CRMWorkflowRule.legal_entity_id.is_(None),
                    CRMWorkflowRule.legal_entity_id.in_(actor_user.allowed_legal_entity_ids),
                )
            )
        else:
            stmt = stmt.where(CRMWorkflowRule.legal_entity_id.is_(None))

        rows = session.scalars(stmt.order_by(CRMWorkflowRule.created_at.desc())).all()
        return [self._to_rule_read(row) for row in rows]

    def get_active_rules_for_trigger(
        self,
        session: Session,
        trigger_event: str,
        legal_entity_id: uuid.UUID | None,
    ) -> list[CRMWorkflowRule]:
        stmt: Select[tuple[CRMWorkflowRule]] = select(CRMWorkflowRule).where(
            and_(
                CRMWorkflowRule.deleted_at.is_(None),
                CRMWorkflowRule.is_active.is_(True),
                CRMWorkflowRule.trigger_event == trigger_event,
            )
        )
        if legal_entity_id is None:
            stmt = stmt.where(CRMWorkflowRule.legal_entity_id.is_(None))
        else:
            stmt = stmt.where(
                or_(
                    CRMWorkflowRule.legal_entity_id.is_(None),
                    CRMWorkflowRule.legal_entity_id == legal_entity_id,
                )
            )
        return session.scalars(stmt.order_by(CRMWorkflowRule.created_at.asc())).all()

    def create_rule(self, session: Session, dto: WorkflowRuleCreate, actor_user: ActorUser) -> WorkflowRuleRead:
        self._require_permission(actor_user, "crm.workflows.manage")
        if dto.legal_entity_id is not None:
            self._enforce_legal_entity_access(actor_user, dto.legal_entity_id)

        rule = CRMWorkflowRule(
            name=dto.name.strip(),
            description=dto.description,
            is_active=dto.is_active,
            legal_entity_id=dto.legal_entity_id,
            trigger_event=dto.trigger_event.strip(),
            cooldown_seconds=dto.cooldown_seconds,
            condition_json=dto.condition_json,
            actions_json=dto.actions_json,
        )
        session.add(rule)
        session.flush()

        after = self._to_rule_read(rule).model_dump(mode="json")
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.workflow_rule",
            entity_id=str(rule.id),
            action="workflow.rule.created",
            before=None,
            after=after,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        session.refresh(rule)
        return self._to_rule_read(rule)

    def update_rule(
        self,
        session: Session,
        rule_id: uuid.UUID,
        dto: WorkflowRuleUpdate,
        actor_user: ActorUser,
    ) -> WorkflowRuleRead:
        self._require_permission(actor_user, "crm.workflows.manage")
        rule = self._load_rule(session, rule_id)
        before = self._to_rule_read(rule).model_dump(mode="json")

        payload = dto.model_dump(exclude_unset=True)
        if "legal_entity_id" in payload and payload["legal_entity_id"] is not None:
            self._enforce_legal_entity_access(actor_user, payload["legal_entity_id"])

        for key in [
            "name",
            "description",
            "is_active",
            "legal_entity_id",
            "trigger_event",
            "cooldown_seconds",
            "condition_json",
            "actions_json",
        ]:
            if key in payload:
                setattr(rule, key, payload[key])
        rule.updated_at = utcnow()
        session.add(rule)
        session.flush()

        after = self._to_rule_read(rule).model_dump(mode="json")
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.workflow_rule",
            entity_id=str(rule.id),
            action="workflow.rule.updated",
            before=before,
            after=after,
            correlation_id=actor_user.correlation_id,
        )
        session.commit()
        session.refresh(rule)
        return self._to_rule_read(rule)

    def soft_delete_rule(self, session: Session, rule_id: uuid.UUID, actor_user: ActorUser) -> None:
        self._require_permission(actor_user, "crm.workflows.manage")
        rule = self._load_rule(session, rule_id)
        before = self._to_rule_read(rule).model_dump(mode="json")

        rule.deleted_at = utcnow()
        rule.updated_at = utcnow()
        session.add(rule)
        session.flush()

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.workflow_rule",
            entity_id=str(rule.id),
            action="workflow.rule.deleted",
            before=before,
            after={"deleted_at": rule.deleted_at.isoformat()},
            correlation_id=actor_user.correlation_id,
        )
        session.commit()

    def evaluate_rule(
        self,
        session: Session,
        rule: CRMWorkflowRule,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> tuple[bool, dict[str, Any]]:
        context_bundle = self._build_entity_context(session, entity_type, entity_id)
        condition = self._parse_condition(rule.condition_json)
        matched = self._eval_condition(condition, context_bundle["context"])
        return matched, context_bundle

    def execute_rule(
        self,
        session: Session,
        actor_user: ActorUser,
        rule_id: uuid.UUID,
        entity_ref: WorkflowEntityRef,
        dry_run: bool,
        *,
        max_actions: int | None = None,
        max_set_field: int | None = None,
    ) -> WorkflowDryRunResponse:
        if "crm.workflows.manage" not in actor_user.permissions and "crm.workflows.execute" not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: crm.workflows.execute")

        rule = self._load_rule(session, rule_id)
        if not rule.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="workflow rule is inactive")

        visible_scope = ensure_entity_visible(session, actor_user, entity_ref.type, entity_ref.id)
        if rule.legal_entity_id is not None and visible_scope.get("legal_entity_id") != rule.legal_entity_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="rule scope does not match target entity")

        matched, context_bundle = self.evaluate_rule(session, rule, entity_ref.type, entity_ref.id)

        planned_actions: list[dict[str, Any]] = []
        planned_mutations: dict[str, Any] = {
            "set_field": [],
            "create_task": [],
            "notify": [],
        }

        if matched:
            actions_executed_count = 0
            set_field_executed_count = 0
            for action_payload in rule.actions_json:
                action = self._parse_action(action_payload)

                if max_actions is not None and actions_executed_count >= max_actions:
                    raise WorkflowLimitExceededError(
                        code="WORKFLOW_LIMIT_EXCEEDED",
                        summary={
                            "reason": "MAX_ACTIONS",
                            "max_actions": max_actions,
                            "actions_executed_count": actions_executed_count,
                            "set_field_executed_count": set_field_executed_count,
                            "matched": matched,
                            "partial_planned_actions": planned_actions,
                            "partial_planned_mutations": planned_mutations,
                        },
                    )

                if isinstance(action, WorkflowActionSetField):
                    if max_set_field is not None and set_field_executed_count >= max_set_field:
                        raise WorkflowLimitExceededError(
                            code="WORKFLOW_LIMIT_EXCEEDED",
                            summary={
                                "reason": "MAX_SET_FIELD",
                                "max_set_field": max_set_field,
                                "actions_executed_count": actions_executed_count,
                                "set_field_executed_count": set_field_executed_count,
                                "matched": matched,
                                "partial_planned_actions": planned_actions,
                                "partial_planned_mutations": planned_mutations,
                            },
                        )

                action_plan = self._execute_action(
                    session,
                    actor_user,
                    context_bundle,
                    action,
                    dry_run=dry_run,
                )
                planned_actions.append(action_plan)
                actions_executed_count += 1
                if action.type == "SET_FIELD":
                    planned_mutations["set_field"].append(action_plan)
                    set_field_executed_count += 1
                elif action.type == "CREATE_TASK":
                    planned_mutations["create_task"].append(action_plan)
                elif action.type == "NOTIFY":
                    planned_mutations["notify"].append(action_plan)

        response = WorkflowDryRunResponse(
            matched=matched,
            planned_actions=planned_actions,
            planned_mutations=planned_mutations,
        )

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.workflow_rule",
            entity_id=str(rule.id),
            action="workflow.dry_run" if dry_run else "workflow.executed",
            before=None,
            after={
                "matched": matched,
                "planned_action_count": len(planned_actions),
                "entity_type": entity_ref.type,
                "entity_id": str(entity_ref.id),
                "dry_run": dry_run,
            },
            correlation_id=actor_user.correlation_id,
        )

        if dry_run:
            return response

        session.commit()
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.workflow.executed",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(visible_scope["legal_entity_id"]) if visible_scope.get("legal_entity_id") is not None else None
                ),
                "version": 1,
                "payload": {
                    "rule_id": str(rule.id),
                    "matched": matched,
                    "planned_action_count": len(planned_actions),
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                },
            }
        )
        return response

    def _execute_action(
        self,
        session: Session,
        actor_user: ActorUser,
        context_bundle: dict[str, Any],
        action: WorkflowAction,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        if isinstance(action, WorkflowActionSetField):
            return self._apply_set_field(session, actor_user, context_bundle, action, dry_run=dry_run)
        if isinstance(action, WorkflowActionCreateTask):
            return self._apply_create_task(session, actor_user, context_bundle, action, dry_run=dry_run)
        return self._apply_notify(session, context_bundle, action, dry_run=dry_run)

    def _apply_set_field(
        self,
        session: Session,
        actor_user: ActorUser,
        context_bundle: dict[str, Any],
        action: WorkflowActionSetField,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        context = context_bundle["context"]
        resource = f"crm.{context_bundle['entity_type']}"
        auth_ctx = _to_auth_context(
            actor_user,
            tenant_id=(
                str(context_bundle.get("legal_entity_id")) if context_bundle.get("legal_entity_id") is not None else None
            ),
        )
        existing_scope = {
            "company_code": str(context_bundle.get("legal_entity_id")) if context_bundle.get("legal_entity_id") else None,
            "region_code": context.get("region_code") or context.get("primary_region_code"),
        }
        exists, before = self._resolve_path(context, action.path)
        _ = exists
        plan = {
            "type": "SET_FIELD",
            "path": action.path,
            "before": self._serialize_value(before),
            "after": self._serialize_value(action.value),
        }

        if action.path.startswith("custom_fields."):
            field_key = action.path.split(".", 1)[1]
            if not field_key:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid custom field path")
            try:
                validate_rls_write(
                    resource,
                    {f"custom_fields.{field_key}": action.value},
                    auth_ctx,
                    existing_scope=existing_scope,
                    action="workflow.set_field",
                )
                validate_fls_write(resource, {f"custom_fields.{field_key}": action.value}, auth_ctx)
            except ForbiddenFieldError as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"forbidden_fields": exc.fields})
            except AuthorizationError as exc:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
            if dry_run:
                return plan

            updated_values = CustomFieldService().set_values_for_entity(
                session,
                context_bundle["entity_type"],
                context_bundle["entity_id"],
                {field_key: action.value},
                context_bundle["legal_entity_id"],
                enforce_required=False,
            )
            context["custom_fields"] = updated_values
            return plan

        if "." in action.path:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported SET_FIELD path")

        allowed = self._set_field_allowlist[context_bundle["entity_type"]]
        if action.path not in allowed:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"field not allowed: {action.path}")

        try:
            validate_rls_write(
                resource,
                {action.path: action.value},
                auth_ctx,
                existing_scope=existing_scope,
                action="workflow.set_field",
            )
            validate_fls_write(resource, {action.path: action.value}, auth_ctx)
        except ForbiddenFieldError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"forbidden_fields": exc.fields})
        except AuthorizationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

        if dry_run:
            return plan

        entity = context_bundle["entity"]
        coerced = self._coerce_standard_value(entity, action.path, action.value)
        setattr(entity, action.path, coerced)
        if hasattr(entity, "updated_at"):
            entity.updated_at = utcnow()
        if hasattr(entity, "row_version"):
            entity.row_version = int(entity.row_version) + 1
        session.add(entity)
        session.flush()
        context[action.path] = getattr(entity, action.path)
        self._publish_entity_updated_event(context_bundle, actor_user, entity)
        return plan

    def _publish_entity_updated_event(self, context_bundle: dict[str, Any], actor_user: ActorUser, entity: Any) -> None:
        event_type_map = {
            "account": "crm.account.updated",
            "contact": "crm.contact.updated",
            "lead": "crm.lead.updated",
            "opportunity": "crm.opportunity.updated",
        }
        payload_key_map = {
            "account": "account_id",
            "contact": "contact_id",
            "lead": "lead_id",
            "opportunity": "opportunity_id",
        }

        entity_type = str(context_bundle.get("entity_type"))
        event_type = event_type_map.get(entity_type)
        payload_key = payload_key_map.get(entity_type)
        if event_type is None or payload_key is None:
            return

        entity_id = context_bundle.get("entity_id")
        legal_entity_id = context_bundle.get("legal_entity_id")
        payload: dict[str, Any] = {payload_key: str(entity_id)}
        if hasattr(entity, "row_version"):
            payload["row_version"] = getattr(entity, "row_version")

        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": str(legal_entity_id) if legal_entity_id is not None else None,
                "version": 1,
                "payload": payload,
            }
        )

    def _apply_create_task(
        self,
        session: Session,
        actor_user: ActorUser,
        context_bundle: dict[str, Any],
        action: WorkflowActionCreateTask,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        due_at = utcnow() + timedelta(days=action.due_in_days)
        ensure_entity_visible(session, actor_user, action.entity_ref.type, action.entity_ref.id)

        plan = {
            "type": "CREATE_TASK",
            "would_create": {
                "entity_type": action.entity_ref.type,
                "entity_id": str(action.entity_ref.id),
                "title": action.title,
                "due_at": due_at.isoformat(),
                "assigned_to_user_id": str(action.assigned_to_user_id),
            },
        }
        if dry_run:
            return plan

        task = CRMActivity(
            entity_type=action.entity_ref.type,
            entity_id=action.entity_ref.id,
            activity_type="Task",
            subject=action.title,
            owner_user_id=_coerce_user_uuid(actor_user.user_id),
            assigned_to_user_id=action.assigned_to_user_id,
            due_at=due_at,
            status="Open",
        )
        session.add(task)
        session.flush()
        return plan

    def _apply_notify(
        self,
        session: Session,
        context_bundle: dict[str, Any],
        action: WorkflowActionNotify,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        payload = action.payload or {}
        recipient_raw = payload.get("recipient_user_id") or context_bundle["context"].get("owner_user_id")
        if recipient_raw is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="recipient_user_id is required for NOTIFY")
        try:
            recipient_user_id = uuid.UUID(str(recipient_raw))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid recipient_user_id") from exc

        activity_id_raw = payload.get("activity_id")
        if activity_id_raw is None:
            activity_id = context_bundle["entity_id"]
        else:
            try:
                activity_id = uuid.UUID(str(activity_id_raw))
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid activity_id") from exc

        plan = {
            "type": "NOTIFY",
            "would_create": {
                "intent_type": action.notification_type,
                "recipient_user_id": str(recipient_user_id),
                "entity_type": context_bundle["entity_type"],
                "entity_id": str(context_bundle["entity_id"]),
                "payload": payload,
            },
        }
        if dry_run:
            return plan

        intent = CRMNotificationIntent(
            intent_type=action.notification_type,
            recipient_user_id=recipient_user_id,
            entity_type=context_bundle["entity_type"],
            entity_id=context_bundle["entity_id"],
            activity_id=activity_id,
            payload_json=json.dumps(payload),
        )
        session.add(intent)
        session.flush()
        return plan

    def _build_entity_context(self, session: Session, entity_type: str, entity_id: uuid.UUID) -> dict[str, Any]:
        if entity_type not in self._entity_models:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid entity_type")

        if entity_type == "account":
            entity = session.scalar(
                select(CRMAccount)
                .where(and_(CRMAccount.id == entity_id, CRMAccount.deleted_at.is_(None)))
                .options(selectinload(CRMAccount.legal_entities))
            )
            if entity is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
            legal_entity_id = entity.legal_entities[0].legal_entity_id if entity.legal_entities else None
        elif entity_type == "contact":
            entity = session.scalar(
                select(CRMContact)
                .where(and_(CRMContact.id == entity_id, CRMContact.deleted_at.is_(None)))
                .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
            )
            if entity is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
            legal_entity_id = entity.account.legal_entities[0].legal_entity_id if entity.account and entity.account.legal_entities else None
        elif entity_type == "lead":
            entity = session.scalar(select(CRMLead).where(and_(CRMLead.id == entity_id, CRMLead.deleted_at.is_(None))))
            if entity is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
            legal_entity_id = entity.selling_legal_entity_id
        else:
            entity = session.scalar(
                select(CRMOpportunity)
                .where(and_(CRMOpportunity.id == entity_id, CRMOpportunity.deleted_at.is_(None)))
            )
            if entity is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
            legal_entity_id = entity.selling_legal_entity_id

        custom_fields = CustomFieldService().get_values_for_entity(session, entity_type, entity_id)
        context = self._to_context_dict(entity)
        context["custom_fields"] = custom_fields
        return {
            "entity": entity,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "legal_entity_id": legal_entity_id,
            "context": context,
        }

    def _to_context_dict(self, entity: Any) -> dict[str, Any]:
        mapper = inspect(entity).mapper
        context: dict[str, Any] = {}
        for column in mapper.column_attrs:
            context[column.key] = getattr(entity, column.key)
        return context

    def _resolve_path(self, context: dict[str, Any], path: str) -> tuple[bool, Any]:
        current: Any = context
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return False, None
            current = current[segment]
        return True, current

    def _eval_condition(self, condition: WorkflowCondition, context: dict[str, Any]) -> bool:
        if isinstance(condition, WorkflowConditionAll):
            return all(self._eval_condition(item, context) for item in condition.all)
        if isinstance(condition, WorkflowConditionAny):
            return any(self._eval_condition(item, context) for item in condition.any)
        if isinstance(condition, WorkflowConditionNot):
            return not self._eval_condition(condition.not_, context)

        exists, current = self._resolve_path(context, condition.path)
        op = condition.op
        target = condition.value

        if op == "exists":
            return exists and current not in (None, "", [], {}, ())
        if op == "eq":
            return self._normalized_compare_value(current) == self._normalized_compare_value(target)
        if op == "neq":
            return self._normalized_compare_value(current) != self._normalized_compare_value(target)
        if op == "in":
            if not isinstance(target, (list, tuple, set)):
                return False
            return any(self._normalized_compare_value(current) == self._normalized_compare_value(item) for item in target)
        if op == "contains":
            if isinstance(current, str) and isinstance(target, str):
                return target in current
            if isinstance(current, (list, tuple, set)):
                return target in current
            return False

        left = self._normalized_compare_value(current)
        right = self._normalized_compare_value(target)
        if left is None or right is None:
            return False
        try:
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right
            if op == "lt":
                return left < right
            if op == "lte":
                return left <= right
        except TypeError:
            return False
        return False

    def _normalized_compare_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, str):
            as_number = self._parse_number(value)
            if as_number is not None:
                return as_number
            as_date = self._parse_date(value)
            if as_date is not None:
                return as_date.isoformat()
            return value
        return value

    def _parse_number(self, value: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_date(self, value: str) -> date | None:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _coerce_standard_value(self, entity: Any, field_name: str, value: Any) -> Any:
        column = inspect(entity.__class__).columns[field_name]
        python_type = getattr(column.type, "python_type", None)
        if value is None or python_type is None:
            return value
        if python_type is uuid.UUID:
            return uuid.UUID(str(value))
        if python_type is date:
            if isinstance(value, date):
                return value
            return date.fromisoformat(str(value))
        if python_type is datetime:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))
        if python_type is Decimal:
            return Decimal(str(value))
        if python_type is float:
            return float(value)
        if python_type is int:
            return int(value)
        if python_type is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                if value.lower() == "true":
                    return True
                if value.lower() == "false":
                    return False
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid boolean for {field_name}")
        return value

    def _parse_condition(self, payload: dict[str, Any]) -> WorkflowCondition:
        if "all" in payload:
            return WorkflowConditionAll(all=[self._parse_condition(item) for item in payload.get("all", [])])
        if "any" in payload:
            return WorkflowConditionAny(any=[self._parse_condition(item) for item in payload.get("any", [])])
        if "not" in payload:
            return WorkflowConditionNot.model_validate({"not": self._parse_condition(payload.get("not"))})
        return WorkflowConditionLeaf.model_validate(payload)

    def _parse_action(self, payload: dict[str, Any]) -> WorkflowAction:
        action_type = payload.get("type")
        if action_type == "SET_FIELD":
            return WorkflowActionSetField.model_validate(payload)
        if action_type == "CREATE_TASK":
            return WorkflowActionCreateTask.model_validate(payload)
        if action_type == "NOTIFY":
            return WorkflowActionNotify.model_validate(payload)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid workflow action type")

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        return value

    def _load_rule(self, session: Session, rule_id: uuid.UUID) -> CRMWorkflowRule:
        rule = session.scalar(select(CRMWorkflowRule).where(and_(CRMWorkflowRule.id == rule_id, CRMWorkflowRule.deleted_at.is_(None))))
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow rule not found")
        return rule

    def _to_rule_read(self, rule: CRMWorkflowRule) -> WorkflowRuleRead:
        return WorkflowRuleRead.model_validate(rule)

    def _require_permission(self, actor_user: ActorUser, permission: str) -> None:
        if permission not in actor_user.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")

    def _enforce_legal_entity_access(self, actor_user: ActorUser, legal_entity_id: uuid.UUID) -> None:
        if legal_entity_id in set(actor_user.allowed_legal_entity_ids):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for legal_entity_id")


class WorkflowAutomationService:
    supported_event_types = {
        "crm.lead.created",
        "crm.lead.updated",
        "crm.opportunity.stage_changed",
        "crm.opportunity.closed_won",
        "crm.opportunity.closed_lost",
        "crm.account.created",
        "crm.account.updated",
    }

    def __init__(self) -> None:
        self.workflow_service = WorkflowService()

    def enqueue_for_event(self, session: Session, envelope: dict[str, Any]) -> list[uuid.UUID]:
        settings = get_settings()
        event_type = str(envelope.get("event_type") or "")
        if event_type not in self.supported_event_types:
            return []

        event_id = str(envelope.get("event_id") or "").strip()
        if not event_id:
            return []

        payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        entity_ref = self._entity_ref_from_event(event_type, payload)
        if entity_ref is None:
            return []

        meta_payload = envelope.get("meta") if isinstance(envelope.get("meta"), dict) else {}
        depth_raw = meta_payload.get("workflow_depth", 0)
        try:
            workflow_depth = int(depth_raw)
        except (TypeError, ValueError):
            workflow_depth = 0

        if workflow_depth >= settings.workflow_max_depth:
            blocked_correlation_id = str(envelope.get("correlation_id") or "").strip() or None
            blocked_token = set_correlation_id(blocked_correlation_id)
            try:
                logger.warning(
                    "workflow_guardrail_blocked",
                    extra={
                        "reason": "MAX_DEPTH",
                        "event_type": event_type,
                        "event_id": event_id,
                        "workflow_depth": workflow_depth,
                        "max_depth": settings.workflow_max_depth,
                        "entity_type": entity_ref.type,
                        "entity_id": str(entity_ref.id),
                    },
                )
            finally:
                reset_correlation_id(blocked_token)
            observe_workflow_guardrail_block("MAX_DEPTH")
            audit.record(
                actor_user_id=str(envelope.get("actor_user_id") or "system"),
                entity_type="crm.workflow",
                entity_id=event_id,
                action="workflow.blocked",
                before=None,
                after={
                    "reason": "MAX_DEPTH",
                    "event_type": event_type,
                    "event_id": event_id,
                    "workflow_depth": workflow_depth,
                    "max_depth": settings.workflow_max_depth,
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                },
                correlation_id=blocked_correlation_id,
            )
            session.commit()
            return []

        legal_entity_id = self._optional_uuid(envelope.get("legal_entity_id"))
        correlation_id = str(envelope.get("correlation_id") or "").strip() or None
        actor_user_id = str(envelope.get("actor_user_id") or "").strip() or None

        rules = self.workflow_service.get_active_rules_for_trigger(session, event_type, legal_entity_id)
        queued_job_ids: list[uuid.UUID] = []

        for rule in rules:
            dedupe_key = f"{event_id}:{rule.id}"
            request_hash = hashlib.sha256(
                f"{event_type}:{entity_ref.type}:{entity_ref.id}:{dedupe_key}".encode("utf-8")
            ).hexdigest()
            existing = session.scalar(
                select(CRMIdempotencyKey).where(
                    and_(
                        CRMIdempotencyKey.endpoint == "crm.workflow.auto_execute",
                        CRMIdempotencyKey.key == dedupe_key,
                    )
                )
            )
            if existing is not None:
                continue

            session.add(
                CRMIdempotencyKey(
                    endpoint="crm.workflow.auto_execute",
                    key=dedupe_key,
                    request_hash=request_hash,
                    response_json=json.dumps({"status": "queued", "event_id": event_id, "rule_id": str(rule.id)}),
                )
            )

            job = CRMJob(
                job_type="WORKFLOW_EXECUTION",
                entity_type=entity_ref.type,
                status="Queued",
                requested_by_user_id=_coerce_user_uuid(actor_user_id or "system"),
                legal_entity_id=legal_entity_id,
                correlation_id=correlation_id,
                params_json=json.dumps(
                    {
                        "rule_id": str(rule.id),
                        "entity_type": entity_ref.type,
                        "entity_id": str(entity_ref.id),
                        "event_id": event_id,
                        "event_type": event_type,
                        "event_depth": workflow_depth,
                        "actor_user_id": actor_user_id,
                        "legal_entity_id": str(legal_entity_id) if legal_entity_id else None,
                    }
                ),
            )
            session.add(job)
            session.flush()
            queued_job_ids.append(job.id)

            audit.record(
                actor_user_id=actor_user_id or "system",
                entity_type="crm.workflow_rule",
                entity_id=str(rule.id),
                action="workflow.queued",
                before=None,
                after={
                    "job_id": str(job.id),
                    "event_id": event_id,
                    "event_type": event_type,
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                },
                correlation_id=correlation_id,
            )

        session.commit()
        return queued_job_ids

    def _entity_ref_from_event(self, event_type: str, payload: dict[str, Any]) -> WorkflowEntityRef | None:
        try:
            if event_type.startswith("crm.lead."):
                lead_id = payload.get("lead_id")
                return WorkflowEntityRef(type="lead", id=uuid.UUID(str(lead_id))) if lead_id else None
            if event_type.startswith("crm.account."):
                account_id = payload.get("account_id")
                return WorkflowEntityRef(type="account", id=uuid.UUID(str(account_id))) if account_id else None
            if event_type.startswith("crm.opportunity."):
                opportunity_id = payload.get("opportunity_id")
                return WorkflowEntityRef(type="opportunity", id=uuid.UUID(str(opportunity_id))) if opportunity_id else None
            return None
        except ValueError:
            return None

    def _optional_uuid(self, value: Any) -> uuid.UUID | None:
        if value in (None, ""):
            return None
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None


class WorkflowExecutionJobRunner:
    def __init__(self) -> None:
        self.workflow_service = WorkflowService()

    def run_workflow_execution_job(self, session: Session, job_id: uuid.UUID) -> CRMJob:
        settings = get_settings()
        job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.job_type != "WORKFLOW_EXECUTION":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid job type")
        if job.status == "Succeeded":
            return job

        params = json.loads(job.params_json or "{}")
        rule_id = uuid.UUID(str(params["rule_id"]))
        entity_ref = WorkflowEntityRef(type=str(params["entity_type"]), id=uuid.UUID(str(params["entity_id"])))
        event_id = str(params.get("event_id") or "")
        event_depth = self._parse_depth(params.get("event_depth", 0))
        actor_user_id = str(params.get("actor_user_id") or "").strip() or None
        legal_entity_id = uuid.UUID(str(params["legal_entity_id"])) if params.get("legal_entity_id") else None

        correlation_id = str(job.correlation_id or "").strip() or None
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        final_status = "Failed"

        try:
            dedupe_key = f"{event_id}:{rule_id}"
            dedupe = session.scalar(
                select(CRMIdempotencyKey).where(
                    and_(
                        CRMIdempotencyKey.endpoint == "crm.workflow.auto_execute",
                        CRMIdempotencyKey.key == dedupe_key,
                    )
                )
            )

            if dedupe is not None:
                dedupe_payload = json.loads(dedupe.response_json or "{}")
                if dedupe_payload.get("status") in {"succeeded", "deduped"}:
                    job.status = "Succeeded"
                    job.started_at = job.started_at or utcnow()
                    job.finished_at = utcnow()
                    job.result_json = json.dumps({"status": "deduped", "event_id": event_id, "rule_id": str(rule_id)})
                    session.add(job)
                    session.commit()
                    final_status = "Succeeded"
                    return job

            if dedupe is None:
                request_hash = hashlib.sha256(f"{event_id}:{rule_id}:{entity_ref.type}:{entity_ref.id}".encode("utf-8")).hexdigest()
                session.add(
                    CRMIdempotencyKey(
                        endpoint="crm.workflow.auto_execute",
                        key=dedupe_key,
                        request_hash=request_hash,
                        response_json=json.dumps({"status": "running", "event_id": event_id, "rule_id": str(rule_id)}),
                    )
                )

            job.status = "Running"
            job.started_at = utcnow()
            job.finished_at = None
            session.add(job)
            session.commit()

            runtime_actor = ActorUser(
                user_id=actor_user_id or "system",
                allowed_legal_entity_ids=[legal_entity_id] if legal_entity_id else [],
                current_legal_entity_id=legal_entity_id,
                permissions={
                    "crm.workflows.execute",
                    "crm.workflows.manage",
                    "crm.accounts.read_all",
                    "crm.contacts.read_all",
                    "crm.leads.read_all",
                    "crm.opportunities.read_all",
                },
                correlation_id=correlation_id,
            )

            rule = self.workflow_service._load_rule(session, rule_id)
            throttled = self._try_rule_cooldown(
                session,
                job,
                rule,
                entity_ref,
                runtime_actor,
                event_id,
            )
            if throttled is not None:
                final_status = "Succeeded"
                return throttled

            depth_token = set_workflow_depth(event_depth + 1)
            try:
                result = self.workflow_service.execute_rule(
                    session,
                    runtime_actor,
                    rule_id,
                    entity_ref,
                    dry_run=False,
                    max_actions=settings.workflow_max_actions,
                    max_set_field=settings.workflow_max_set_field,
                )
            finally:
                reset_workflow_depth(depth_token)

            actions_executed_count = len(result.planned_actions)
            result_payload = {
                "status": "succeeded",
                "matched": result.matched,
                "actions_executed_count": actions_executed_count,
                "mutation_summary": result.planned_mutations,
                "event_id": event_id,
                "rule_id": str(rule_id),
            }

            job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
            if job is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
            job.status = "Succeeded"
            job.finished_at = utcnow()
            job.result_json = json.dumps(result_payload)
            session.add(job)

            dedupe = session.scalar(
                select(CRMIdempotencyKey).where(
                    and_(
                        CRMIdempotencyKey.endpoint == "crm.workflow.auto_execute",
                        CRMIdempotencyKey.key == dedupe_key,
                    )
                )
            )
            if dedupe is not None:
                dedupe.response_json = json.dumps(result_payload)
                session.add(dedupe)

            session.commit()
            final_status = "Succeeded"
            return job
        except WorkflowLimitExceededError as exc:
            session.rollback()
            job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
            if job is None:
                raise

            logger.warning(
                "workflow_guardrail_limit_exceeded",
                extra={
                    "reason": exc.summary.get("reason"),
                    "job_id": str(job_id),
                    "rule_id": str(rule_id),
                    "event_id": event_id,
                },
            )
            observe_workflow_guardrail_block("LIMIT_EXCEEDED")
            audit.record(
                actor_user_id=actor_user_id or "system",
                entity_type="crm.workflow_rule",
                entity_id=str(rule_id),
                action="workflow.blocked",
                before=None,
                after={
                    "reason": "LIMIT_EXCEEDED",
                    "job_id": str(job_id),
                    "event_id": event_id,
                    "limit_reason": str(exc.summary.get("reason") or "WORKFLOW_LIMIT_EXCEEDED"),
                    **exc.summary,
                },
                correlation_id=correlation_id,
            )

            job.status = "Failed"
            job.finished_at = utcnow()
            job.result_json = json.dumps(
                {
                    "status": "failed",
                    "code": "WORKFLOW_LIMIT_EXCEEDED",
                    "event_id": event_id,
                    "rule_id": str(rule_id),
                    **exc.summary,
                }
            )
            session.add(job)
            session.commit()
            final_status = "Failed"
            return job
        except Exception as exc:
            session.rollback()
            job = session.scalar(select(CRMJob).where(CRMJob.id == job_id))
            if job is None:
                raise
            job.status = "Failed"
            job.finished_at = utcnow()
            job.result_json = json.dumps(
                {
                    "status": "failed",
                    "error": str(exc)[:2000],
                    "event_id": event_id,
                    "rule_id": str(rule_id),
                }
            )
            session.add(job)
            session.commit()
            final_status = "Failed"
            return job
        finally:
            observe_job(job_type="WORKFLOW_EXECUTION", status=final_status, duration=time.perf_counter() - started)
            reset_correlation_id(token)

    def _parse_depth(self, value: Any) -> int:
        try:
            depth = int(value)
        except (TypeError, ValueError):
            return 0
        return depth if depth >= 0 else 0

    def _try_rule_cooldown(
        self,
        session: Session,
        job: CRMJob,
        rule: CRMWorkflowRule,
        entity_ref: WorkflowEntityRef,
        actor_user: ActorUser,
        event_id: str,
    ) -> CRMJob | None:
        if not rule.cooldown_seconds:
            return None

        cooldown_seconds = int(rule.cooldown_seconds)
        time_bucket = int(utcnow().timestamp() // cooldown_seconds)
        cooldown_key = f"{rule.id}:{entity_ref.type}:{entity_ref.id}:{time_bucket}"

        existing = session.scalar(
            select(CRMIdempotencyKey).where(
                and_(
                    CRMIdempotencyKey.endpoint == "crm.workflow.cooldown",
                    CRMIdempotencyKey.key == cooldown_key,
                )
            )
        )
        if existing is not None:
            logger.warning(
                "workflow_guardrail_blocked",
                extra={
                    "reason": "COOLDOWN",
                    "rule_id": str(rule.id),
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                    "cooldown_seconds": cooldown_seconds,
                },
            )
            observe_workflow_guardrail_block("COOLDOWN")
            audit.record(
                actor_user_id=actor_user.user_id,
                entity_type="crm.workflow_rule",
                entity_id=str(rule.id),
                action="workflow.blocked",
                before=None,
                after={
                    "reason": "COOLDOWN",
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                    "cooldown_seconds": cooldown_seconds,
                    "time_bucket": time_bucket,
                },
                correlation_id=actor_user.correlation_id,
            )

            job.status = "Succeeded"
            job.started_at = job.started_at or utcnow()
            job.finished_at = utcnow()
            job.result_json = json.dumps(
                {
                    "status": "succeeded",
                    "throttled": True,
                    "bucket": cooldown_key,
                    "reason": "COOLDOWN",
                    "rule_id": str(rule.id),
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                    "event_id": event_id,
                }
            )
            session.add(job)
            session.commit()
            return job

        request_hash = hashlib.sha256(cooldown_key.encode("utf-8")).hexdigest()
        session.add(
            CRMIdempotencyKey(
                endpoint="crm.workflow.cooldown",
                key=cooldown_key,
                request_hash=request_hash,
                response_json=json.dumps(
                    {
                        "status": "reserved",
                        "rule_id": str(rule.id),
                        "entity_type": entity_ref.type,
                        "entity_id": str(entity_ref.id),
                        "time_bucket": time_bucket,
                    }
                ),
            )
        )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            job.status = "Succeeded"
            job.started_at = job.started_at or utcnow()
            job.finished_at = utcnow()
            job.result_json = json.dumps(
                {
                    "status": "succeeded",
                    "throttled": True,
                    "bucket": cooldown_key,
                    "reason": "COOLDOWN",
                    "rule_id": str(rule.id),
                    "entity_type": entity_ref.type,
                    "entity_id": str(entity_ref.id),
                    "event_id": event_id,
                }
            )
            session.add(job)
            session.commit()
            return job

        return None


VALID_ENTITY_TYPES = {"account", "contact", "lead", "opportunity"}


def _normalize_audit_entity_type(entity_type: str | None) -> str | None:
    if entity_type is None:
        return None
    value = entity_type.strip().lower()
    if value.startswith("crm."):
        value = value.split(".", 1)[1]
    return value


def _is_read_all(actor_user: ActorUser) -> bool:
    return any(
        permission in actor_user.permissions
        for permission in [
            "crm.accounts.read_all",
            "crm.contacts.read_all",
            "crm.leads.read_all",
            "crm.opportunities.read_all",
        ]
    )


def ensure_entity_visible(
    session: Session,
    actor_user: ActorUser,
    entity_type: str,
    entity_id: uuid.UUID,
) -> dict[str, Any]:
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid entity_type")

    allowed = set(actor_user.allowed_legal_entity_ids)
    read_all = _is_read_all(actor_user)

    if entity_type == "account":
        account = session.scalar(
            select(CRMAccount)
            .where(and_(CRMAccount.id == entity_id, CRMAccount.deleted_at.is_(None)))
            .options(selectinload(CRMAccount.legal_entities))
        )
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        legal_entity_ids = [link.legal_entity_id for link in account.legal_entities]
        if not read_all and not any(legal_entity_id in allowed for legal_entity_id in legal_entity_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        legal_entity_id = legal_entity_ids[0] if legal_entity_ids else None
        return {"entity_type": entity_type, "entity_id": entity_id, "legal_entity_id": legal_entity_id}

    if entity_type == "contact":
        contact = session.scalar(
            select(CRMContact)
            .where(and_(CRMContact.id == entity_id, CRMContact.deleted_at.is_(None)))
            .options(selectinload(CRMContact.account).selectinload(CRMAccount.legal_entities))
        )
        if contact is None or contact.account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        legal_entity_ids = [link.legal_entity_id for link in contact.account.legal_entities]
        if not read_all and not any(legal_entity_id in allowed for legal_entity_id in legal_entity_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        legal_entity_id = legal_entity_ids[0] if legal_entity_ids else None
        return {"entity_type": entity_type, "entity_id": entity_id, "legal_entity_id": legal_entity_id}

    if entity_type == "lead":
        lead = session.scalar(select(CRMLead).where(and_(CRMLead.id == entity_id, CRMLead.deleted_at.is_(None))))
        if lead is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        if not read_all and lead.selling_legal_entity_id not in allowed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        return {"entity_type": entity_type, "entity_id": entity_id, "legal_entity_id": lead.selling_legal_entity_id}

    opportunity = session.scalar(
        select(CRMOpportunity)
        .where(and_(CRMOpportunity.id == entity_id, CRMOpportunity.deleted_at.is_(None)))
        .options(selectinload(CRMOpportunity.account).selectinload(CRMAccount.legal_entities))
    )
    if opportunity is None or opportunity.account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    account_legal_entities = [link.legal_entity_id for link in opportunity.account.legal_entities]
    if not read_all:
        if opportunity.selling_legal_entity_id not in allowed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
        if not any(legal_entity_id in allowed for legal_entity_id in account_legal_entities):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return {"entity_type": entity_type, "entity_id": entity_id, "legal_entity_id": opportunity.selling_legal_entity_id}


class AuditService:
    def list_audit_logs(
        self,
        session: Session,
        actor_user: ActorUser,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> list[AuditRead]:
        entries = self._sorted_entries()

        entity_type_filter = _normalize_audit_entity_type(filters.get("entity_type"))
        entity_id_filter = str(filters.get("entity_id")) if filters.get("entity_id") else None
        actor_user_id_filter = filters.get("actor_user_id")
        action_filter = filters.get("action")
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        correlation_id_filter = filters.get("correlation_id")

        filtered: list[dict[str, Any]] = []
        for entry in entries:
            normalized_entry_type = _normalize_audit_entity_type(str(entry.get("entity_type", "")))
            if entity_type_filter and normalized_entry_type != entity_type_filter:
                continue
            if entity_id_filter and str(entry.get("entity_id")) != entity_id_filter:
                continue
            if actor_user_id_filter and str(entry.get("actor_user_id")) != str(actor_user_id_filter):
                continue
            if action_filter and str(entry.get("action")) != str(action_filter):
                continue
            if correlation_id_filter and str(entry.get("correlation_id")) != str(correlation_id_filter):
                continue

            occurred_at = self._parse_occurred_at(entry)
            if date_from and occurred_at < date_from:
                continue
            if date_to and occurred_at > date_to:
                continue

            if "crm.audit.read_all" not in actor_user.permissions:
                if normalized_entry_type not in VALID_ENTITY_TYPES:
                    continue
                try:
                    ensure_entity_visible(session, actor_user, normalized_entry_type, uuid.UUID(str(entry["entity_id"])))
                except (HTTPException, ValueError):
                    continue

            filtered.append(entry)

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        page = filtered[offset : offset + limit]
        return [self._to_read_model(entry) for entry in page]

    def list_entity_audit_logs(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        cursor: str | None,
        limit: int,
    ) -> list[AuditRead]:
        if "crm.audit.read_all" not in actor_user.permissions:
            ensure_entity_visible(session, actor_user, entity_type, entity_id)
        return self.list_audit_logs(
            session,
            actor_user,
            filters={"entity_type": entity_type, "entity_id": str(entity_id)},
            cursor=cursor,
            limit=limit,
        )

    def _sorted_entries(self) -> list[dict[str, Any]]:
        return sorted(audit.audit_entries, key=self._parse_occurred_at, reverse=True)

    def _parse_occurred_at(self, entry: dict[str, Any]) -> datetime:
        occurred_at_raw = entry.get("occurred_at")
        if isinstance(occurred_at_raw, datetime):
            return occurred_at_raw
        if isinstance(occurred_at_raw, str):
            try:
                parsed = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                pass
        return datetime.fromtimestamp(0, tz=timezone.utc)

    def _to_read_model(self, entry: dict[str, Any]) -> AuditRead:
        return AuditRead.model_validate(
            {
                "id": str(entry.get("id") or uuid.uuid4()),
                "entity_type": str(entry.get("entity_type", "")),
                "entity_id": str(entry.get("entity_id", "")),
                "action": str(entry.get("action", "")),
                "actor_user_id": str(entry.get("actor_user_id", "")),
                "occurred_at": self._parse_occurred_at(entry),
                "correlation_id": entry.get("correlation_id"),
                "before": entry.get("before"),
                "after": entry.get("after"),
            }
        )


class ActivityService:
    valid_types = {"Call", "Email", "Meeting", "Task", "Other"}
    valid_statuses = {"Open", "Completed"}

    def list_activities(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> list[ActivityRead]:
        ensure_entity_visible(session, actor_user, entity_type, entity_id)
        stmt: Select[tuple[CRMActivity]] = select(CRMActivity).where(
            and_(
                CRMActivity.entity_type == entity_type,
                CRMActivity.entity_id == entity_id,
                CRMActivity.deleted_at.is_(None),
            )
        )
        if filters.get("activity_type"):
            stmt = stmt.where(CRMActivity.activity_type == filters["activity_type"])
        if filters.get("status"):
            stmt = stmt.where(CRMActivity.status == filters["status"])
        if filters.get("assigned_to_user_id"):
            stmt = stmt.where(CRMActivity.assigned_to_user_id == filters["assigned_to_user_id"])
        if filters.get("due_from"):
            stmt = stmt.where(CRMActivity.due_at >= filters["due_from"])
        if filters.get("due_to"):
            stmt = stmt.where(CRMActivity.due_at <= filters["due_to"])

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        rows = session.scalars(stmt.order_by(CRMActivity.created_at.desc()).offset(offset).limit(limit)).all()
        return [ActivityRead.model_validate(row) for row in rows]

    def create_activity(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        dto: ActivityCreate,
    ) -> ActivityRead:
        scope_context = ensure_entity_visible(session, actor_user, entity_type, entity_id)
        if dto.activity_type not in self.valid_types:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid activity_type")

        payload = dto.model_dump()
        if dto.activity_type == "Task":
            if dto.assigned_to_user_id is None or dto.due_at is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Task requires assigned_to_user_id and due_at",
                )
            if dto.status not in self.valid_statuses:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status")
            if dto.status == "Completed" and dto.completed_at is None:
                payload["completed_at"] = utcnow()
        else:
            payload["assigned_to_user_id"] = None
            payload["due_at"] = None
            payload["status"] = "Open"
            payload["completed_at"] = None

        activity = CRMActivity(
            entity_type=entity_type,
            entity_id=entity_id,
            activity_type=dto.activity_type,
            subject=payload.get("subject"),
            body=payload.get("body"),
            owner_user_id=dto.owner_user_id,
            assigned_to_user_id=payload.get("assigned_to_user_id"),
            due_at=payload.get("due_at"),
            status=payload.get("status", "Open"),
            completed_at=payload.get("completed_at"),
        )
        session.add(activity)
        session.flush()

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.activity",
            entity_id=str(activity.id),
            action="create",
            before=None,
            after=ActivityRead.model_validate(activity).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.activity.created",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"activity_id": str(activity.id), "entity_type": entity_type, "entity_id": str(entity_id)},
            }
        )
        if activity.activity_type == "Task" and activity.assigned_to_user_id is not None:
            self._enqueue_task_notification(session, activity, entity_type, entity_id)

        session.commit()
        return ActivityRead.model_validate(activity)

    def update_activity(
        self,
        session: Session,
        actor_user: ActorUser,
        activity_id: uuid.UUID,
        dto: ActivityUpdate,
    ) -> ActivityRead:
        activity = session.scalar(
            select(CRMActivity).where(and_(CRMActivity.id == activity_id, CRMActivity.deleted_at.is_(None)))
        )
        if activity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="activity not found")
        scope_context = ensure_entity_visible(session, actor_user, activity.entity_type, activity.entity_id)

        payload = dto.model_dump(exclude_unset=True)
        payload.pop("row_version", None)
        if not payload:
            return ActivityRead.model_validate(activity)

        if activity.activity_type != "Task":
            for field in ["assigned_to_user_id", "due_at", "completed_at"]:
                if field in payload:
                    payload.pop(field)
            if "status" in payload:
                payload["status"] = "Open"
        else:
            if payload.get("status") == "Completed" and payload.get("completed_at") is None:
                payload["completed_at"] = utcnow()
            if payload.get("status") == "Completed" and payload.get("completed_at") is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="completed_at required")

        payload["updated_at"] = utcnow()
        payload["row_version"] = CRMActivity.row_version + 1
        old_assignee = activity.assigned_to_user_id

        result = session.execute(
            update(CRMActivity)
            .where(
                and_(
                    CRMActivity.id == activity.id,
                    CRMActivity.row_version == dto.row_version,
                    CRMActivity.deleted_at.is_(None),
                )
            )
            .values(**payload)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated = session.scalar(select(CRMActivity).where(CRMActivity.id == activity.id))
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="activity not found")

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.activity",
            entity_id=str(updated.id),
            action="update",
            before=ActivityRead.model_validate(activity).model_dump(mode="json"),
            after=ActivityRead.model_validate(updated).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.activity.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"activity_id": str(updated.id)},
            }
        )

        if updated.activity_type == "Task" and updated.assigned_to_user_id is not None and updated.assigned_to_user_id != old_assignee:
            self._enqueue_task_notification(session, updated, updated.entity_type, updated.entity_id)

        session.commit()
        return ActivityRead.model_validate(updated)

    def complete_activity(
        self,
        session: Session,
        actor_user: ActorUser,
        activity_id: uuid.UUID,
        dto: CompleteActivityRequest,
    ) -> ActivityRead:
        activity = session.scalar(
            select(CRMActivity).where(and_(CRMActivity.id == activity_id, CRMActivity.deleted_at.is_(None)))
        )
        if activity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="activity not found")
        scope_context = ensure_entity_visible(session, actor_user, activity.entity_type, activity.entity_id)
        if activity.activity_type != "Task":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="only Task can be completed")

        result = session.execute(
            update(CRMActivity)
            .where(and_(CRMActivity.id == activity.id, CRMActivity.row_version == dto.row_version))
            .values(
                status="Completed",
                completed_at=utcnow(),
                updated_at=utcnow(),
                row_version=CRMActivity.row_version + 1,
            )
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated = session.scalar(select(CRMActivity).where(CRMActivity.id == activity.id))
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="activity not found")
        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.activity",
            entity_id=str(updated.id),
            action="complete",
            before=ActivityRead.model_validate(activity).model_dump(mode="json"),
            after=ActivityRead.model_validate(updated).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.activity.completed",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"activity_id": str(updated.id)},
            }
        )
        session.commit()
        return ActivityRead.model_validate(updated)

    def _enqueue_task_notification(
        self,
        session: Session,
        activity: CRMActivity,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> None:
        if activity.assigned_to_user_id is None:
            return
        session.add(
            CRMNotificationIntent(
                intent_type="TASK_ASSIGNED",
                recipient_user_id=activity.assigned_to_user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                activity_id=activity.id,
                payload_json=json.dumps(
                    {
                        "subject": activity.subject,
                        "due_at": activity.due_at.isoformat() if activity.due_at else None,
                    }
                ),
            )
        )


class NoteService:
    def list_notes(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        cursor: str | None,
        limit: int,
    ) -> list[NoteRead]:
        ensure_entity_visible(session, actor_user, entity_type, entity_id)
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        rows = session.scalars(
            select(CRMNote)
            .where(
                and_(
                    CRMNote.entity_type == entity_type,
                    CRMNote.entity_id == entity_id,
                    CRMNote.deleted_at.is_(None),
                )
            )
            .order_by(CRMNote.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [NoteRead.model_validate(row) for row in rows]

    def create_note(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        dto: NoteCreate,
    ) -> NoteRead:
        scope_context = ensure_entity_visible(session, actor_user, entity_type, entity_id)
        if not dto.content.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="content is required")
        if dto.content_format not in {"markdown", "plaintext"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid content_format")

        note = CRMNote(
            entity_type=entity_type,
            entity_id=entity_id,
            content=dto.content,
            content_format=dto.content_format,
            owner_user_id=dto.owner_user_id,
        )
        session.add(note)
        session.flush()

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.note",
            entity_id=str(note.id),
            action="create",
            before=None,
            after=NoteRead.model_validate(note).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.note.created",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"note_id": str(note.id), "entity_type": entity_type, "entity_id": str(entity_id)},
            }
        )
        session.commit()
        return NoteRead.model_validate(note)

    def update_note(
        self,
        session: Session,
        actor_user: ActorUser,
        note_id: uuid.UUID,
        dto: NoteUpdate,
    ) -> NoteRead:
        note = session.scalar(select(CRMNote).where(and_(CRMNote.id == note_id, CRMNote.deleted_at.is_(None))))
        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        scope_context = ensure_entity_visible(session, actor_user, note.entity_type, note.entity_id)

        payload = dto.model_dump(exclude_unset=True)
        payload.pop("row_version", None)
        if "content" in payload and payload["content"] is not None and not str(payload["content"]).strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="content is required")
        if payload.get("content_format") is not None and payload["content_format"] not in {"markdown", "plaintext"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid content_format")

        payload["updated_at"] = utcnow()
        payload["row_version"] = CRMNote.row_version + 1

        result = session.execute(
            update(CRMNote)
            .where(and_(CRMNote.id == note.id, CRMNote.row_version == dto.row_version, CRMNote.deleted_at.is_(None)))
            .values(**payload)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="row_version conflict")

        updated = session.scalar(select(CRMNote).where(CRMNote.id == note.id))
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.note",
            entity_id=str(updated.id),
            action="update",
            before=NoteRead.model_validate(note).model_dump(mode="json"),
            after=NoteRead.model_validate(updated).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.note.updated",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"note_id": str(updated.id)},
            }
        )
        session.commit()
        return NoteRead.model_validate(updated)


class AttachmentService:
    def list_attachments(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AttachmentLinkRead]:
        ensure_entity_visible(session, actor_user, entity_type, entity_id)
        rows = session.scalars(
            select(CRMAttachmentLink)
            .where(and_(CRMAttachmentLink.entity_type == entity_type, CRMAttachmentLink.entity_id == entity_id))
            .order_by(CRMAttachmentLink.created_at.desc())
        ).all()
        return [AttachmentLinkRead.model_validate(row) for row in rows]

    def create_attachment_link(
        self,
        session: Session,
        actor_user: ActorUser,
        entity_type: str,
        entity_id: uuid.UUID,
        dto: AttachmentLinkCreate,
    ) -> AttachmentLinkRead:
        scope_context = ensure_entity_visible(session, actor_user, entity_type, entity_id)
        link = CRMAttachmentLink(
            entity_type=entity_type,
            entity_id=entity_id,
            file_id=dto.file_id,
            created_by_user_id=uuid.UUID(actor_user.user_id) if _is_uuid(actor_user.user_id) else None,
        )
        session.add(link)
        session.flush()

        audit.record(
            actor_user_id=actor_user.user_id,
            entity_type="crm.attachment_link",
            entity_id=str(link.id),
            action="create",
            before=None,
            after=AttachmentLinkRead.model_validate(link).model_dump(mode="json"),
            correlation_id=actor_user.correlation_id,
        )
        events.publish(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "crm.attachment_link.created",
                "occurred_at": utcnow().isoformat(),
                "actor_user_id": actor_user.user_id,
                "legal_entity_id": (
                    str(scope_context["legal_entity_id"]) if scope_context["legal_entity_id"] is not None else None
                ),
                "version": 1,
                "payload": {"attachment_link_id": str(link.id), "file_id": str(link.file_id)},
            }
        )
        session.commit()
        return AttachmentLinkRead.model_validate(link)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
