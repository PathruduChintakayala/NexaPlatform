from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app import files_stub
from app.context import get_correlation_id
from app.core.auth import AuthUser, get_current_user as get_auth_user
from app.core.database import get_db
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
    OpportunityChangeStageRequest,
    OpportunityCloseLostRequest,
    OpportunityCloseWonRequest,
    OpportunityCreate,
    OpportunityRead,
    OpportunityRevenueRead,
    OpportunityReopenRequest,
    OpportunityUpdate,
    PipelineCreate,
    PipelineRead,
    PipelineStageCreate,
    PipelineStageRead,
    RevenueHandoffRequest,
    RevenueHandoffRetryResponse,
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    AuditRead,
    AttachmentLinkCreate,
    AttachmentLinkRead,
    CompleteActivityRequest,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    WorkflowDryRunRequest,
    WorkflowDryRunResponse,
    WorkflowEntityRef,
    WorkflowRuleCreate,
    WorkflowRuleRead,
    WorkflowRuleUpdate,
)
from app.crm.search import search_entities
from app.crm.service import (
    AccountService,
    ActivityService,
    AuditService,
    ActorUser,
    AttachmentService,
    ContactService,
    CustomFieldService,
    LeadService,
    NoteService,
    OpportunityService,
    PipelineService,
    RevenueHandoffService,
    RevenueHandoffJobRunner,
    ImportExportService,
    WorkflowService,
)

router = APIRouter(prefix="/api/crm/accounts", tags=["crm.accounts"])
contacts_router = APIRouter(prefix="/api/crm", tags=["crm.contacts"])
leads_router = APIRouter(prefix="/api/crm", tags=["crm.leads"])
pipelines_router = APIRouter(prefix="/api/crm", tags=["crm.pipelines"])
opportunities_router = APIRouter(prefix="/api/crm", tags=["crm.opportunities"])
activities_router = APIRouter(prefix="/api/crm", tags=["crm.activities"])
notes_router = APIRouter(prefix="/api/crm", tags=["crm.notes"])
attachments_router = APIRouter(prefix="/api/crm", tags=["crm.attachments"])
audit_router = APIRouter(prefix="/api/crm", tags=["crm.audit"])
search_router = APIRouter(prefix="/api/crm", tags=["crm.search"])
import_export_router = APIRouter(prefix="/api/crm", tags=["crm.import_export"])
jobs_router = APIRouter(prefix="/api/crm", tags=["crm.jobs"])
custom_fields_router = APIRouter(prefix="/api/crm", tags=["crm.custom_fields"])
workflows_router = APIRouter(prefix="/api/crm", tags=["crm.workflows"])
service = AccountService()
contact_service = ContactService()
lead_service = LeadService()
pipeline_service = PipelineService()
opportunity_service = OpportunityService()
revenue_handoff_service = RevenueHandoffService()
revenue_handoff_job_runner = RevenueHandoffJobRunner()
activity_service = ActivityService()
note_service = NoteService()
attachment_service = AttachmentService()
audit_service = AuditService()
import_export_service = ImportExportService()
custom_field_service = CustomFieldService()
workflow_service = WorkflowService()


@dataclass
class ErrorEnvelope:
    code: str
    message: str
    details: Any
    correlation_id: str | None


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    correlation_id = get_correlation_id() or getattr(getattr(request.state, "context", None), "request_id", None)
    payload = ErrorEnvelope(
        code=code,
        message=message,
        details=details,
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=status_code, content=payload.__dict__)


def _parse_uuid_list(raw: str | None) -> list[uuid.UUID]:
    if not raw:
        return []
    values = [item.strip() for item in raw.split(",") if item.strip()]
    parsed: list[uuid.UUID] = []
    for value in values:
        parsed.append(uuid.UUID(value))
    return parsed


