from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, model_validator


CustomFieldDataType = Literal["text", "number", "bool", "date", "select"]


class CustomFieldDefinitionCreate(BaseModel):
    field_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    data_type: CustomFieldDataType
    is_required: bool = False
    allowed_values: list[str] | None = None
    legal_entity_id: UUID | None = None
    is_active: bool = True


class CustomFieldDefinitionUpdate(BaseModel):
    label: str | None = None
    is_required: bool | None = None
    allowed_values: list[str] | None = None
    is_active: bool | None = None


class CustomFieldDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    field_key: str
    label: str
    data_type: CustomFieldDataType
    is_required: bool
    allowed_values: list[str] | None
    legal_entity_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


WorkflowConditionOp = Literal["eq", "neq", "in", "contains", "gt", "gte", "lt", "lte", "exists"]


class WorkflowConditionLeaf(BaseModel):
    path: str = Field(min_length=1)
    op: WorkflowConditionOp
    value: Any = None


class WorkflowConditionAll(BaseModel):
    all: list["WorkflowCondition"] = Field(min_length=1)


class WorkflowConditionAny(BaseModel):
    any: list["WorkflowCondition"] = Field(min_length=1)


class WorkflowConditionNot(BaseModel):
    not_: "WorkflowCondition" = Field(alias="not")

    model_config = ConfigDict(populate_by_name=True)


WorkflowCondition = WorkflowConditionLeaf | WorkflowConditionAll | WorkflowConditionAny | WorkflowConditionNot


class WorkflowEntityRef(BaseModel):
    type: Literal["account", "contact", "lead", "opportunity"]
    id: UUID


class WorkflowActionSetField(BaseModel):
    type: Literal["SET_FIELD"]
    path: str = Field(min_length=1)
    value: Any


class WorkflowActionCreateTask(BaseModel):
    type: Literal["CREATE_TASK"]
    title: str = Field(min_length=1)
    due_in_days: int
    assigned_to_user_id: UUID
    entity_ref: WorkflowEntityRef


class WorkflowActionNotify(BaseModel):
    type: Literal["NOTIFY"]
    notification_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


WorkflowAction = Annotated[
    WorkflowActionSetField | WorkflowActionCreateTask | WorkflowActionNotify,
    Field(discriminator="type"),
]

_workflow_action_list_adapter = TypeAdapter(list[WorkflowAction])


def _parse_workflow_condition(value: Any) -> WorkflowCondition:
    if not isinstance(value, dict):
        raise ValueError("condition_json must be an object")

    if "all" in value:
        items = value.get("all")
        if not isinstance(items, list) or not items:
            raise ValueError("all must be a non-empty list")
        return WorkflowConditionAll(all=[_parse_workflow_condition(item) for item in items])

    if "any" in value:
        items = value.get("any")
        if not isinstance(items, list) or not items:
            raise ValueError("any must be a non-empty list")
        return WorkflowConditionAny(any=[_parse_workflow_condition(item) for item in items])

    if "not" in value:
        return WorkflowConditionNot.model_validate({"not": _parse_workflow_condition(value.get("not"))})

    return WorkflowConditionLeaf.model_validate(value)


class WorkflowRuleCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    is_active: bool = True
    legal_entity_id: UUID | None = None
    trigger_event: str = Field(min_length=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)
    condition_json: dict[str, Any]
    actions_json: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_workflow_structure(self) -> "WorkflowRuleCreate":
        condition = _parse_workflow_condition(self.condition_json)
        actions = _workflow_action_list_adapter.validate_python(self.actions_json)
        self.condition_json = condition.model_dump(by_alias=True)
        self.actions_json = [action.model_dump(mode="json") for action in actions]
        return self


class WorkflowRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    legal_entity_id: UUID | None = None
    trigger_event: str | None = Field(default=None, min_length=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)
    condition_json: dict[str, Any] | None = None
    actions_json: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def validate_workflow_structure(self) -> "WorkflowRuleUpdate":
        if self.condition_json is not None:
            condition = _parse_workflow_condition(self.condition_json)
            self.condition_json = condition.model_dump(by_alias=True)
        if self.actions_json is not None:
            actions = _workflow_action_list_adapter.validate_python(self.actions_json)
            self.actions_json = [action.model_dump(mode="json") for action in actions]
        return self


class WorkflowRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    legal_entity_id: UUID | None
    trigger_event: str
    cooldown_seconds: int | None
    condition_json: dict[str, Any]
    actions_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class WorkflowDryRunRequest(BaseModel):
    entity_type: Literal["account", "contact", "lead", "opportunity"]
    entity_id: UUID


class WorkflowDryRunResponse(BaseModel):
    matched: bool
    planned_actions: list[dict[str, Any]] = Field(default_factory=list)
    planned_mutations: dict[str, Any] = Field(default_factory=dict)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1)
    owner_user_id: UUID | None = None
    primary_region_code: str | None = None
    default_currency_code: str | None = None
    external_reference: str | None = None
    legal_entity_ids: list[UUID] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    row_version: int = Field(ge=1)
    name: str | None = None
    status: str | None = None
    owner_user_id: UUID | None = None
    primary_region_code: str | None = None
    default_currency_code: str | None = None
    external_reference: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    owner_user_id: UUID | None
    primary_region_code: str | None
    default_currency_code: str | None
    external_reference: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    legal_entity_ids: list[UUID]
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ContactCreate(BaseModel):
    account_id: UUID
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    department: str | None = None
    locale: str | None = None
    timezone: str | None = None
    owner_user_id: UUID | None = None
    is_primary: bool = False
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ContactUpdate(BaseModel):
    row_version: int = Field(ge=1)
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    department: str | None = None
    locale: str | None = None
    timezone: str | None = None
    owner_user_id: UUID | None = None
    is_primary: bool | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    title: str | None
    department: str | None
    locale: str | None
    timezone: str | None
    owner_user_id: UUID | None
    is_primary: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadCreate(BaseModel):
    status: str
    source: str
    selling_legal_entity_id: UUID
    region_code: str
    owner_user_id: UUID | None = None
    company_name: str | None = None
    contact_first_name: str | None = None
    contact_last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    qualification_notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    row_version: int = Field(ge=1)
    status: str | None = None
    source: str | None = None
    owner_user_id: UUID | None = None
    region_code: str | None = None
    company_name: str | None = None
    contact_first_name: str | None = None
    contact_last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    qualification_notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    source: str
    owner_user_id: UUID | None
    selling_legal_entity_id: UUID
    region_code: str
    company_name: str | None
    contact_first_name: str | None
    contact_last_name: str | None
    email: str | None
    phone: str | None
    qualification_notes: str | None
    disqualify_reason_code: str | None
    disqualify_notes: str | None
    converted_account_id: UUID | None
    converted_contact_id: UUID | None
    converted_opportunity_id: UUID | None
    converted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadDisqualifyRequest(BaseModel):
    reason_code: str = Field(min_length=1)
    notes: str | None = None
    row_version: int = Field(ge=1)


class LeadConvertAccountInput(BaseModel):
    mode: str
    account_id: UUID | None = None
    name: str | None = None
    primary_region_code: str | None = None
    owner_user_id: UUID | None = None
    legal_entity_ids: list[UUID] = Field(default_factory=list)


class LeadConvertContactInput(BaseModel):
    mode: str
    contact_id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    owner_user_id: UUID | None = None
    is_primary: bool | None = None


class LeadConvertRequest(BaseModel):
    row_version: int = Field(ge=1)
    account: LeadConvertAccountInput
    contact: LeadConvertContactInput
    create_opportunity: bool = False


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1)
    selling_legal_entity_id: UUID | None = None
    is_default: bool = False


class PipelineStageCreate(BaseModel):
    name: str = Field(min_length=1)
    position: int = Field(ge=1)
    stage_type: str
    default_probability: int | None = Field(default=None, ge=0, le=100)
    requires_amount: bool = False
    requires_expected_close_date: bool = False
    is_active: bool = True


class PipelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    selling_legal_entity_id: UUID | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    stages: list["PipelineStageRead"] = Field(default_factory=list)


class PipelineStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pipeline_id: UUID
    name: str
    position: int
    stage_type: str
    default_probability: int | None
    requires_amount: bool
    requires_expected_close_date: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int


