import type { OpsPlanRead, OpsSubscriptionChangeRead, OpsSubscriptionRead } from "../types";
import { apiRequest, toQuery } from "./core";

export function listSubscriptions(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<OpsSubscriptionRead[]>(`/subscriptions${toQuery(params)}`);
}

export function listPlans(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<OpsPlanRead[]>(`/subscriptions/plans${toQuery(params)}`);
}

export function getPlan(planId: string) {
  return apiRequest<OpsPlanRead>(`/subscriptions/plans/${planId}`);
}

export function getSubscription(subscriptionId: string) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}`);
}

export function listSubscriptionChanges(subscriptionId: string) {
  return apiRequest<OpsSubscriptionChangeRead[]>(`/subscriptions/${subscriptionId}/changes`);
}

export function createSubscriptionFromContract(
  contractId: string,
  body: {
    plan_id?: string | null;
    account_id?: string | null;
    auto_renew?: boolean;
    renewal_term_count?: number;
    renewal_billing_period?: "MONTHLY" | "YEARLY" | null;
    start_date?: string | null;
  }
) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/from-contract/${contractId}`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function activateSubscription(subscriptionId: string, body: { start_date?: string | null }) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/activate`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function suspendSubscription(subscriptionId: string, body: { effective_date: string }) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/suspend`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function resumeSubscription(subscriptionId: string, body: { effective_date: string }) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/resume`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function cancelSubscription(subscriptionId: string, body: { effective_date: string; reason?: string | null }) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/cancel`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function renewSubscription(subscriptionId: string) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/renew`, {
    method: "POST"
  });
}

export function changeSubscriptionQuantity(
  subscriptionId: string,
  productId: string,
  body: { new_qty: string; effective_date: string }
) {
  return apiRequest<OpsSubscriptionRead>(`/subscriptions/${subscriptionId}/items/${productId}/quantity`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}
