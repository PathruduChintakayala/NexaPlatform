import type { OpsPaymentAllocationRead, OpsPaymentRead, OpsRefundRead } from "../types";
import { apiRequest, toQuery } from "./core";

export function listPayments(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<OpsPaymentRead[]>(`/payments${toQuery(params)}`);
}

export function getPayment(paymentId: string) {
  return apiRequest<OpsPaymentRead>(`/payments/${paymentId}`);
}

export function createPayment(body: {
  tenant_id: string;
  company_code: string;
  region_code?: string | null;
  account_id?: string | null;
  currency: string;
  amount: string;
  payment_method: "MANUAL" | "BANK_TRANSFER" | "CARD";
  received_at?: string | null;
  fx_rate_to_company_base?: string;
  allocations?: Array<{ invoice_id: string; amount: string }>;
}) {
  return apiRequest<OpsPaymentRead>("/payments", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function allocatePayment(paymentId: string, body: { invoice_id: string; amount: string }) {
  return apiRequest<OpsPaymentRead>(`/payments/${paymentId}/allocate`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function refundPayment(
  paymentId: string,
  body: { amount: string; reason: string; fx_rate_to_company_base?: string }
) {
  return apiRequest<OpsRefundRead>(`/payments/${paymentId}/refund`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listPaymentAllocations(paymentId: string) {
  return apiRequest<OpsPaymentAllocationRead[]>(`/payments/${paymentId}/allocations`);
}
