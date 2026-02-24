export const queryKeys = {
  accounts: (params: Record<string, unknown>) => ["accounts", params] as const,
  account: (accountId: string) => ["account", accountId] as const,
  contacts: (accountId: string, params: Record<string, unknown>) => ["contacts", accountId, params] as const,
  opportunities: (params: Record<string, unknown>) => ["opportunities", params] as const,
  opportunity: (opportunityId: string) => ["opportunity", opportunityId] as const,
  opportunityRevenue: (opportunityId: string) => ["opportunityRevenue", opportunityId] as const,
  pipelineDefault: (sellingLegalEntityId?: string) => ["pipelineDefault", sellingLegalEntityId ?? "__current__"] as const,
  pipelineStages: (pipelineId: string) => ["pipelineStages", pipelineId] as const,
  leads: (params: Record<string, unknown>) => ["leads", params] as const,
  lead: (leadId: string) => ["lead", leadId] as const,
  crmSearch: (q: string, types?: string, limit?: number) => ["crmSearch", q, types ?? "", limit ?? 10] as const,
  auditLogs: (params: Record<string, unknown>) => ["auditLogs", params] as const,
  entityAuditLogs: (entityType: string, entityId: string, params: Record<string, unknown>) =>
    ["entityAuditLogs", entityType, entityId, params] as const,
  activities: (entityType: string, entityId: string) => ["activities", entityType, entityId] as const,
  notes: (entityType: string, entityId: string) => ["notes", entityType, entityId] as const,
  attachments: (entityType: string, entityId: string) => ["attachments", entityType, entityId] as const,
  job: (jobId: string) => ["job", jobId] as const,
  workflows: {
    list: (params: Record<string, unknown>) => ["workflows", "list", params] as const,
    detail: (ruleId: string) => ["workflows", "detail", ruleId] as const,
    executions: (params: Record<string, unknown>) => ["workflows", "executions", params] as const,
    execution: (jobId: string) => ["workflows", "execution", jobId] as const,
    executionsDetail: (jobId: string) => ["workflows", "executions", "detail", jobId] as const
  },
  workflowsList: (params: Record<string, unknown>) => ["workflows", "list", params] as const,
  workflowDetail: (ruleId: string) => ["workflows", "detail", ruleId] as const,
  workflowExecutions: (params: Record<string, unknown>) => ["workflows", "executions", params] as const,
  workflowExecution: (jobId: string) => ["workflows", "execution", jobId] as const,
  customFieldDefinitions: (entityType: string, legalEntityId?: string) =>
    ["customFieldDefinitions", entityType, legalEntityId ?? "__global__"] as const
};