class AuditRead(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: str
    occurred_at: datetime
    correlation_id: str | None
    before: dict | None
    after: dict | None


class OpportunityCreate(BaseModel):
    account_id: UUID
    name: str = Field(min_length=1)
    selling_legal_entity_id: UUID
    region_code: str = Field(min_length=1)
    currency_code: str = Field(min_length=1)
    amount: float = 0
    owner_user_id: UUID | None = None
    expected_close_date: date | None = None
    primary_contact_id: UUID | None = None
    stage_id: UUID | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    forecast_category: str | None = "Pipeline"
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class OpportunityUpdate(BaseModel):
    row_version: int = Field(ge=1)
    name: str | None = None
    region_code: str | None = None
    currency_code: str | None = None
    amount: float | None = None
    owner_user_id: UUID | None = None
    expected_close_date: date | None = None
    primary_contact_id: UUID | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    forecast_category: str | None = None
    selling_legal_entity_id: UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    name: str
    stage_id: UUID
    selling_legal_entity_id: UUID
    region_code: str
    currency_code: str
    amount: float
    owner_user_id: UUID | None
    expected_close_date: date | None
    probability: int | None
    forecast_category: str | None
    primary_contact_id: UUID | None
    close_reason: str | None
    revenue_quote_id: UUID | None
    revenue_order_id: UUID | None
    revenue_handoff_status: str
    revenue_handoff_mode: str | None
    revenue_handoff_last_error: str | None
    revenue_handoff_requested_at: datetime | None
    revenue_handoff_completed_at: datetime | None
    closed_won_at: datetime | None
    closed_lost_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class OpportunityChangeStageRequest(BaseModel):
    stage_id: UUID
    row_version: int = Field(ge=1)


class OpportunityRevenueHandoffInput(BaseModel):
    requested: bool = False
    mode: Literal["CREATE_DRAFT_QUOTE", "CREATE_DRAFT_ORDER"] | None = None


class OpportunityCloseWonRequest(BaseModel):
    row_version: int = Field(ge=1)
    revenue_handoff: OpportunityRevenueHandoffInput | None = None
    revenue_handoff_mode: str | None = None
    revenue_handoff_requested: bool | None = None


class OpportunityCloseLostRequest(BaseModel):
    row_version: int = Field(ge=1)
    close_reason: str = Field(min_length=1)


class OpportunityReopenRequest(BaseModel):
    row_version: int = Field(ge=1)
    new_stage_id: UUID | None = None


class RevenueHandoffRequest(BaseModel):
    mode: Literal["CREATE_DRAFT_QUOTE", "CREATE_DRAFT_ORDER"]


class RevenueDocStatusRead(BaseModel):
    id: UUID
    status: str
    updated_at: datetime


class OpportunityRevenueRead(BaseModel):
    quote: RevenueDocStatusRead | None = None
    order: RevenueDocStatusRead | None = None


class RevenueHandoffRetryResponse(BaseModel):
    job_id: UUID
    status: str


class ActivityCreate(BaseModel):
    activity_type: str
    subject: str | None = None
    body: str | None = None
    owner_user_id: UUID | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    status: str = "Open"
    completed_at: datetime | None = None


class ActivityUpdate(BaseModel):
    row_version: int = Field(ge=1)
    subject: str | None = None
    body: str | None = None
    owner_user_id: UUID | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    status: str | None = None
    completed_at: datetime | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    activity_type: str
    subject: str | None
    body: str | None
    owner_user_id: UUID | None
    assigned_to_user_id: UUID | None
    due_at: datetime | None
    status: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int


class CompleteActivityRequest(BaseModel):
    row_version: int = Field(ge=1)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1)
    content_format: str = "markdown"
    owner_user_id: UUID | None = None


class NoteUpdate(BaseModel):
    row_version: int = Field(ge=1)
    content: str | None = None
    content_format: str | None = None


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    content: str
    content_format: str
    owner_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    row_version: int


class AttachmentLinkCreate(BaseModel):
    file_id: UUID


class AttachmentLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    file_id: UUID
    created_by_user_id: UUID | None
    created_at: datetime
