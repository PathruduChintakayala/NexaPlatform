import type { OpsCreditNoteRead, OpsInvoiceLineRead, OpsInvoiceRead } from "../types";
import { apiRequest, toQuery } from "./core";

export function listBillingInvoices(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<OpsInvoiceRead[]>(`/billing/invoices${toQuery(params)}`);
}

export function issueInvoice(invoiceId: string) {
  return apiRequest<OpsInvoiceRead>(`/billing/invoices/${invoiceId}/issue`, {
    method: "POST"
  });
}

export function getBillingInvoice(invoiceId: string) {
  return apiRequest<OpsInvoiceRead>(`/billing/invoices/${invoiceId}`);
}

export function listBillingInvoiceLines(invoiceId: string) {
  return apiRequest<OpsInvoiceLineRead[]>(`/billing/invoices/${invoiceId}/lines`);
}

export function generateInvoiceFromSubscription(subscriptionId: string, params: { period_start: string; period_end: string }) {
  return apiRequest<OpsInvoiceRead>(`/billing/invoices/from-subscription/${subscriptionId}${toQuery(params)}`, {
    method: "POST"
  });
}

export function voidInvoice(invoiceId: string, reason: string) {
  return apiRequest<OpsInvoiceRead>(`/billing/invoices/${invoiceId}/void${toQuery({ reason })}`, {
    method: "POST"
  });
}

export function markInvoicePaid(invoiceId: string, body: { amount: string; paid_at?: string | null }) {
  return apiRequest<OpsInvoiceRead>(`/billing/invoices/${invoiceId}/mark-paid`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function createCreditNote(
  invoiceId: string,
  body: {
    issue_date?: string | null;
    tax_total?: string;
    lines: Array<{
      invoice_line_id?: string | null;
      description?: string | null;
      quantity: string;
      unit_price_snapshot: string;
    }>;
  }
) {
  return apiRequest<OpsCreditNoteRead>(`/billing/invoices/${invoiceId}/credit-notes`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listCreditNotes(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<OpsCreditNoteRead[]>(`/billing/credit-notes${toQuery(params)}`);
}
