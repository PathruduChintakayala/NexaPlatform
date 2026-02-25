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

export interface FinanceAgingBucket {
  label: string;
  amount: string;
}

export interface FinanceAgingRow {
  invoice_id: string;
  invoice_number: string;
  due_date: string | null;
  days_overdue: number;
  amount_due: string;
  currency: string;
  status: string;
}

export interface FinanceARAgingReport {
  as_of_date: string;
  total_amount_due: string;
  buckets: FinanceAgingBucket[];
  rows: FinanceAgingRow[];
}

export interface FinanceTrialBalanceRow {
  account_id: string;
  account_code: string;
  account_name: string;
  debit_total: string;
  credit_total: string;
  net_balance: string;
}

export interface FinanceTrialBalanceReport {
  start_date: string | null;
  end_date: string | null;
  total_debits: string;
  total_credits: string;
  rows: FinanceTrialBalanceRow[];
}

export interface FinanceCashSummaryReport {
  start_date: string | null;
  end_date: string | null;
  currency: string | null;
  received_total: string;
  refunded_total: string;
  net_cash_total: string;
  payment_count: number;
  refund_count: number;
}

export interface FinanceRevenueSummaryReport {
  start_date: string | null;
  end_date: string | null;
  invoiced_total: string;
  credit_note_total: string;
  net_revenue_total: string;
  invoice_count: number;
  credit_note_count: number;
}

export interface FinanceInvoicePaymentMismatch {
  invoice_id: string;
  invoice_number: string;
  invoice_total: string;
  allocated_total: string;
  credit_note_total: string;
  expected_amount_due: string;
  actual_amount_due: string;
  delta: string;
}

export interface FinanceLedgerLinkMismatch {
  entity_type: string;
  entity_id: string;
  reference_number: string;
  ledger_journal_entry_id: string | null;
  issue: string;
}

export interface FinanceReconciliationReport {
  start_date: string | null;
  end_date: string | null;
  invoice_payment_mismatches: FinanceInvoicePaymentMismatch[];
  ledger_link_mismatches: FinanceLedgerLinkMismatch[];
}

export interface FinanceInvoiceDrilldown {
  invoice: Record<string, unknown>;
}

export interface FinancePaymentDrilldown {
  payment: Record<string, unknown>;
}

export interface FinanceJournalDrilldown {
  journal_entry: Record<string, unknown>;
}

export interface AdminRoleRead {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
}

export interface AdminRoleUpdate {
  name?: string;
  description?: string | null;
}

export interface AdminPermissionRead {
  id: string;
  resource: string;
  action: string;
  field: string | null;
  scope_type: string | null;
  scope_value: string | null;
  effect: string;
  description: string | null;
  created_at: string;
}

export interface AdminPermissionUpdate {
  resource?: string;
  action?: string;
  field?: string | null;
  scope_type?: string | null;
  scope_value?: string | null;
  effect?: "allow" | "deny";
  description?: string | null;
}

export interface AdminRolePermissionRead {
  role_id: string;
  role_name: string;
  permission_id: string;
  resource: string;
  action: string;
  field: string | null;
  scope_type: string | null;
  scope_value: string | null;
  effect: string;
  created_at: string;
}

export interface AdminUserRoleRead {
  user_id: string;
  role_id: string;
  role_name: string;
  created_at: string;
}

export interface BillingInvoiceRead {
  id: string;
  invoice_number: string;
  status: string;
  tenant_id: string;
  company_code: string;
  currency: string;
  amount_total: string;
  amount_due: string;
  issued_at: string | null;
  due_date: string | null;
}

export type BillingPeriod = "ONE_TIME" | "MONTHLY" | "QUARTERLY" | "ANNUAL";

export interface CatalogProductRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  sku: string;
  name: string;
  description: string | null;
  product_type?: string | null;
  default_currency: string;
  is_active: boolean;
  created_at: string;
}

export interface CatalogProductCreate {
  tenant_id: string;
  company_code: string;
  region_code?: string | null;
  sku: string;
  name: string;
  description?: string | null;
  product_type?: string | null;
  default_currency: string;
  is_active?: boolean;
}

export interface CatalogPricebookRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  name: string;
  currency: string;
  is_default: boolean;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CatalogPricebookCreate {
  tenant_id: string;
  company_code: string;
  region_code?: string | null;
  name: string;
  currency: string;
  is_default?: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
  is_active?: boolean;
}

export interface CatalogPricebookItemRead {
  id: string;
  pricebook_id: string;
  product_id: string;
  billing_period: BillingPeriod;
  currency: string;
  unit_price: string;
  is_active: boolean;
  created_at: string;
}

export interface CatalogPricebookItemUpsert {
  pricebook_id: string;
  product_id: string;
  billing_period: BillingPeriod;
  currency: string;
  unit_price: string;
  usage_unit?: string | null;
  is_active?: boolean;
}

export interface CatalogPriceRead {
  tenant_id: string;
  company_code: string;
  sku: string;
  product_id: string;
  pricebook_id: string;
  currency: string;
  billing_period: BillingPeriod;
  unit_price: string;
  valid_from: string | null;
  valid_to: string | null;
}