def get_current_user(request: Request, auth_user: AuthUser = Depends(get_auth_user)) -> ActorUser:
    correlation_id = get_correlation_id() or getattr(getattr(request.state, "context", None), "request_id", None)
    legal_entity_header = request.headers.get("x-allowed-legal-entities")
    region_header = request.headers.get("x-allowed-regions")
    current_legal_entity_raw = request.headers.get("x-current-legal-entity")

    if current_legal_entity_raw:
        current_legal_entity_id = uuid.UUID(current_legal_entity_raw)
    else:
        context_legal_entity = getattr(getattr(request.state, "context", None), "legal_entity", None)
        current_legal_entity_id = None
        if context_legal_entity and context_legal_entity != "default":
            try:
                current_legal_entity_id = uuid.UUID(context_legal_entity)
            except ValueError:
                current_legal_entity_id = None

    allowed_legal_entities = _parse_uuid_list(legal_entity_header)
    if not allowed_legal_entities and current_legal_entity_id is not None:
        allowed_legal_entities = [current_legal_entity_id]

    allowed_regions = [item.strip() for item in (region_header or "").split(",") if item.strip()]
    if not allowed_regions:
        current_region = getattr(getattr(request.state, "context", None), "region", None)
        if isinstance(current_region, str) and current_region and current_region.lower() != "global":
            allowed_regions = [current_region]

    normalized_roles = {str(role).lower() for role in auth_user.roles}
    is_super_admin = "admin" in normalized_roles or "system.admin" in normalized_roles

    return ActorUser(
        user_id=auth_user.sub,
        allowed_legal_entity_ids=allowed_legal_entities,
        current_legal_entity_id=current_legal_entity_id,
        permissions=set(auth_user.roles),
        allowed_region_codes=allowed_regions,
        is_super_admin=is_super_admin,
        correlation_id=correlation_id,
    )


def require_permission(user: ActorUser, permission: str) -> None:
    if permission not in user.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")


