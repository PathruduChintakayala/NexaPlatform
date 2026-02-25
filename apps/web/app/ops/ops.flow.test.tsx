import React from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import OpsInvoicesPage from "./invoices/page";
import OpsInvoiceDetailPage from "./invoices/[id]/page";
import OpsPaymentsPage from "./payments/page";
import OpsPaymentDetailPage from "./payments/[id]/page";
import OpsSubscriptionsPage from "./subscriptions/page";
import OpsSubscriptionDetailPage from "./subscriptions/[id]/page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "./test-utils";

const apiBase = "http://localhost:8000";

let subscriptionState = {
  id: "sub-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  subscription_number: "SUB-1001",
  contract_id: "contract-1",
  account_id: "account-1",
  currency: "USD",
  status: "DRAFT",
  start_date: null as string | null,
  current_period_start: null as string | null,
  current_period_end: null as string | null,
  auto_renew: true,
  renewal_term_count: 1,
  renewal_billing_period: "MONTHLY",
  created_at: "2026-02-26T00:00:00Z",
  updated_at: "2026-02-26T00:00:00Z",
  items: [
    {
      id: "sub-item-1",
      subscription_id: "sub-1",
      product_id: "product-1",
      pricebook_item_id: "pbi-1",
      quantity: "2",
      unit_price_snapshot: "10.00",
      created_at: "2026-02-26T00:00:00Z"
    }
  ]
};

