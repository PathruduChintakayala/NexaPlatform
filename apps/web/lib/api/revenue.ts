import { apiRequest, toQuery } from "./core";
import type {
  RevenueContractRead,
  RevenueOrderRead,
  RevenueQuoteCreate,
  RevenueQuoteLineCreate,
  RevenueQuoteLineRead,
  RevenueQuoteRead
} from "../types";

export function listRevenueQuotes(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<RevenueQuoteRead[]>(`/revenue/quotes${toQuery(params)}`);
}

export function createRevenueQuote(body: RevenueQuoteCreate) {
  return apiRequest<RevenueQuoteRead>("/revenue/quotes", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getRevenueQuote(quoteId: string) {
  return apiRequest<RevenueQuoteRead>(`/revenue/quotes/${quoteId}`);
}

export function addRevenueQuoteLine(quoteId: string, body: RevenueQuoteLineCreate) {
  return apiRequest<RevenueQuoteLineRead>(`/revenue/quotes/${quoteId}/lines`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function sendRevenueQuote(quoteId: string) {
  return apiRequest<RevenueQuoteRead>(`/revenue/quotes/${quoteId}/send`, {
    method: "POST"
  });
}

export function acceptRevenueQuote(quoteId: string) {
  return apiRequest<RevenueQuoteRead>(`/revenue/quotes/${quoteId}/accept`, {
    method: "POST"
  });
}

export function createRevenueOrderFromQuote(quoteId: string) {
  return apiRequest<RevenueOrderRead>(`/revenue/quotes/${quoteId}/create-order`, {
    method: "POST"
  });
}

export function listRevenueOrders(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<RevenueOrderRead[]>(`/revenue/orders${toQuery(params)}`);
}

export function getRevenueOrder(orderId: string) {
  return apiRequest<RevenueOrderRead>(`/revenue/orders/${orderId}`);
}

export function confirmRevenueOrder(orderId: string) {
  return apiRequest<RevenueOrderRead>(`/revenue/orders/${orderId}/confirm`, {
    method: "POST"
  });
}

export function createRevenueContractFromOrder(orderId: string) {
  return apiRequest<RevenueContractRead>(`/revenue/orders/${orderId}/create-contract`, {
    method: "POST"
  });
}

export function listRevenueContracts(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<RevenueContractRead[]>(`/revenue/contracts${toQuery(params)}`);
}

export function getRevenueContract(contractId: string) {
  return apiRequest<RevenueContractRead>(`/revenue/contracts/${contractId}`);
}
