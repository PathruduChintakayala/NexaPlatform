import React from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import OpsInvoicesPage from "./invoices/page";
import OpsInvoiceDetailPage from "./invoices/[id]/page";
import OpsJournalEntriesPage from "./journal-entries/page";
import OpsJournalEntryDetailPage from "./journal-entries/[id]/page";
import OpsPaymentsPage from "./payments/page";
import OpsPaymentDetailPage from "./payments/[id]/page";
import OpsPlansPage from "./plans/page";
import OpsPlanDetailPage from "./plans/[id]/page";
import OpsSubscriptionsPage from "./subscriptions/page";
import OpsSubscriptionDetailPage from "./subscriptions/[id]/page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "./test-utils";

const apiBase = "http://localhost:8000";

const plan = {
  id: "plan-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  name: "Starter",
  code: "START",
  currency: "USD",
  status: "ACTIVE",
  billing_period: "MONTHLY",
  default_pricebook_id: null,
  created_at: "2026-02-26T00:00:00Z",
  items: [
    {
      id: "plan-item-1",
      plan_id: "plan-1",
      product_id: "product-1",
      pricebook_item_id: "pbi-1",
      quantity_default: "1",
      unit_price_snapshot: "10.00",
      created_at: "2026-02-26T00:00:00Z"
    }
  ]
};

const subscription = {
  id: "sub-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  subscription_number: "SUB-1001",
  contract_id: "contract-1",
  account_id: "account-1",
  currency: "USD",
  status: "ACTIVE",
  start_date: "2026-02-01",
  current_period_start: "2026-02-01",
  current_period_end: "2026-02-29",
  auto_renew: true,
  renewal_term_count: 1,
  renewal_billing_period: "MONTHLY",
  created_at: "2026-02-01T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
  items: [
    {
      id: "sub-item-1",
      subscription_id: "sub-1",
      product_id: "product-1",
      pricebook_item_id: "pbi-1",
      quantity: "2",
      unit_price_snapshot: "10.00",
      created_at: "2026-02-01T00:00:00Z"
    }
  ]
};

const invoice = {
  id: "invoice-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  invoice_number: "INV-1001",
  account_id: "account-1",
  subscription_id: "sub-1",
  order_id: null,
  currency: "USD",
  status: "DRAFT",
  issue_date: null,
  due_date: "2026-03-05",
  period_start: "2026-02-01",
  period_end: "2026-02-29",
  subtotal: "20.00",
  discount_total: "0.00",
  tax_total: "0.00",
  total: "20.00",
  amount_due: "20.00",
  ledger_journal_entry_id: null,
  created_at: "2026-02-26T00:00:00Z",
  updated_at: "2026-02-26T00:00:00Z",
  lines: [
    {
      id: "line-1",
      invoice_id: "invoice-1",
      product_id: "product-1",
      description: "Line",
      quantity: "2",
      unit_price_snapshot: "10.00",
      line_total: "20.00",
      source_type: "SUBSCRIPTION",
      source_id: "sub-1"
    }
  ]
};

const creditNote = {
  id: "cn-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  credit_note_number: "CN-1001",
  invoice_id: "invoice-1",
  currency: "USD",
  status: "APPLIED",
  issue_date: "2026-02-27",
  subtotal: "5.00",
  tax_total: "0.00",
  total: "5.00",
  ledger_journal_entry_id: null,
  created_at: "2026-02-27T00:00:00Z",
  lines: []
};

const payment = {
  id: "payment-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  payment_number: "PAY-1001",
  account_id: "account-1",
  currency: "USD",
  amount: "20.00",
  status: "CONFIRMED",
  payment_method: "MANUAL",
  received_at: "2026-02-27T00:00:00Z",
  ledger_journal_entry_id: null,
  created_at: "2026-02-27T00:00:00Z",
  allocations: [
    { id: "alloc-1", payment_id: "payment-1", invoice_id: "invoice-1", amount_allocated: "20.00", created_at: "2026-02-27T00:00:00Z" }
  ],
  refunds: []
};

