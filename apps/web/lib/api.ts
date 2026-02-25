import type {
  AccountRead,
  ActivityRead,
  AuditRead,
  ApiErrorEnvelope,
  AttachmentLinkRead,
  ContactRead,
  CustomFieldDefinitionCreate,
  CustomFieldDefinitionRead,
  CustomFieldDefinitionUpdate,
  JobResponse,
  LeadCreate,
  LeadDisqualifyRequest,
  LeadRead,
  LeadUpdate,
  LeadConvertRequest,
  NoteRead,
  OpportunityChangeStageRequest,
  OpportunityCloseLostRequest,
  OpportunityCloseWonRequest,
  OpportunityRevenueRead,
  OpportunityReopenRequest,
  OpportunityRead,
  PipelineRead,
  PipelineStageRead,
  RevenueHandoffRequest,
  SearchResult,
  WorkflowDryRunRequest,
  WorkflowDryRunResponse,
  WorkflowRuleCreate,
  WorkflowRuleRead,
  WorkflowRuleUpdate,
  FinanceARAgingReport,
  FinanceCashSummaryReport,
  FinanceInvoiceDrilldown,
  FinanceJournalDrilldown,
  FinancePaymentDrilldown,
  FinanceReconciliationReport,
  FinanceRevenueSummaryReport,
  FinanceTrialBalanceReport
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  envelope?: ApiErrorEnvelope;
  correlationId: string | null;
  requestCorrelationId: string | null;

  constructor(
    message: string,
    status: number,
    envelope?: ApiErrorEnvelope,
    correlationId?: string | null,
    requestCorrelationId?: string | null
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
    this.correlationId = correlationId ?? envelope?.correlation_id ?? null;
    this.requestCorrelationId = requestCorrelationId ?? null;
  }
}

export interface ApiToastMessage {
  message: string;
  correlationId: string | null;
}

