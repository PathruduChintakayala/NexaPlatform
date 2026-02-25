import { apiRequest, toQuery } from "./core";
import type {
  CatalogPricebookCreate,
  CatalogPricebookItemRead,
  CatalogPricebookItemUpsert,
  CatalogPricebookRead,
  CatalogPriceRead,
  CatalogProductCreate,
  CatalogProductRead
} from "../types";

export function listCatalogProducts(params: { tenant_id: string; company_code?: string }) {
  return apiRequest<CatalogProductRead[]>(`/catalog/products${toQuery(params)}`);
}

export function createCatalogProduct(body: CatalogProductCreate) {
  return apiRequest<CatalogProductRead>("/catalog/products", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function listCatalogPricebooks(params: { tenant_id: string; company_code?: string; currency?: string }) {
  return apiRequest<CatalogPricebookRead[]>(`/catalog/pricebooks${toQuery(params)}`);
}

export function createCatalogPricebook(body: CatalogPricebookCreate) {
  return apiRequest<CatalogPricebookRead>("/catalog/pricebooks", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function upsertCatalogPricebookItem(body: CatalogPricebookItemUpsert) {
  return apiRequest<CatalogPricebookItemRead>("/catalog/pricebook-items", {
    method: "PUT",
    body: JSON.stringify(body)
  });
}

export function getCatalogPrice(params: {
  tenant_id: string;
  company_code: string;
  sku: string;
  currency: string;
  billing_period: string;
  at_date?: string;
}) {
  return apiRequest<CatalogPriceRead>(`/catalog/price${toQuery(params)}`);
}