const journalEntry = {
  id: "je-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  entry_date: "2026-02-27",
  description: "Invoice posting",
  source_module: "billing",
  source_type: "invoice",
  source_id: "invoice-1",
  posting_status: "POSTED",
  created_by: "ops.user",
  created_at: "2026-02-27T00:00:00Z",
  lines: [
    {
      id: "je-line-1",
      journal_entry_id: "je-1",
      account_id: "acct-1",
      debit_amount: "20.00",
      credit_amount: "0.00",
      currency: "USD",
      fx_rate_to_company_base: "1",
      amount_company_base: "20.00",
      memo: null,
      dimensions_json: null,
      created_at: "2026-02-27T00:00:00Z"
    }
  ]
};

const server = setupServer(
  http.get(`${apiBase}/subscriptions/plans`, () => HttpResponse.json([plan])),
  http.get(`${apiBase}/subscriptions/plans/:planId`, () => HttpResponse.json(plan)),
  http.get(`${apiBase}/subscriptions`, () => HttpResponse.json([subscription])),
  http.get(`${apiBase}/subscriptions/:subscriptionId`, () => HttpResponse.json(subscription)),
  http.get(`${apiBase}/subscriptions/:subscriptionId/changes`, () =>
    HttpResponse.json([
      {
        id: "chg-1",
        subscription_id: "sub-1",
        change_type: "ACTIVATE",
        effective_date: "2026-02-01",
        payload_json: null,
        created_at: "2026-02-01T00:00:00Z"
      }
    ])
  ),
  http.get(`${apiBase}/billing/invoices`, () => HttpResponse.json([invoice])),
  http.get(`${apiBase}/billing/invoices/:invoiceId`, () => HttpResponse.json(invoice)),
  http.get(`${apiBase}/billing/invoices/:invoiceId/lines`, () => HttpResponse.json(invoice.lines)),
  http.get(`${apiBase}/billing/credit-notes`, () => HttpResponse.json([creditNote])),
  http.get(`${apiBase}/payments`, () => HttpResponse.json([payment])),
  http.get(`${apiBase}/payments/:paymentId`, () => HttpResponse.json(payment)),
  http.get(`${apiBase}/payments/:paymentId/allocations`, () => HttpResponse.json(payment.allocations)),
  http.get(`${apiBase}/ledger/journal-entries`, () => HttpResponse.json([journalEntry])),
  http.get(`${apiBase}/ledger/journal-entries/:entryId`, () => HttpResponse.json(journalEntry))
);

describe("Ops route smoke", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());

  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["ops"]));
  });

  it("renders plans routes", async () => {
    renderWithQueryClient(React.createElement(OpsPlansPage));
    expect(await screen.findByText("Ops · Plans")).toBeDefined();

    renderWithQueryClient(React.createElement(OpsPlanDetailPage, { params: { id: "plan-1" } }));
    expect(await screen.findByText("Ops · Plan Detail")).toBeDefined();
  });

  it("renders subscriptions routes", async () => {
    renderWithQueryClient(React.createElement(OpsSubscriptionsPage));
    expect(await screen.findByText("Ops · Subscriptions")).toBeDefined();

    renderWithQueryClient(React.createElement(OpsSubscriptionDetailPage, { params: { id: "sub-1" } }));
    expect(await screen.findByText("Ops · Subscription Detail")).toBeDefined();
  });

  it("renders invoices routes", async () => {
    renderWithQueryClient(React.createElement(OpsInvoicesPage));
    expect(await screen.findByText("Ops · Invoices")).toBeDefined();

    renderWithQueryClient(React.createElement(OpsInvoiceDetailPage, { params: { id: "invoice-1" } }));
    expect(await screen.findByText("Ops · Invoice Detail")).toBeDefined();
  });

  it("renders payments routes", async () => {
    renderWithQueryClient(React.createElement(OpsPaymentsPage));
    expect(await screen.findByText("Ops · Payments")).toBeDefined();

    renderWithQueryClient(React.createElement(OpsPaymentDetailPage, { params: { id: "payment-1" } }));
    expect(await screen.findByText("Ops · Payment Detail")).toBeDefined();
  });

  it("renders journal entries routes", async () => {
    renderWithQueryClient(React.createElement(OpsJournalEntriesPage));
    expect(await screen.findByText("Ops · Journal Entries")).toBeDefined();

    renderWithQueryClient(React.createElement(OpsJournalEntryDetailPage, { params: { id: "je-1" } }));
    expect(await screen.findByText("Ops · Journal Entry Detail")).toBeDefined();
  });
});
