import type {
  FinanceARAgingReport,
  FinanceCashSummaryReport,
  FinanceInvoiceDrilldown,
  FinanceJournalDrilldown,
  FinancePaymentDrilldown,
  FinanceReconciliationReport,
  FinanceRevenueSummaryReport,
  FinanceTrialBalanceReport
} from "../types";
import { apiRequest, toQuery } from "./core";

export interface FinanceWindowParams {
  tenant_id: string;
  company_code?: string;
  start_date?: string;
  end_date?: string;
}

export function getFinanceARAging(params: FinanceWindowParams & { as_of_date?: string }) {
  return apiRequest<FinanceARAgingReport>(`/reports/finance/ar-aging${toQuery(params)}`);
}

export function getFinanceTrialBalance(params: FinanceWindowParams) {
  return apiRequest<FinanceTrialBalanceReport>(`/reports/finance/trial-balance${toQuery(params)}`);
}

export function getFinanceCashSummary(params: FinanceWindowParams) {
  return apiRequest<FinanceCashSummaryReport>(`/reports/finance/cash-summary${toQuery(params)}`);
}

export function getFinanceRevenueSummary(params: FinanceWindowParams) {
  return apiRequest<FinanceRevenueSummaryReport>(`/reports/finance/revenue-summary${toQuery(params)}`);
}

export function getFinanceReconciliation(params: FinanceWindowParams) {
  return apiRequest<FinanceReconciliationReport>(`/reports/finance/reconciliation${toQuery(params)}`);
}

export function getInvoiceDrilldown(invoiceId: string) {
  return apiRequest<FinanceInvoiceDrilldown>(`/reports/finance/drilldowns/invoices/${invoiceId}`);
}

export function getPaymentDrilldown(paymentId: string) {
  return apiRequest<FinancePaymentDrilldown>(`/reports/finance/drilldowns/payments/${paymentId}`);
}

export function getJournalDrilldown(entryId: string) {
  return apiRequest<FinanceJournalDrilldown>(`/reports/finance/drilldowns/journal/${entryId}`);
}
