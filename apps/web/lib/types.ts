export interface ApiErrorEnvelope {
  code: string;
  message: string;
  details: unknown;
  correlation_id: string | null;
}

export type CustomFieldDataType = "text" | "number" | "bool" | "date" | "select";

export interface CustomFieldDefinitionRead {
  id: string;
  entity_type: "account" | "contact" | "lead" | "opportunity";
  field_key: string;
  label: string;
  data_type: CustomFieldDataType;
  is_required: boolean;
  allowed_values: string[] | null;
  legal_entity_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomFieldDefinitionCreate {
  field_key: string;
  label: string;
  data_type: CustomFieldDataType;
  is_required?: boolean;
  allowed_values?: string[];
  legal_entity_id?: string | null;
  is_active?: boolean;
}

export interface CustomFieldDefinitionUpdate {
  label?: string;
  is_required?: boolean;
  allowed_values?: string[];
  is_active?: boolean;
}

export type WorkflowEntityType = "account" | "contact" | "lead" | "opportunity";
export type WorkflowOperator = "eq" | "neq" | "in" | "contains" | "gt" | "gte" | "lt" | "lte" | "exists";

export interface WorkflowConditionLeaf {
  path: string;
  op: WorkflowOperator;
  value?: unknown;
}

export interface WorkflowConditionAll {
  all: WorkflowCondition[];
}

export interface WorkflowConditionAny {
  any: WorkflowCondition[];
}

export interface WorkflowConditionNot {
  not: WorkflowCondition;
}

export type WorkflowCondition = WorkflowConditionLeaf | WorkflowConditionAll | WorkflowConditionAny | WorkflowConditionNot;

export interface WorkflowActionSetField {
  type: "SET_FIELD";
  path: string;
  value: unknown;
}

export interface WorkflowActionCreateTask {
  type: "CREATE_TASK";
  title: string;
  due_in_days: number;
  assigned_to_user_id: string;
  entity_ref: { type: WorkflowEntityType; id: string };
}

export interface WorkflowActionNotify {
  type: "NOTIFY";
  notification_type: string;
  payload: Record<string, unknown>;
}

export type WorkflowAction = WorkflowActionSetField | WorkflowActionCreateTask | WorkflowActionNotify;

export interface WorkflowRuleRead {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  legal_entity_id: string | null;
  trigger_event: string;
  condition_json: Record<string, unknown>;
  actions_json: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface WorkflowRuleCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
  legal_entity_id?: string | null;
  trigger_event: string;
  condition_json: Record<string, unknown>;
  actions_json: Record<string, unknown>[];
}

export interface WorkflowRuleUpdate {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  legal_entity_id?: string | null;
  trigger_event?: string;
  condition_json?: Record<string, unknown>;
  actions_json?: Record<string, unknown>[];
}

export interface WorkflowDryRunRequest {
  entity_type: WorkflowEntityType;
  entity_id: string;
}

export interface WorkflowDryRunResponse {
  matched: boolean;
  planned_actions: Record<string, unknown>[];
  planned_mutations: Record<string, unknown>;
}

export interface AccountRead {
  id: string;
  name: string;
  status: string;
  owner_user_id: string | null;
  primary_region_code: string | null;
  default_currency_code: string | null;
  external_reference: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
  legal_entity_ids: string[];
  custom_fields: Record<string, unknown>;
}

export interface ContactRead {
  id: string;
  account_id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  title: string | null;
  department: string | null;
  locale: string | null;
  timezone: string | null;
  owner_user_id: string | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
  custom_fields: Record<string, unknown>;
}

export interface OpportunityRead {
  id: string;
  account_id: string;
  name: string;
  stage_id: string;
  selling_legal_entity_id: string;
  region_code: string;
  currency_code: string;
  amount: number;
  owner_user_id: string | null;
  expected_close_date: string | null;
  probability: number | null;
  forecast_category: string | null;
  primary_contact_id: string | null;
  close_reason: string | null;
  revenue_quote_id: string | null;
  revenue_order_id: string | null;
  closed_won_at: string | null;
  closed_lost_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
  custom_fields: Record<string, unknown>;
}

export interface PipelineRead {
  id: string;
  name: string;
  selling_legal_entity_id?: string | null;
  is_default: boolean;
  stages?: PipelineStageRead[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
}

export interface PipelineStageRead {
  id: string;
  pipeline_id: string;
  name: string;
  position: number;
  stage_type: string;
  default_probability: number | null;
  requires_amount: boolean;
  requires_expected_close_date: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
}

export interface OpportunityChangeStageRequest {
  stage_id: string;
  row_version: number;
}

export interface OpportunityCloseWonRequest {
  row_version: number;
  revenue_handoff_mode?: string | null;
  revenue_handoff_requested?: boolean | null;
}

export interface OpportunityCloseLostRequest {
  row_version: number;
  close_reason: string;
}

export interface OpportunityReopenRequest {
  row_version: number;
  new_stage_id?: string | null;
}

export interface RevenueDocStatus {
  id: string;
  status: string;
  updated_at?: string;
}

export interface OpportunityRevenueRead {
  quote?: RevenueDocStatus;
  order?: RevenueDocStatus;
}

export interface RevenueHandoffRequest {
  mode: "CREATE_DRAFT_QUOTE" | "CREATE_DRAFT_ORDER";
}

export interface ActivityRead {
  id: string;
  entity_type: string;
  entity_id: string;
  activity_type: string;
  subject: string | null;
  body: string | null;
  owner_user_id: string | null;
  assigned_to_user_id: string | null;
  due_at: string | null;
  status: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
}

export interface AuditRead {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_user_id: string;
  occurred_at: string;
  correlation_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface NoteRead {
  id: string;
  entity_type: string;
  entity_id: string;
  content: string;
  content_format: string;
  owner_user_id: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
}

export interface AttachmentLinkRead {
  id: string;
  entity_type: string;
  entity_id: string;
  file_id: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface LeadRead {
  id: string;
  status: string;
  source: string;
  owner_user_id: string | null;
  selling_legal_entity_id: string;
  region_code: string;
  company_name: string | null;
  contact_first_name: string | null;
  contact_last_name: string | null;
  email: string | null;
  phone: string | null;
  qualification_notes: string | null;
  disqualify_reason_code: string | null;
  disqualify_notes: string | null;
  converted_account_id: string | null;
  converted_contact_id: string | null;
  converted_opportunity_id: string | null;
  converted_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  row_version: number;
  custom_fields: Record<string, unknown>;
}

export interface LeadCreate {
  status: string;
  source: string;
  selling_legal_entity_id: string;
  region_code: string;
  owner_user_id?: string | null;
  company_name?: string | null;
  contact_first_name?: string | null;
  contact_last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  qualification_notes?: string | null;
  custom_fields?: Record<string, unknown>;
}

export interface LeadUpdate {
  row_version: number;
  status?: string | null;
  source?: string | null;
  owner_user_id?: string | null;
  region_code?: string | null;
  company_name?: string | null;
  contact_first_name?: string | null;
  contact_last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  qualification_notes?: string | null;
  custom_fields?: Record<string, unknown>;
}

export interface LeadDisqualifyRequest {
  reason_code: string;
  notes?: string | null;
  row_version: number;
}

export interface LeadConvertAccountInput {
  mode: "existing" | "new";
  account_id?: string | null;
  name?: string | null;
  primary_region_code?: string | null;
  owner_user_id?: string | null;
  legal_entity_ids?: string[];
}

export interface LeadConvertContactInput {
  mode: "existing" | "new";
  contact_id?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  owner_user_id?: string | null;
  is_primary?: boolean | null;
}

export interface LeadConvertRequest {
  row_version: number;
  account: LeadConvertAccountInput;
  contact: LeadConvertContactInput;
  create_opportunity: boolean;
}

export interface SearchResult {
  entity_type: "account" | "contact" | "lead" | "opportunity";
  entity_id: string;
  legal_entity_id: string | null;
  title: string;
  subtitle: string | null;
  updated_at: string;
}

export interface JobArtifact {
  artifact_type: "EXPORT_CSV" | "ERROR_REPORT_CSV";
  file_id: string;
  created_at: string;
}

export interface JobResponse {
  id: string;
  job_type: "CSV_IMPORT" | "CSV_EXPORT" | "WORKFLOW_EXECUTION" | "REVENUE_HANDOFF";
  entity_type: WorkflowEntityType;
  status: "Queued" | "Running" | "Succeeded" | "Failed" | "PartiallySucceeded";
  requested_by_user_id: string;
  legal_entity_id: string | null;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  artifacts: JobArtifact[];
}