function authHeaders() {
  const headers: Record<string, string> = {};
  const token = typeof window !== "undefined" ? window.localStorage.getItem("auth-token") : null;
  if (token) {
    headers.authorization = `Bearer ${token}`;
  }
  return headers;
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

function createCorrelationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const requestCorrelationId = createCorrelationId();
  headers.set("x-correlation-id", requestCorrelationId);
  const auth = authHeaders();
  Object.entries(auth).forEach(([key, value]) => headers.set(key, value));

  if (!(init?.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    const responseCorrelationId = response.headers.get("x-correlation-id");
    let envelope: ApiErrorEnvelope | undefined;
    try {
      envelope = (await response.json()) as ApiErrorEnvelope;
    } catch {
      envelope = undefined;
    }
    const resolvedCorrelationId = responseCorrelationId ?? envelope?.correlation_id ?? requestCorrelationId;
    if (envelope) {
      envelope = { ...envelope, correlation_id: resolvedCorrelationId };
    }
    throw new ApiError(
      envelope?.message ?? `Request failed (${response.status})`,
      response.status,
      envelope,
      resolvedCorrelationId,
      requestCorrelationId
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function toQuery<T extends object>(params: T) {
  const search = new URLSearchParams();
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const raw = search.toString();
  return raw ? `?${raw}` : "";
}

export interface AccountsListParams {
  name?: string;
  status?: string;
  owner_user_id?: string;
  cursor?: string;
  limit?: number;
}

export interface LeadsListParams {
  status?: string;
  source?: string;
  owner_user_id?: string;
  q?: string;
  cursor?: string;
  limit?: number;
}

export type CustomFieldEntityType = "account" | "contact" | "lead" | "opportunity";

export interface AuditLogsListParams {
  entity_type?: string;
  entity_id?: string;
  actor_user_id?: string;
  action?: string;
  date_from?: string;
  date_to?: string;
  correlation_id?: string;
  cursor?: string;
  limit?: number;
}

export interface WorkflowRuleListParams {
  trigger_event?: string;
  legal_entity_id?: string;
  active?: boolean;
  limit?: number;
  cursor?: string;
}

export interface WorkflowExecutionListParams {
  entity_type?: string;
  entity_id?: string;
  rule_id?: string;
  limit?: number;
  cursor?: string;
}

export function listAccounts(params: AccountsListParams) {
  return apiRequest<AccountRead[]>(`/api/crm/accounts${toQuery(params)}`);
}

export function listLeads(params: LeadsListParams) {
  return apiRequest<LeadRead[]>(`/api/crm/leads${toQuery(params)}`);
}

export function listCustomFieldDefinitions(entityType: CustomFieldEntityType, legalEntityId?: string) {
  return apiRequest<CustomFieldDefinitionRead[]>(
    `/api/crm/custom-fields/${entityType}${toQuery({ legal_entity_id: legalEntityId })}`
  );
}

export function createCustomFieldDefinition(entityType: CustomFieldEntityType, body: CustomFieldDefinitionCreate) {
  return apiRequest<CustomFieldDefinitionRead>(`/api/crm/custom-fields/${entityType}`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function updateCustomFieldDefinition(definitionId: string, body: CustomFieldDefinitionUpdate) {
  return apiRequest<CustomFieldDefinitionRead>(`/api/crm/custom-fields/definitions/${definitionId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function listWorkflowRules(params: WorkflowRuleListParams = {}) {
  return apiRequest<WorkflowRuleRead[]>(`/api/crm/workflows${toQuery(params)}`);
}

export async function getWorkflowRule(ruleId: string) {
  const rules = await listWorkflowRules();
  const rule = rules.find((item) => item.id === ruleId);
  if (!rule) {
    throw new Error("Workflow rule not found");
  }
  return rule;
}

export function createWorkflowRule(body: WorkflowRuleCreate) {
  return apiRequest<WorkflowRuleRead>("/api/crm/workflows", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function updateWorkflowRule(ruleId: string, body: WorkflowRuleUpdate) {
  return apiRequest<WorkflowRuleRead>(`/api/crm/workflows/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function deleteWorkflowRule(ruleId: string) {
  return apiRequest<{ status: string }>(`/api/crm/workflows/${ruleId}`, {
    method: "DELETE"
  });
}

export function dryRunWorkflowRule(ruleId: string, body: WorkflowDryRunRequest) {
  return apiRequest<WorkflowDryRunResponse>(`/api/crm/workflows/${ruleId}/dry-run`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function executeWorkflowRule(ruleId: string, body: WorkflowDryRunRequest) {
  return apiRequest<WorkflowDryRunResponse>(`/api/crm/workflows/${ruleId}/execute`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listWorkflowExecutions(params: WorkflowExecutionListParams = {}) {
  return apiRequest<JobResponse[]>(`/api/crm/workflows/executions${toQuery(params)}`);
}

export function getWorkflowExecution(jobId: string) {
  return apiRequest<JobResponse>(`/api/crm/workflows/executions/${jobId}`);
}

export function createLead(body: LeadCreate) {
  return apiRequest<LeadRead>("/api/crm/leads", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getLead(leadId: string) {
  return apiRequest<LeadRead>(`/api/crm/leads/${leadId}`);
}

export function patchLead(leadId: string, body: LeadUpdate) {
  return apiRequest<LeadRead>(`/api/crm/leads/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function disqualifyLead(leadId: string, body: LeadDisqualifyRequest) {
  return apiRequest<LeadRead>(`/api/crm/leads/${leadId}/disqualify`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function convertLead(leadId: string, body: LeadConvertRequest, idempotencyKey: string) {
  return apiRequest<LeadRead>(`/api/crm/leads/${leadId}/convert`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function searchCRM(q: string, types?: string, limit = 10) {
  return apiRequest<SearchResult[]>(`/api/crm/search${toQuery({ q, types, limit })}`);
}

export function createAccount(body: {
  name: string;
  owner_user_id?: string | null;
  primary_region_code?: string | null;
  default_currency_code?: string | null;
  external_reference?: string | null;
  legal_entity_ids?: string[];
  custom_fields?: Record<string, unknown>;
}) {
  return apiRequest<AccountRead>("/api/crm/accounts", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getAccount(accountId: string) {
  return apiRequest<AccountRead>(`/api/crm/accounts/${accountId}`);
}

export function patchAccount(accountId: string, body: Record<string, unknown>) {
  return apiRequest<AccountRead>(`/api/crm/accounts/${accountId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function listContacts(accountId: string, params: Record<string, string | number | boolean | null | undefined>) {
  return apiRequest<ContactRead[]>(`/api/crm/accounts/${accountId}/contacts${toQuery(params)}`);
}

export function createContact(accountId: string, body: Record<string, unknown>) {
  return apiRequest<ContactRead>(`/api/crm/accounts/${accountId}/contacts`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listOpportunities(params: Record<string, string | number | boolean | null | undefined>) {
  return apiRequest<OpportunityRead[]>(`/api/crm/opportunities${toQuery(params)}`);
}

export function getOpportunity(opportunityId: string) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}`);
}

export function patchOpportunity(opportunityId: string, body: Record<string, unknown>) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function changeOpportunityStage(
  opportunityId: string,
  body: OpportunityChangeStageRequest,
  idempotencyKey: string
) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}/change-stage`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function closeWon(opportunityId: string, body: OpportunityCloseWonRequest, idempotencyKey: string) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}/close-won`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function closeLost(opportunityId: string, body: OpportunityCloseLostRequest, idempotencyKey: string) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}/close-lost`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function reopenOpportunity(opportunityId: string, body: OpportunityReopenRequest) {
  return apiRequest<OpportunityRead>(`/api/crm/opportunities/${opportunityId}/reopen`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getOpportunityRevenue(opportunityId: string) {
  return apiRequest<OpportunityRevenueRead>(`/api/crm/opportunities/${opportunityId}/revenue`);
}

export function triggerRevenueHandoff(opportunityId: string, body: RevenueHandoffRequest, idempotencyKey: string) {
  return apiRequest<OpportunityRevenueRead>(`/api/crm/opportunities/${opportunityId}/revenue/handoff`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function getDefaultPipeline(params?: { selling_legal_entity_id?: string; include_inactive?: boolean }) {
  return apiRequest<PipelineRead>(`/api/crm/pipelines/default${toQuery(params ?? {})}`);
}

export function getPipeline(pipelineId: string, include_inactive?: boolean) {
  return apiRequest<PipelineRead>(`/api/crm/pipelines/${pipelineId}${toQuery({ include_inactive })}`);
}

export function getPipelineStages(pipelineId: string, include_inactive?: boolean) {
  return apiRequest<PipelineStageRead[]>(`/api/crm/pipelines/${pipelineId}/stages${toQuery({ include_inactive })}`);
}

export function listAuditLogs(params: AuditLogsListParams) {
  return apiRequest<AuditRead[]>(`/api/crm/audit${toQuery(params)}`);
}

export function listEntityAuditLogs(entityType: string, entityId: string, params?: { cursor?: string; limit?: number }) {
  return apiRequest<AuditRead[]>(`/api/crm/entities/${entityType}/${entityId}/audit${toQuery(params ?? {})}`);
}

export function listActivities(entityType: string, entityId: string) {
  return apiRequest<ActivityRead[]>(`/api/crm/entities/${entityType}/${entityId}/activities`);
}

export function createActivity(entityType: string, entityId: string, body: Record<string, unknown>) {
  return apiRequest<ActivityRead>(`/api/crm/entities/${entityType}/${entityId}/activities`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function completeActivity(activityId: string, rowVersion: number) {
  return apiRequest<ActivityRead>(`/api/crm/activities/${activityId}/complete`, {
    method: "POST",
    body: JSON.stringify({ row_version: rowVersion })
  });
}

export function listNotes(entityType: string, entityId: string) {
  return apiRequest<NoteRead[]>(`/api/crm/entities/${entityType}/${entityId}/notes`);
}

export function createNote(entityType: string, entityId: string, body: Record<string, unknown>) {
  return apiRequest<NoteRead>(`/api/crm/entities/${entityType}/${entityId}/notes`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listAttachments(entityType: string, entityId: string) {
  return apiRequest<AttachmentLinkRead[]>(`/api/crm/entities/${entityType}/${entityId}/attachments`);
}

export function createAttachment(entityType: string, entityId: string, body: Record<string, unknown>) {
  return apiRequest<AttachmentLinkRead>(`/api/crm/entities/${entityType}/${entityId}/attachments`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function exportAccounts(filters: Record<string, unknown>, sync = true) {
  return apiRequest<JobResponse>(`/api/crm/export/accounts${toQuery({ sync })}`, {
    method: "POST",
    body: JSON.stringify(filters)
  });
}

export function importAccounts(file: File, mapping: Record<string, unknown>, sync = true) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("mapping", JSON.stringify(mapping));
  return apiRequest<JobResponse>(`/api/crm/import/accounts${toQuery({ sync })}`, {
    method: "POST",
    body: formData
  });
}

export function getJob(jobId: string) {
  return apiRequest<JobResponse>(`/api/crm/jobs/${jobId}`);
}

export async function downloadJobArtifact(jobId: string, artifactType: string) {
  const requestCorrelationId = createCorrelationId();
  const response = await fetch(`${API_BASE_URL}/api/crm/jobs/${jobId}/download/${artifactType}`, {
    headers: {
      ...authHeaders(),
      "x-correlation-id": requestCorrelationId
    },
    cache: "no-store"
  });
  if (!response.ok) {
    const responseCorrelationId = response.headers.get("x-correlation-id") ?? requestCorrelationId;
    throw new ApiError(`Download failed (${response.status})`, response.status, undefined, responseCorrelationId, requestCorrelationId);
  }
  return response.blob();
}

export function getErrorToastMessage(error: unknown): ApiToastMessage {
  if (error instanceof ApiError) {
    return {
      message: error.message,
      correlationId: error.correlationId ?? error.envelope?.correlation_id ?? error.requestCorrelationId
    };
  }
  if (error instanceof Error) {
    return { message: error.message, correlationId: null };
  }
  return { message: "Something went wrong", correlationId: null };
}

export function getErrorMessage(error: unknown) {
  return getErrorToastMessage(error).message;
}

export interface FinanceReportParams {
  tenant_id: string;
  company_code?: string;
  start_date?: string;
  end_date?: string;
}

export function getFinanceArAging(params: { tenant_id: string; company_code?: string; as_of_date?: string }) {
  return apiRequest<FinanceARAgingReport>(`/reports/finance/ar-aging${toQuery(params)}`);
}

export function getFinanceTrialBalance(params: FinanceReportParams) {
  return apiRequest<FinanceTrialBalanceReport>(`/reports/finance/trial-balance${toQuery(params)}`);
}

export function getFinanceCashSummary(params: FinanceReportParams) {
  return apiRequest<FinanceCashSummaryReport>(`/reports/finance/cash-summary${toQuery(params)}`);
}

export function getFinanceRevenueSummary(params: FinanceReportParams) {
  return apiRequest<FinanceRevenueSummaryReport>(`/reports/finance/revenue-summary${toQuery(params)}`);
}

export function getFinanceReconciliation(params: FinanceReportParams) {
  return apiRequest<FinanceReconciliationReport>(`/reports/finance/reconciliation${toQuery(params)}`);
}

export function getFinanceInvoiceDrilldown(invoiceId: string) {
  return apiRequest<FinanceInvoiceDrilldown>(`/reports/finance/drilldowns/invoices/${invoiceId}`);
}

export function getFinancePaymentDrilldown(paymentId: string) {
  return apiRequest<FinancePaymentDrilldown>(`/reports/finance/drilldowns/payments/${paymentId}`);
}

export function getFinanceJournalDrilldown(entryId: string) {
  return apiRequest<FinanceJournalDrilldown>(`/reports/finance/drilldowns/journal-entries/${entryId}`);
}
