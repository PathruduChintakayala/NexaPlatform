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
    ["customFieldDefinitions", entityType, legalEntityId ?? "__global__"] as const,
  finance: {
    arAging: (params: Record<string, unknown>) => ["finance", "arAging", params] as const,
    trialBalance: (params: Record<string, unknown>) => ["finance", "trialBalance", params] as const,
    cashSummary: (params: Record<string, unknown>) => ["finance", "cashSummary", params] as const,
    revenueSummary: (params: Record<string, unknown>) => ["finance", "revenueSummary", params] as const,
    reconciliation: (params: Record<string, unknown>) => ["finance", "reconciliation", params] as const,
    invoiceDrilldown: (invoiceId: string) => ["finance", "invoice", invoiceId] as const,
    paymentDrilldown: (paymentId: string) => ["finance", "payment", paymentId] as const,
    journalDrilldown: (entryId: string) => ["finance", "journal", entryId] as const
  },
  admin: {
    roles: () => ["admin", "roles"] as const,
    permissions: () => ["admin", "permissions"] as const,
    rolePermissions: (roleId: string) => ["admin", "rolePermissions", roleId] as const,
    userRoleAssignments: () => ["admin", "userRoleAssignments"] as const,
    userRoles: (userId: string) => ["admin", "userRoles", userId] as const
  },
  sales: {
    products: (params: Record<string, unknown>) => ["sales", "products", params] as const,
    pricebooks: (params: Record<string, unknown>) => ["sales", "pricebooks", params] as const,
    pricebookItems: (pricebookId: string) => ["sales", "pricebookItems", pricebookId] as const,
    priceLookup: (params: Record<string, unknown>) => ["sales", "priceLookup", params] as const,
    quotes: (params: Record<string, unknown>) => ["sales", "quotes", params] as const,
    quote: (quoteId: string) => ["sales", "quote", quoteId] as const,
    orders: (params: Record<string, unknown>) => ["sales", "orders", params] as const,
    order: (orderId: string) => ["sales", "order", orderId] as const,
    contracts: (params: Record<string, unknown>) => ["sales", "contracts", params] as const,
    contract: (contractId: string) => ["sales", "contract", contractId] as const
  },
  ops: {
    plans: (params: Record<string, unknown>) => ["ops", "plans", params] as const,
    plan: (planId: string) => ["ops", "plan", planId] as const,
    subscriptions: (params: Record<string, unknown>) => ["ops", "subscriptions", params] as const,
    subscription: (subscriptionId: string) => ["ops", "subscription", subscriptionId] as const,
    subscriptionChanges: (subscriptionId: string) => ["ops", "subscriptionChanges", subscriptionId] as const,
    invoices: (params: Record<string, unknown>) => ["ops", "invoices", params] as const,
    invoice: (invoiceId: string) => ["ops", "invoice", invoiceId] as const,
    invoiceLines: (invoiceId: string) => ["ops", "invoiceLines", invoiceId] as const,
    creditNotes: (params: Record<string, unknown>) => ["ops", "creditNotes", params] as const,
    paymentList: (params: Record<string, unknown>) => ["ops", "payments", params] as const,
    payment: (paymentId: string) => ["ops", "payment", paymentId] as const,
    paymentAllocations: (paymentId: string) => ["ops", "paymentAllocations", paymentId] as const,
    journalEntries: (params: Record<string, unknown>) => ["ops", "journalEntries", params] as const,
    journalEntry: (entryId: string) => ["ops", "journalEntry", entryId] as const
  }
};