export interface RevenueQuoteLineRead {
  id: string;
  quote_id: string;
  product_id: string;
  pricebook_item_id: string;
  description: string | null;
  quantity: string;
  unit_price: string;
  line_total: string;
}

export interface RevenueQuoteRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  quote_number: string;
  account_id: string | null;
  currency: string;
  status: string;
  valid_until: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  lines: RevenueQuoteLineRead[];
}

export interface RevenueQuoteCreate {
  tenant_id: string;
  company_code: string;
  region_code?: string | null;
  currency: string;
  valid_until?: string | null;
}

export interface RevenueQuoteLineCreate {
  product_id: string;
  pricebook_item_id: string;
  description?: string | null;
  quantity: string;
}

export interface RevenueOrderLineRead {
  id: string;
  order_id: string;
  product_id: string;
  pricebook_item_id: string;
  quantity: string;
  unit_price: string;
  line_total: string;
  service_start: string | null;
  service_end: string | null;
}

export interface RevenueOrderRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  order_number: string;
  quote_id: string | null;
  currency: string;
  status: string;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  lines: RevenueOrderLineRead[];
}

export interface RevenueContractRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  contract_number: string;
  order_id: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
}

export interface OpsPlanItemRead {
  id: string;
  plan_id: string;
  product_id: string;
  pricebook_item_id: string;
  quantity_default: string;
  unit_price_snapshot: string;
  created_at: string;
}

export interface OpsPlanRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  name: string;
  code: string;
  currency: string;
  status: string;
  billing_period: string;
  default_pricebook_id: string | null;
  created_at: string;
  items: OpsPlanItemRead[];
}

export interface OpsSubscriptionItemRead {
  id: string;
  subscription_id: string;
  product_id: string;
  pricebook_item_id: string;
  quantity: string;
  unit_price_snapshot: string;
  created_at: string;
}

export interface OpsSubscriptionRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  subscription_number: string;
  contract_id: string;
  account_id: string | null;
  currency: string;
  status: string;
  start_date: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  auto_renew: boolean;
  renewal_term_count: number;
  renewal_billing_period: string;
  created_at: string;
  updated_at: string;
  items: OpsSubscriptionItemRead[];
}

export interface OpsSubscriptionChangeRead {
  id: string;
  subscription_id: string;
  change_type: string;
  effective_date: string;
  payload_json: Record<string, unknown> | null;
  created_at: string;
}

export interface OpsInvoiceLineRead {
  id: string;
  invoice_id: string;
  product_id: string | null;
  description: string | null;
  quantity: string;
  unit_price_snapshot: string;
  line_total: string;
  source_type: string;
  source_id: string | null;
}

export interface OpsInvoiceRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  invoice_number: string;
  account_id: string | null;
  subscription_id: string | null;
  order_id: string | null;
  currency: string;
  status: string;
  issue_date: string | null;
  due_date: string | null;
  period_start: string | null;
  period_end: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
  amount_due: string;
  ledger_journal_entry_id: string | null;
  created_at: string;
  updated_at: string;
  lines: OpsInvoiceLineRead[];
}

export interface OpsCreditNoteLineRead {
  id: string;
  credit_note_id: string;
  invoice_line_id: string | null;
  description: string | null;
  quantity: string;
  unit_price_snapshot: string;
  line_total: string;
}

export interface OpsCreditNoteRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  credit_note_number: string;
  invoice_id: string;
  currency: string;
  status: string;
  issue_date: string | null;
  subtotal: string;
  tax_total: string;
  total: string;
  ledger_journal_entry_id: string | null;
  created_at: string;
  lines: OpsCreditNoteLineRead[];
}

export interface OpsPaymentAllocationRead {
  id: string;
  payment_id: string;
  invoice_id: string;
  amount_allocated: string;
  created_at: string;
}

export interface OpsRefundRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  payment_id: string;
  amount: string;
  reason: string;
  status: string;
  ledger_journal_entry_id: string | null;
  created_at: string;
}

export interface OpsPaymentRead {
  id: string;
  tenant_id: string;
  company_code: string;
  region_code: string | null;
  payment_number: string;
  account_id: string | null;
  currency: string;
  amount: string;
  status: string;
  payment_method: string;
  received_at: string | null;
  ledger_journal_entry_id: string | null;
  created_at: string;
  allocations: OpsPaymentAllocationRead[];
  refunds: OpsRefundRead[];
}

export interface OpsJournalLineRead {
  id: string;
  journal_entry_id: string;
  account_id: string;
  debit_amount: string;
  credit_amount: string;
  currency: string;
  fx_rate_to_company_base: string;
  amount_company_base: string;
  memo: string | null;
  dimensions_json: Record<string, unknown> | null;
  created_at: string;
}

export interface OpsJournalEntryRead {
  id: string;
  tenant_id: string;
  company_code: string;
  entry_date: string;
  description: string;
  source_module: string;
  source_type: string;
  source_id: string;
  posting_status: string;
  created_by: string;
  created_at: string;
  lines: OpsJournalLineRead[];
}