def require_any_permission(user: ActorUser, permissions: list[str]) -> None:
    if not any(permission in user.permissions for permission in permissions):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {' or '.join(permissions)}")


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    request: Request,
    dto: AccountCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AccountRead | JSONResponse:
    try:
        require_permission(user, "crm.accounts.write")
        return service.create_account(
            db,
            actor_user_id=user.user_id,
            dto=dto,
            legal_entity_ids=dto.legal_entity_ids,
            current_legal_entity_id=user.current_legal_entity_id,
            correlation_id=user.correlation_id,
            idempotency_key=idempotency_key,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_account_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@router.get("", response_model=list[AccountRead])
def list_accounts(
    request: Request,
    name: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    owner_user_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[AccountRead] | JSONResponse:
    try:
        require_permission(user, "crm.accounts.read")
        return service.list_accounts(
            db,
            user,
            filters={"name": name, "status": status_filter, "owner_user_id": owner_user_id},
            cursor=cursor,
            limit=limit,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_account_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@router.get("/{account_id}", response_model=AccountRead)
def get_account(
    request: Request,
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> AccountRead | JSONResponse:
    try:
        require_permission(user, "crm.accounts.read")
        return service.get_account(db, user, account_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_account_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@router.patch("/{account_id}", response_model=AccountRead)
def patch_account(
    request: Request,
    account_id: uuid.UUID,
    dto: AccountUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> AccountRead | JSONResponse:
    try:
        require_permission(user, "crm.accounts.write")
        return service.update_account(db, user, account_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_account_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@router.delete("/{account_id}", status_code=status.HTTP_200_OK, response_model=None)
def delete_account(
    request: Request,
    account_id: uuid.UUID,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> Any:
    try:
        require_permission(user, "crm.accounts.delete")
        if force:
            require_permission(user, "crm.accounts.delete_force")
        service.soft_delete_account(db, user, account_id, force=force)
        return {"status": "deleted"}
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_account_delete_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@contacts_router.get("/accounts/{account_id}/contacts", response_model=list[ContactRead])
def list_contacts(
    request: Request,
    account_id: uuid.UUID,
    name: str | None = Query(default=None),
    email: str | None = Query(default=None),
    is_primary: bool | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[ContactRead] | JSONResponse:
    try:
        require_permission(user, "crm.contacts.read")
        if include_deleted:
            require_permission(user, "crm.contacts.read_deleted")
        return contact_service.list_contacts_for_account(
            db,
            user,
            account_id,
            filters={
                "name": name,
                "email": email,
                "is_primary": is_primary,
                "owner_user_id": owner_user_id,
            },
            cursor=cursor,
            limit=limit,
            include_deleted=include_deleted,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_contact_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@contacts_router.post("/accounts/{account_id}/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(
    request: Request,
    account_id: uuid.UUID,
    dto: ContactCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ContactRead | JSONResponse:
    try:
        require_permission(user, "crm.contacts.create")
        if dto.account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="account_id in path and body must match",
            )
        return contact_service.create_contact(db, user, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_contact_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@contacts_router.get("/contacts/{contact_id}", response_model=ContactRead)
def get_contact(
    request: Request,
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ContactRead | JSONResponse:
    try:
        require_permission(user, "crm.contacts.read")
        return contact_service.get_contact(db, user, contact_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_contact_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@contacts_router.patch("/contacts/{contact_id}", response_model=ContactRead)
def patch_contact(
    request: Request,
    contact_id: uuid.UUID,
    dto: ContactUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ContactRead | JSONResponse:
    try:
        require_permission(user, "crm.contacts.update")
        return contact_service.update_contact(db, user, contact_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_contact_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@contacts_router.delete("/contacts/{contact_id}", response_model=None, status_code=status.HTTP_200_OK)
def delete_contact(
    request: Request,
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> Any:
    try:
        require_permission(user, "crm.contacts.delete")
        contact_service.soft_delete_contact(db, user, contact_id)
        return {"status": "deleted"}
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_contact_delete_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.get("/leads", response_model=list[LeadRead])
def list_leads(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[LeadRead] | JSONResponse:
    try:
        require_permission(user, "crm.leads.read")
        return lead_service.list_leads(
            db,
            user,
            filters={
                "status": status_filter,
                "source": source,
                "owner_user_id": owner_user_id,
                "created_from": created_from,
                "created_to": created_to,
                "q": q,
            },
            cursor=cursor,
            limit=limit,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.post("/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead(
    request: Request,
    dto: LeadCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> LeadRead | JSONResponse:
    try:
        require_permission(user, "crm.leads.create")
        return lead_service.create_lead(db, user, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(
    request: Request,
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> LeadRead | JSONResponse:
    try:
        require_permission(user, "crm.leads.read")
        return lead_service.get_lead(db, user, lead_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.patch("/leads/{lead_id}", response_model=LeadRead)
def patch_lead(
    request: Request,
    lead_id: uuid.UUID,
    dto: LeadUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> LeadRead | JSONResponse:
    try:
        require_permission(user, "crm.leads.update")
        return lead_service.update_lead(db, user, lead_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.post("/leads/{lead_id}/disqualify", response_model=LeadRead)
def disqualify_lead(
    request: Request,
    lead_id: uuid.UUID,
    dto: LeadDisqualifyRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> LeadRead | JSONResponse:
    try:
        require_permission(user, "crm.leads.disqualify")
        return lead_service.disqualify_lead(db, user, lead_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_disqualify_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@leads_router.post("/leads/{lead_id}/convert", response_model=LeadRead)
def convert_lead(
    request: Request,
    lead_id: uuid.UUID,
    dto: LeadConvertRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> LeadRead | JSONResponse:
    try:
        require_permission(user, "crm.leads.convert")
        return lead_service.convert_lead(db, user, lead_id, dto, idempotency_key)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_lead_convert_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@pipelines_router.post("/pipelines", response_model=PipelineRead, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    request: Request,
    dto: PipelineCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> PipelineRead | JSONResponse:
    try:
        require_permission(user, "crm.pipelines.manage")
        return pipeline_service.create_pipeline(db, user, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_pipeline_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@pipelines_router.post("/pipelines/{pipeline_id}/stages", response_model=PipelineStageRead, status_code=status.HTTP_201_CREATED)
def add_pipeline_stage(
    request: Request,
    pipeline_id: uuid.UUID,
    dto: PipelineStageCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> PipelineStageRead | JSONResponse:
    try:
        require_permission(user, "crm.pipelines.manage")
        return pipeline_service.add_stage(db, user, pipeline_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_pipeline_stage_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@pipelines_router.get("/pipelines/default", response_model=PipelineRead)
def get_default_pipeline(
    request: Request,
    selling_legal_entity_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> PipelineRead | JSONResponse:
    try:
        require_any_permission(user, ["crm.pipelines.read", "crm.opportunities.read"])
        if include_inactive:
            require_permission(user, "crm.pipelines.manage")
        return pipeline_service.get_default_pipeline_with_stages(
            db,
            user,
            selling_legal_entity_id=selling_legal_entity_id,
            include_inactive=include_inactive,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_pipeline_default_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@pipelines_router.get("/pipelines/{pipeline_id}", response_model=PipelineRead)
def get_pipeline(
    request: Request,
    pipeline_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> PipelineRead | JSONResponse:
    try:
        require_any_permission(user, ["crm.pipelines.read", "crm.opportunities.read"])
        if include_inactive:
            require_permission(user, "crm.pipelines.manage")
        return pipeline_service.get_pipeline(db, user, pipeline_id, include_inactive=include_inactive)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_pipeline_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@pipelines_router.get("/pipelines/{pipeline_id}/stages", response_model=list[PipelineStageRead])
def list_pipeline_stages(
    request: Request,
    pipeline_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[PipelineStageRead] | JSONResponse:
    try:
        require_any_permission(user, ["crm.pipelines.read", "crm.opportunities.read"])
        if include_inactive:
            require_permission(user, "crm.pipelines.manage")
        return pipeline_service.list_stages(db, user, pipeline_id, include_inactive=include_inactive)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_pipeline_stage_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.get("/opportunities", response_model=list[OpportunityRead])
def list_opportunities(
    request: Request,
    stage_id: uuid.UUID | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    forecast_category: str | None = Query(default=None),
    expected_close_from: datetime | None = Query(default=None),
    expected_close_to: datetime | None = Query(default=None),
    account_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[OpportunityRead] | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.read")
        return opportunity_service.list_opportunities(
            db,
            user,
            filters={
                "stage_id": stage_id,
                "owner_user_id": owner_user_id,
                "forecast_category": forecast_category,
                "expected_close_from": expected_close_from.date() if expected_close_from else None,
                "expected_close_to": expected_close_to.date() if expected_close_to else None,
                "account_id": account_id,
            },
            cursor=cursor,
            limit=limit,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    request: Request,
    dto: OpportunityCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.create")
        return opportunity_service.create_opportunity(db, user, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(
    request: Request,
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.read")
        return opportunity_service.get_opportunity(db, user, opportunity_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.patch("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def patch_opportunity(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: OpportunityUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.update")
        return opportunity_service.update_opportunity(db, user, opportunity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/change-stage", response_model=OpportunityRead)
def change_opportunity_stage(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: OpportunityChangeStageRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.change_stage")
        return opportunity_service.change_stage(db, user, opportunity_id, dto, idempotency_key)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_change_stage_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/close-won", response_model=OpportunityRead)
def close_opportunity_won(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: OpportunityCloseWonRequest,
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.close_won")
        return opportunity_service.close_won(db, user, opportunity_id, dto, idempotency_key, sync=sync)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_close_won_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/revenue/retry", response_model=RevenueHandoffRetryResponse)
def retry_revenue_handoff(
    request: Request,
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    sync: bool = Query(default=False),
) -> RevenueHandoffRetryResponse | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.revenue_handoff")
        job = revenue_handoff_service.retry_handoff(db, user, opportunity_id)
        if sync:
            job = revenue_handoff_job_runner.run_revenue_handoff_job(db, user, job.id)
        return RevenueHandoffRetryResponse(job_id=job.id, status=job.status)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY and detail.get("code") == "REVENUE_HANDOFF_NOT_FAILED":
            return error_response(
                request,
                status_code=exc.status_code,
                code="REVENUE_HANDOFF_NOT_FAILED",
                message=detail.get("message", "Opportunity revenue handoff is not in failed state"),
                details=exc.detail,
            )
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_revenue_retry_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/close-lost", response_model=OpportunityRead)
def close_opportunity_lost(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: OpportunityCloseLostRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.close_lost")
        return opportunity_service.close_lost(db, user, opportunity_id, dto, idempotency_key)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_close_lost_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/reopen", response_model=OpportunityRead)
def reopen_opportunity(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: OpportunityReopenRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> OpportunityRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.reopen")
        return opportunity_service.reopen(db, user, opportunity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_reopen_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.post("/opportunities/{opportunity_id}/revenue/handoff", response_model=OpportunityRevenueRead)
def trigger_revenue_handoff(
    request: Request,
    opportunity_id: uuid.UUID,
    dto: RevenueHandoffRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OpportunityRevenueRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.revenue_handoff")
        return revenue_handoff_service.trigger_handoff(db, user, opportunity_id, dto.mode, idempotency_key)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY and detail.get("code") == "OPPORTUNITY_NOT_CLOSED_WON":
            return error_response(
                request,
                status_code=exc.status_code,
                code="OPPORTUNITY_NOT_CLOSED_WON",
                message=detail.get("message", "Opportunity must be ClosedWon"),
                details=exc.detail,
            )
        if exc.status_code == status.HTTP_502_BAD_GATEWAY and detail.get("code") == "REVENUE_UNAVAILABLE":
            return error_response(
                request,
                status_code=exc.status_code,
                code="REVENUE_UNAVAILABLE",
                message=detail.get("message", "Revenue module unavailable"),
                details=exc.detail,
            )
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_revenue_handoff_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@opportunities_router.get("/opportunities/{opportunity_id}/revenue", response_model=OpportunityRevenueRead)
def get_opportunity_revenue_status(
    request: Request,
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> OpportunityRevenueRead | JSONResponse:
    try:
        require_permission(user, "crm.opportunities.read")
        return revenue_handoff_service.get_revenue_status(db, user, opportunity_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_opportunity_revenue_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in {"account", "contact", "lead", "opportunity"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid entity_type")


@custom_fields_router.get("/custom-fields/{entity_type}", response_model=list[CustomFieldDefinitionRead])
def list_custom_field_definitions(
    request: Request,
    entity_type: str,
    legal_entity_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[CustomFieldDefinitionRead] | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.custom_fields.read")
        return custom_field_service.list_definitions(
            db,
            entity_type,
            user,
            legal_entity_id=legal_entity_id,
            include_inactive=include_inactive,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_custom_fields_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@custom_fields_router.post("/custom-fields/{entity_type}", response_model=CustomFieldDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_custom_field_definition(
    request: Request,
    entity_type: str,
    dto: CustomFieldDefinitionCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> CustomFieldDefinitionRead | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.custom_fields.manage")
        return custom_field_service.create_definition(db, entity_type, dto, user)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_custom_fields_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@custom_fields_router.patch("/custom-fields/definitions/{definition_id}", response_model=CustomFieldDefinitionRead)
def update_custom_field_definition(
    request: Request,
    definition_id: uuid.UUID,
    dto: CustomFieldDefinitionUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> CustomFieldDefinitionRead | JSONResponse:
    try:
        require_permission(user, "crm.custom_fields.manage")
        return custom_field_service.update_definition(db, definition_id, dto, user)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_custom_fields_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.get("/workflows", response_model=list[WorkflowRuleRead])
def list_workflow_rules(
    request: Request,
    trigger_event: str | None = Query(default=None),
    legal_entity_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[WorkflowRuleRead] | JSONResponse:
    try:
        require_permission(user, "crm.workflows.read")
        return workflow_service.list_rules(
            db,
            user,
            legal_entity_id=legal_entity_id,
            trigger_event=trigger_event,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.post("/workflows", response_model=WorkflowRuleRead, status_code=status.HTTP_201_CREATED)
def create_workflow_rule(
    request: Request,
    dto: WorkflowRuleCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> WorkflowRuleRead | JSONResponse:
    try:
        require_permission(user, "crm.workflows.manage")
        return workflow_service.create_rule(db, dto, user)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.patch("/workflows/{rule_id}", response_model=WorkflowRuleRead)
def update_workflow_rule(
    request: Request,
    rule_id: uuid.UUID,
    dto: WorkflowRuleUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> WorkflowRuleRead | JSONResponse:
    try:
        require_permission(user, "crm.workflows.manage")
        return workflow_service.update_rule(db, rule_id, dto, user)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.delete("/workflows/{rule_id}", status_code=status.HTTP_200_OK, response_model=None)
def delete_workflow_rule(
    request: Request,
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, str] | JSONResponse:
    try:
        require_permission(user, "crm.workflows.manage")
        workflow_service.soft_delete_rule(db, rule_id, user)
        return {"status": "deleted"}
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_delete_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.post("/workflows/{rule_id}/dry-run", response_model=WorkflowDryRunResponse)
def dry_run_workflow_rule(
    request: Request,
    rule_id: uuid.UUID,
    dto: WorkflowDryRunRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> WorkflowDryRunResponse | JSONResponse:
    try:
        require_any_permission(user, ["crm.workflows.execute", "crm.workflows.manage"])
        return workflow_service.execute_rule(
            db,
            user,
            rule_id,
            WorkflowEntityRef(type=dto.entity_type, id=dto.entity_id),
            dry_run=True,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_dry_run_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.post("/workflows/{rule_id}/execute", response_model=WorkflowDryRunResponse)
def execute_workflow_rule(
    request: Request,
    rule_id: uuid.UUID,
    dto: WorkflowDryRunRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> WorkflowDryRunResponse | JSONResponse:
    try:
        require_any_permission(user, ["crm.workflows.execute", "crm.workflows.manage"])
        return workflow_service.execute_rule(
            db,
            user,
            rule_id,
            WorkflowEntityRef(type=dto.entity_type, id=dto.entity_id),
            dry_run=False,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_execute_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.get("/workflows/executions", response_model=list[dict[str, Any]])
def list_workflow_executions(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    rule_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[dict[str, Any]] | JSONResponse:
    try:
        require_permission(user, "crm.workflows.read")
        jobs = import_export_service.list_workflow_execution_jobs(
            db,
            user,
            entity_type=entity_type,
            entity_id=entity_id,
            rule_id=rule_id,
            cursor=cursor,
            limit=limit,
        )
        return [import_export_service.to_response(job) for job in jobs]
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_executions_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@workflows_router.get("/workflows/executions/{job_id}", response_model=dict[str, Any])
def get_workflow_execution(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.workflows.read")
        job = import_export_service.get_workflow_execution_job(db, user, job_id)
        return import_export_service.to_response(job)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_workflow_execution_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@import_export_router.post("/import/accounts", response_model=dict[str, Any])
def import_accounts_csv(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.import.execute")
        mapping_payload = json.loads(mapping)
        content = file.file.read()
        source_file_id = files_stub.store_bytes(content, file.filename or "import.csv", file.content_type or "text/csv")

        job = import_export_service.create_job(
            db,
            user,
            job_type="CSV_IMPORT",
            entity_type="account",
            params={"mapping": mapping_payload, "source_file_id": str(source_file_id)},
        )
        if sync:
            job = import_export_service.run_job_sync(db, user, job.id)
        return import_export_service.to_response(job)
    except (ValueError, json.JSONDecodeError) as exc:
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="crm_import_accounts_failed",
            message=str(exc),
            details=str(exc),
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_import_accounts_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@import_export_router.post("/import/contacts", response_model=dict[str, Any])
def import_contacts_csv(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(...),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.import.execute")
        mapping_payload = json.loads(mapping)
        content = file.file.read()
        source_file_id = files_stub.store_bytes(content, file.filename or "import.csv", file.content_type or "text/csv")

        job = import_export_service.create_job(
            db,
            user,
            job_type="CSV_IMPORT",
            entity_type="contact",
            params={"mapping": mapping_payload, "source_file_id": str(source_file_id)},
        )
        if sync:
            job = import_export_service.run_job_sync(db, user, job.id)
        return import_export_service.to_response(job)
    except (ValueError, json.JSONDecodeError) as exc:
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="crm_import_contacts_failed",
            message=str(exc),
            details=str(exc),
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_import_contacts_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@import_export_router.post("/export/accounts", response_model=dict[str, Any])
def export_accounts_csv(
    request: Request,
    filters: dict[str, Any] = Body(default_factory=dict),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.export.execute")
        job = import_export_service.create_job(
            db,
            user,
            job_type="CSV_EXPORT",
            entity_type="account",
            params={"filters": filters},
        )
        if sync:
            job = import_export_service.run_job_sync(db, user, job.id)
        return import_export_service.to_response(job)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_export_accounts_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@import_export_router.post("/export/contacts", response_model=dict[str, Any])
def export_contacts_csv(
    request: Request,
    filters: dict[str, Any] = Body(default_factory=dict),
    sync: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.export.execute")
        job = import_export_service.create_job(
            db,
            user,
            job_type="CSV_EXPORT",
            entity_type="contact",
            params={"filters": filters},
        )
        if sync:
            job = import_export_service.run_job_sync(db, user, job.id)
        return import_export_service.to_response(job)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_export_contacts_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@jobs_router.get("/jobs/{job_id}", response_model=dict[str, Any])
def get_job_status(
    request: Request,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> dict[str, Any] | JSONResponse:
    try:
        require_permission(user, "crm.jobs.read")
        job = import_export_service.get_job(db, user, job_id)
        return import_export_service.to_response(job)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_job_get_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@jobs_router.get("/jobs/{job_id}/download/{artifact_type}", response_model=None)
def download_job_artifact(
    request: Request,
    job_id: uuid.UUID,
    artifact_type: str,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> Response | JSONResponse:
    try:
        require_permission(user, "crm.jobs.read")
        artifact = import_export_service.get_job_artifact(db, user, job_id, artifact_type)
        payload = files_stub.get_bytes(artifact.file_id)
        return Response(
            content=payload,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.artifact_type.lower()}_{artifact.file_id}.csv"',
            },
        )
    except FileNotFoundError as exc:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="crm_job_download_failed",
            message=str(exc),
            details=str(exc),
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_job_download_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@search_router.get("/search", response_model=list[dict[str, Any]])
def global_search(
    request: Request,
    q: str = Query(..., min_length=1),
    types: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[dict[str, Any]] | JSONResponse:
    try:
        require_permission(user, "crm.search.read")
        selected_types = {"account", "contact", "lead", "opportunity"}
        if types:
            parsed = {item.strip().lower() for item in types.split(",") if item.strip()}
            if not parsed:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="types cannot be empty")
            invalid = parsed - selected_types
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid types: {', '.join(sorted(invalid))}",
                )
            selected_types = parsed

        return search_entities(db, user, q, selected_types, limit)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_search_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@audit_router.get("/audit", response_model=list[AuditRead])
def list_audit_logs(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[AuditRead] | JSONResponse:
    try:
        require_permission(user, "crm.audit.read")
        return audit_service.list_audit_logs(
            db,
            user,
            filters={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actor_user_id": actor_user_id,
                "action": action,
                "date_from": date_from,
                "date_to": date_to,
                "correlation_id": correlation_id,
            },
            cursor=cursor,
            limit=limit,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_audit_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@audit_router.get("/entities/{entity_type}/{entity_id}/audit", response_model=list[AuditRead])
def list_entity_audit_logs(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[AuditRead] | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.audit.read")
        return audit_service.list_entity_audit_logs(db, user, entity_type, entity_id, cursor=cursor, limit=limit)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_entity_audit_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@activities_router.get("/entities/{entity_type}/{entity_id}/activities", response_model=list[ActivityRead])
def list_activities(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    activity_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    due_from: datetime | None = Query(default=None),
    due_to: datetime | None = Query(default=None),
    assigned_to_user_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[ActivityRead] | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.activities.read")
        return activity_service.list_activities(
            db,
            user,
            entity_type,
            entity_id,
            filters={
                "activity_type": activity_type,
                "status": status_filter,
                "due_from": due_from,
                "due_to": due_to,
                "assigned_to_user_id": assigned_to_user_id,
            },
            cursor=cursor,
            limit=limit,
        )
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_activity_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@activities_router.post("/entities/{entity_type}/{entity_id}/activities", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    dto: ActivityCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ActivityRead | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.activities.create")
        return activity_service.create_activity(db, user, entity_type, entity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_activity_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@activities_router.patch("/activities/{activity_id}", response_model=ActivityRead)
def patch_activity(
    request: Request,
    activity_id: uuid.UUID,
    dto: ActivityUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ActivityRead | JSONResponse:
    try:
        require_permission(user, "crm.activities.update")
        return activity_service.update_activity(db, user, activity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_activity_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@activities_router.post("/activities/{activity_id}/complete", response_model=ActivityRead)
def complete_activity(
    request: Request,
    activity_id: uuid.UUID,
    dto: CompleteActivityRequest,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> ActivityRead | JSONResponse:
    try:
        require_permission(user, "crm.activities.complete")
        return activity_service.complete_activity(db, user, activity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_activity_complete_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@notes_router.get("/entities/{entity_type}/{entity_id}/notes", response_model=list[NoteRead])
def list_notes(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[NoteRead] | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.notes.read")
        return note_service.list_notes(db, user, entity_type, entity_id, cursor, limit)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_note_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@notes_router.post("/entities/{entity_type}/{entity_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    dto: NoteCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> NoteRead | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.notes.create")
        return note_service.create_note(db, user, entity_type, entity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_note_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@notes_router.patch("/notes/{note_id}", response_model=NoteRead)
def patch_note(
    request: Request,
    note_id: uuid.UUID,
    dto: NoteUpdate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> NoteRead | JSONResponse:
    try:
        require_permission(user, "crm.notes.update")
        return note_service.update_note(db, user, note_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_note_update_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@attachments_router.get("/entities/{entity_type}/{entity_id}/attachments", response_model=list[AttachmentLinkRead])
def list_attachments(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> list[AttachmentLinkRead] | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.attachments.read")
        return attachment_service.list_attachments(db, user, entity_type, entity_id)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_attachment_list_failed",
            message=str(exc.detail),
            details=exc.detail,
        )


@attachments_router.post("/entities/{entity_type}/{entity_id}/attachments", response_model=AttachmentLinkRead, status_code=status.HTTP_201_CREATED)
def create_attachment(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    dto: AttachmentLinkCreate,
    db: Session = Depends(get_db),
    user: ActorUser = Depends(get_current_user),
) -> AttachmentLinkRead | JSONResponse:
    try:
        _validate_entity_type(entity_type)
        require_permission(user, "crm.attachments.create")
        return attachment_service.create_attachment_link(db, user, entity_type, entity_id, dto)
    except HTTPException as exc:
        return error_response(
            request,
            status_code=exc.status_code,
            code="crm_attachment_create_failed",
            message=str(exc.detail),
            details=exc.detail,
        )