let invoiceState = {
  id: "invoice-1",
  tenant_id: "tenant-a",
  company_code: "C1",
  region_code: "US",
  invoice_number: "INV-1001",
  account_id: "account-1",
  subscription_id: "sub-1",
  order_id: null as string | null,
  currency: "USD",
  status: "DRAFT",
  issue_date: null as string | null,
  due_date: "2026-03-05",
  period_start: "2026-02-01",
  period_end: "2026-02-29",
  subtotal: "20.00",
  discount_total: "0.00",
  tax_total: "0.00",
  total: "20.00",
  amount_due: "20.00",
  ledger_journal_entry_id: null as string | null,
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

let paymentState = {
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
  ledger_journal_entry_id: null as string | null,
  created_at: "2026-02-27T00:00:00Z",
  allocations: [] as Array<{ id: string; payment_id: string; invoice_id: string; amount_allocated: string; created_at: string }>,
  refunds: [] as Array<{ id: string; amount: string; reason: string; status: string; created_at: string }>
};

const server = setupServer(
  http.get(`${apiBase}/subscriptions`, () => HttpResponse.json([subscriptionState])),
  http.post(`${apiBase}/subscriptions/from-contract/:contractId`, async () => {
    subscriptionState = { ...subscriptionState, status: "DRAFT", start_date: "2026-02-01", current_period_start: "2026-02-01", current_period_end: "2026-02-29" };
    return HttpResponse.json(subscriptionState, { status: 201 });
  }),
  http.get(`${apiBase}/subscriptions/:subscriptionId`, () => HttpResponse.json(subscriptionState)),
  http.get(`${apiBase}/subscriptions/:subscriptionId/changes`, () => HttpResponse.json([])),
  http.post(`${apiBase}/subscriptions/:subscriptionId/activate`, async () => {
    subscriptionState = { ...subscriptionState, status: "ACTIVE" };
    return HttpResponse.json(subscriptionState);
  }),
  http.post(`${apiBase}/subscriptions/:subscriptionId/renew`, async () => HttpResponse.json(subscriptionState)),
  http.post(`${apiBase}/subscriptions/:subscriptionId/suspend`, async () => HttpResponse.json(subscriptionState)),
  http.post(`${apiBase}/subscriptions/:subscriptionId/resume`, async () => HttpResponse.json(subscriptionState)),
  http.post(`${apiBase}/subscriptions/:subscriptionId/cancel`, async () => HttpResponse.json(subscriptionState)),
  http.post(`${apiBase}/subscriptions/:subscriptionId/items/:productId/quantity`, async () => HttpResponse.json(subscriptionState)),

  http.get(`${apiBase}/billing/invoices`, () => HttpResponse.json([invoiceState])),
  http.get(`${apiBase}/billing/invoices/:invoiceId`, () => HttpResponse.json(invoiceState)),
  http.get(`${apiBase}/billing/invoices/:invoiceId/lines`, () => HttpResponse.json(invoiceState.lines)),
  http.get(`${apiBase}/billing/credit-notes`, () => HttpResponse.json([])),
  http.post(`${apiBase}/billing/invoices/from-subscription/:subscriptionId`, () => {
    invoiceState = { ...invoiceState, status: "DRAFT", amount_due: "20.00" };
    return HttpResponse.json(invoiceState, { status: 201 });
  }),
  http.post(`${apiBase}/billing/invoices/:invoiceId/issue`, () => {
    invoiceState = { ...invoiceState, status: "ISSUED", issue_date: "2026-02-27" };
    return HttpResponse.json(invoiceState);
  }),
  http.post(`${apiBase}/billing/invoices/:invoiceId/void`, () => HttpResponse.json(invoiceState)),
  http.post(`${apiBase}/billing/invoices/:invoiceId/mark-paid`, async () => {
    invoiceState = { ...invoiceState, status: "PAID", amount_due: "0.00" };
    return HttpResponse.json(invoiceState);
  }),
  http.post(`${apiBase}/billing/invoices/:invoiceId/credit-notes`, () => HttpResponse.json({}, { status: 201 })),

  http.get(`${apiBase}/payments`, () => HttpResponse.json([paymentState])),
  http.post(`${apiBase}/payments`, async ({ request }) => {
    const body = (await request.json()) as { amount: string };
    paymentState = { ...paymentState, amount: body.amount };
    return HttpResponse.json(paymentState, { status: 201 });
  }),
  http.get(`${apiBase}/payments/:paymentId`, () => HttpResponse.json(paymentState)),
  http.get(`${apiBase}/payments/:paymentId/allocations`, () => HttpResponse.json(paymentState.allocations)),
  http.post(`${apiBase}/payments/:paymentId/allocate`, async ({ request }) => {
    const body = (await request.json()) as { invoice_id: string; amount: string };
    paymentState = {
      ...paymentState,
      allocations: [
        ...paymentState.allocations,
        {
          id: `alloc-${paymentState.allocations.length + 1}`,
          payment_id: paymentState.id,
          invoice_id: body.invoice_id,
          amount_allocated: body.amount,
          created_at: "2026-02-27T00:00:00Z"
        }
      ]
    };
    if (body.invoice_id === invoiceState.id && body.amount === invoiceState.amount_due) {
      invoiceState = { ...invoiceState, status: "PAID", amount_due: "0.00" };
    }
    return HttpResponse.json(paymentState);
  }),
  http.post(`${apiBase}/payments/:paymentId/refund`, () => HttpResponse.json({}, { status: 201 }))
);

describe("Ops lifecycle flow", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => {
    server.resetHandlers();
    cleanup();
  });
  afterAll(() => server.close());

  beforeEach(() => {
    subscriptionState = {
      ...subscriptionState,
      status: "DRAFT",
      start_date: null,
      current_period_start: null,
      current_period_end: null
    };
    invoiceState = {
      ...invoiceState,
      status: "DRAFT",
      issue_date: null,
      amount_due: "20.00"
    };
    paymentState = {
      ...paymentState,
      amount: "20.00",
      allocations: []
    };

    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["ops"]));
  });

  it("creates subscription, activates, invoices, issues, pays and allocates to paid invoice", async () => {
    const user = userEvent.setup();

    renderWithQueryClient(React.createElement(OpsSubscriptionsPage));
    await user.click(screen.getByRole("button", { name: "Create from contract" }));
    await user.type(screen.getByLabelText("Contract ID"), "contract-1");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(screen.getByText("SUB-1001")).toBeDefined();
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsSubscriptionDetailPage, { params: { id: "sub-1" } }));
    await user.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => {
      expect(screen.getByText(/ACTIVE/)).toBeDefined();
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsInvoicesPage));
    await user.click(screen.getByRole("button", { name: "Generate from subscription" }));
    await user.type(screen.getByLabelText("Subscription ID"), "sub-1");
    await user.type(screen.getByLabelText("Period start"), "2026-02-01");
    await user.type(screen.getByLabelText("Period end"), "2026-02-29");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => {
      expect(screen.getByText("INV-1001")).toBeDefined();
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsInvoiceDetailPage, { params: { id: "invoice-1" } }));
    await user.click(screen.getByRole("button", { name: "Issue" }));
    await waitFor(() => {
      expect(screen.getByText(/ISSUED/)).toBeDefined();
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsPaymentsPage));
    await user.click(screen.getByRole("button", { name: "Create payment" }));
    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "20.00");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(screen.getByText("PAY-1001")).toBeDefined();
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsPaymentDetailPage, { params: { id: "payment-1" } }));
    await user.click(screen.getByRole("button", { name: "Allocate to invoice" }));
    await user.type(screen.getByLabelText("Invoice ID"), "invoice-1");
    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "20.00");
    await user.click(screen.getByRole("button", { name: "Allocate" }));

    await waitFor(() => {
      expect(paymentState.allocations.length).toBe(1);
      expect(invoiceState.status).toBe("PAID");
    });

    cleanup();
    renderWithQueryClient(React.createElement(OpsInvoiceDetailPage, { params: { id: "invoice-1" } }));
    await waitFor(() => {
      expect(screen.getByText(/PAID/)).toBeDefined();
    });
  });
});
