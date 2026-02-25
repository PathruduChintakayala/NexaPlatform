"use client";

import { useQuery } from "@tanstack/react-query";

import { listBillingInvoiceLines, listBillingInvoices, listCreditNotes, getBillingInvoice } from "../../lib/api/billing";
import { ApiError } from "../../lib/api/core";
import { getJournalEntry, listJournalEntries } from "../../lib/api/ledger";
import { getPayment, listPaymentAllocations, listPayments } from "../../lib/api/payments";
import {
  getPlan,
  getSubscription,
  listPlans,
  listSubscriptionChanges,
  listSubscriptions
} from "../../lib/api/subscription";
import { queryKeys } from "../../lib/queryKeys";

export function safeText(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return "—";
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const correlationId = error.correlationId ? ` (Correlation ID: ${error.correlationId})` : "";
    return `${error.message}${correlationId}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed";
}

export function useOpsPlans(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.ops.plans({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listPlans({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useOpsPlan(planId: string) {
  return useQuery({
    queryKey: queryKeys.ops.plan(planId),
    queryFn: () => getPlan(planId),
    enabled: Boolean(planId)
  });
}

export function useOpsSubscriptions(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.ops.subscriptions({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listSubscriptions({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useOpsSubscription(subscriptionId: string) {
  return useQuery({
    queryKey: queryKeys.ops.subscription(subscriptionId),
    queryFn: () => getSubscription(subscriptionId),
    enabled: Boolean(subscriptionId)
  });
}

export function useOpsSubscriptionChanges(subscriptionId: string) {
  return useQuery({
    queryKey: queryKeys.ops.subscriptionChanges(subscriptionId),
    queryFn: () => listSubscriptionChanges(subscriptionId),
    enabled: Boolean(subscriptionId)
  });
}

export function useOpsInvoices(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.ops.invoices({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listBillingInvoices({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useOpsInvoice(invoiceId: string) {
  return useQuery({
    queryKey: queryKeys.ops.invoice(invoiceId),
    queryFn: () => getBillingInvoice(invoiceId),
    enabled: Boolean(invoiceId)
  });
}

export function useOpsInvoiceLines(invoiceId: string) {
  return useQuery({
    queryKey: queryKeys.ops.invoiceLines(invoiceId),
    queryFn: () => listBillingInvoiceLines(invoiceId),
    enabled: Boolean(invoiceId)
  });
}

export function useOpsCreditNotes(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.ops.creditNotes({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listCreditNotes({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useOpsPayments(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.ops.paymentList({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listPayments({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useOpsPayment(paymentId: string) {
  return useQuery({
    queryKey: queryKeys.ops.payment(paymentId),
    queryFn: () => getPayment(paymentId),
    enabled: Boolean(paymentId)
  });
}

export function useOpsPaymentAllocations(paymentId: string) {
  return useQuery({
    queryKey: queryKeys.ops.paymentAllocations(paymentId),
    queryFn: () => listPaymentAllocations(paymentId),
    enabled: Boolean(paymentId)
  });
}

export function useOpsJournalEntries(params: {
  tenant_id: string;
  company_code: string;
  start_date?: string;
  end_date?: string;
}) {
  return useQuery({
    queryKey: queryKeys.ops.journalEntries(params),
    queryFn: () => listJournalEntries(params),
    enabled: Boolean(params.tenant_id && params.company_code)
  });
}

export function useOpsJournalEntry(entryId: string) {
  return useQuery({
    queryKey: queryKeys.ops.journalEntry(entryId),
    queryFn: () => getJournalEntry(entryId),
    enabled: Boolean(entryId)
  });
}
