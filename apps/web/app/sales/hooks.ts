"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../../lib/api/core";
import {
  getCatalogPrice,
  listCatalogPricebooks,
  listCatalogProducts
} from "../../lib/api/catalog";
import {
  getRevenueContract,
  getRevenueOrder,
  getRevenueQuote,
  listRevenueContracts,
  listRevenueOrders,
  listRevenueQuotes
} from "../../lib/api/revenue";
import { queryKeys } from "../../lib/queryKeys";

export function safeText(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
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

export function useCatalogProducts(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.sales.products({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listCatalogProducts({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useCatalogPricebooks(tenantId: string, companyCode: string, currency?: string) {
  return useQuery({
    queryKey: queryKeys.sales.pricebooks({ tenant_id: tenantId, company_code: companyCode, currency: currency ?? "" }),
    queryFn: () => listCatalogPricebooks({ tenant_id: tenantId, company_code: companyCode, currency }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useCatalogPriceLookup(params: {
  tenant_id: string;
  company_code: string;
  sku: string;
  currency: string;
  billing_period: string;
}) {
  return useQuery({
    queryKey: queryKeys.sales.priceLookup(params),
    queryFn: () => getCatalogPrice(params),
    enabled: Boolean(params.tenant_id && params.company_code && params.sku && params.currency && params.billing_period)
  });
}

export function useRevenueQuotes(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.sales.quotes({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listRevenueQuotes({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useRevenueQuote(quoteId: string) {
  return useQuery({
    queryKey: queryKeys.sales.quote(quoteId),
    queryFn: () => getRevenueQuote(quoteId),
    enabled: Boolean(quoteId)
  });
}

export function useRevenueOrders(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.sales.orders({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listRevenueOrders({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useRevenueOrder(orderId: string) {
  return useQuery({
    queryKey: queryKeys.sales.order(orderId),
    queryFn: () => getRevenueOrder(orderId),
    enabled: Boolean(orderId)
  });
}

export function useRevenueContracts(tenantId: string, companyCode: string) {
  return useQuery({
    queryKey: queryKeys.sales.contracts({ tenant_id: tenantId, company_code: companyCode }),
    queryFn: () => listRevenueContracts({ tenant_id: tenantId, company_code: companyCode }),
    enabled: Boolean(tenantId && companyCode)
  });
}

export function useRevenueContract(contractId: string) {
  return useQuery({
    queryKey: queryKeys.sales.contract(contractId),
    queryFn: () => getRevenueContract(contractId),
    enabled: Boolean(contractId)
  });
}
