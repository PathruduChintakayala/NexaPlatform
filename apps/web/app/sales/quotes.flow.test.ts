import React from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import SalesQuotesPage from "./quotes/page";
import SalesQuoteDetailPage from "./quotes/[id]/page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "./test-utils";

const apiBase = "http://localhost:8000";

let quoteState = {
  id: "quote-1",
  quote_number: "Q-1001",
  status: "DRAFT",
  subtotal: "0",
  discount_total: "0",
  tax_total: "0",
  total: "0",
  lines: [] as Array<{ id: string; product_id: string; pricebook_item_id: string; quantity: string; unit_price: string; line_total: string }>
};

let createdOrderId = "";

const server = setupServer(
  http.get(`${apiBase}/revenue/quotes`, () => HttpResponse.json([quoteState])),
  http.post(`${apiBase}/revenue/quotes`, async () => HttpResponse.json(quoteState, { status: 201 })),
  http.get(`${apiBase}/revenue/quotes/:quoteId`, () => HttpResponse.json(quoteState)),
  http.post(`${apiBase}/revenue/quotes/:quoteId/lines`, async ({ request }) => {
    const body = (await request.json()) as { product_id: string; pricebook_item_id: string; quantity: string };
    const line = {
      id: `line-${quoteState.lines.length + 1}`,
      product_id: body.product_id,
      pricebook_item_id: body.pricebook_item_id,
      quantity: body.quantity,
      unit_price: "50.00",
      line_total: "50.00"
    };
    quoteState = { ...quoteState, lines: [...quoteState.lines, line], subtotal: "50.00", total: "50.00" };
    return HttpResponse.json(line, { status: 201 });
  }),
  http.post(`${apiBase}/revenue/quotes/:quoteId/accept`, () => {
    quoteState = { ...quoteState, status: "ACCEPTED" };
    return HttpResponse.json(quoteState);
  }),
  http.post(`${apiBase}/revenue/quotes/:quoteId/create-order`, () => {
    createdOrderId = "order-1";
    return HttpResponse.json({ id: createdOrderId }, { status: 201 });
  }),
  http.get(`${apiBase}/catalog/products`, () =>
    HttpResponse.json([
      {
        id: "prod-1",
        sku: "PRO-1",
        name: "Product 1",
        is_active: true,
        description: null,
        product_type: null,
        default_currency: "USD",
        tenant_id: "tenant-a",
        company_code: "C1",
        region_code: "US",
        created_at: "2026-02-25"
      }
    ])
  ),
  http.get(`${apiBase}/revenue/orders`, () => HttpResponse.json(createdOrderId ? [{ id: createdOrderId }] : []))
);

describe("Sales quote flow", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());

  beforeEach(() => {
    quoteState = {
      id: "quote-1",
      quote_number: "Q-1001",
      status: "DRAFT",
      subtotal: "0",
      discount_total: "0",
      tax_total: "0",
      total: "0",
      lines: []
    };
    createdOrderId = "";

    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["sales"]));
  });

  it("creates quote then adds line accepts and creates order", async () => {
    renderWithQueryClient(React.createElement(SalesQuotesPage));

    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "Create quote" })[0]);
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getByText("Q-1001")).toBeDefined();
    });

    renderWithQueryClient(React.createElement(SalesQuoteDetailPage, { params: { id: "quote-1" } }));

    await user.click(screen.getByRole("button", { name: "Add line" }));
    await user.selectOptions(screen.getByLabelText("Product"), "prod-1");
    await user.type(screen.getByLabelText("Pricebook item ID"), "pbi-1");
    await user.clear(screen.getByLabelText("Quantity"));
    await user.type(screen.getByLabelText("Quantity"), "1");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(screen.getByText("pbi-1")).toBeDefined();
    });

    await user.click(screen.getByRole("button", { name: "Accept quote" }));
    await waitFor(() => {
      expect(screen.getByText(/ACCEPTED/)).toBeDefined();
    });

    await user.click(screen.getByRole("button", { name: "Create order" }));
    await waitFor(() => {
      expect(createdOrderId).toBe("order-1");
    });
  });
});
