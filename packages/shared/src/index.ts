export type ModuleKey =
  | "admin"
  | "crm"
  | "catalog"
  | "revenue"
  | "billing"
  | "payments"
  | "support";

export type RegionCode = "global" | "us" | "eu" | "apac";

export type CurrencyCode = "USD" | "EUR" | "GBP";

export interface RequestScope {
  legalEntity: string;
  region: RegionCode;
  currency: CurrencyCode;
}

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}
