import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import SalesHubPage from "./page";
import SalesProductsPage from "./products/page";
import SalesPricebooksPage from "./pricebooks/page";
import SalesPricebookDetailPage from "./pricebooks/[id]/page";
import SalesQuotesPage from "./quotes/page";
import SalesQuoteDetailPage from "./quotes/[id]/page";
import SalesOrdersPage from "./orders/page";
import SalesOrderDetailPage from "./orders/[id]/page";
import SalesContractsPage from "./contracts/page";
import SalesContractDetailPage from "./contracts/[id]/page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "./test-utils";

const catalog = vi.hoisted(() => ({
  listCatalogProducts: vi.fn(),
  createCatalogProduct: vi.fn(),
  listCatalogPricebooks: vi.fn(),
  createCatalogPricebook: vi.fn(),
  upsertCatalogPricebookItem: vi.fn(),
  getCatalogPrice: vi.fn()
}));

const revenue = vi.hoisted(() => ({
  listRevenueQuotes: vi.fn(),
  createRevenueQuote: vi.fn(),
  getRevenueQuote: vi.fn(),
  addRevenueQuoteLine: vi.fn(),
  sendRevenueQuote: vi.fn(),
  acceptRevenueQuote: vi.fn(),
  createRevenueOrderFromQuote: vi.fn(),
  listRevenueOrders: vi.fn(),
  getRevenueOrder: vi.fn(),
  confirmRevenueOrder: vi.fn(),
  createRevenueContractFromOrder: vi.fn(),
  listRevenueContracts: vi.fn(),
  getRevenueContract: vi.fn()
}));

vi.mock("../../lib/api/catalog", () => catalog);
vi.mock("../../lib/api/revenue", () => revenue);

describe("Sales routes smoke", () => {
  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["sales"]));

    catalog.listCatalogProducts.mockResolvedValue([]);
    catalog.createCatalogProduct.mockResolvedValue({ id: "p1" });
    catalog.listCatalogPricebooks.mockResolvedValue([]);
    catalog.createCatalogPricebook.mockResolvedValue({ id: "pb1" });
    catalog.upsertCatalogPricebookItem.mockResolvedValue({ id: "pbi1" });
    catalog.getCatalogPrice.mockResolvedValue({ unit_price: "10.00", currency: "USD" });

    revenue.listRevenueQuotes.mockResolvedValue([]);
    revenue.createRevenueQuote.mockResolvedValue({ id: "q1" });
    revenue.getRevenueQuote.mockResolvedValue({ id: "q1", status: "DRAFT", quote_number: "Q-1", subtotal: "0", discount_total: "0", tax_total: "0", total: "0", lines: [] });
    revenue.addRevenueQuoteLine.mockResolvedValue({ id: "ql1" });
    revenue.sendRevenueQuote.mockResolvedValue({ id: "q1" });
    revenue.acceptRevenueQuote.mockResolvedValue({ id: "q1" });
    revenue.createRevenueOrderFromQuote.mockResolvedValue({ id: "o1" });
    revenue.listRevenueOrders.mockResolvedValue([]);
    revenue.getRevenueOrder.mockResolvedValue({ id: "o1", status: "DRAFT", order_number: "O-1", subtotal: "0", discount_total: "0", tax_total: "0", total: "0", lines: [] });
    revenue.confirmRevenueOrder.mockResolvedValue({ id: "o1" });
    revenue.createRevenueContractFromOrder.mockResolvedValue({ id: "c1" });
    revenue.listRevenueContracts.mockResolvedValue([]);
    revenue.getRevenueContract.mockResolvedValue({ id: "c1", contract_number: "C-1", status: "ACTIVE", start_date: null, end_date: null, order_id: "o1" });
  });

  it("renders sales hub", async () => {
    renderWithQueryClient(React.createElement(SalesHubPage));
    expect(await screen.findByText("Sales Hub")).toBeDefined();
  });

  it("renders products page", async () => {
    renderWithQueryClient(React.createElement(SalesProductsPage));
    expect(await screen.findByText("Sales · Products")).toBeDefined();
  });

  it("renders pricebooks page", async () => {
    renderWithQueryClient(React.createElement(SalesPricebooksPage));
    expect(await screen.findByText("Sales · Pricebooks")).toBeDefined();
  });

  it("renders pricebook detail page", async () => {
    renderWithQueryClient(React.createElement(SalesPricebookDetailPage, { params: { id: "pb1" } }));
    expect(await screen.findByText("Sales · Pricebook Detail")).toBeDefined();
  });

  it("renders quotes page", async () => {
    renderWithQueryClient(React.createElement(SalesQuotesPage));
    expect(await screen.findByText("Sales · Quotes")).toBeDefined();
  });

  it("renders quote detail page", async () => {
    renderWithQueryClient(React.createElement(SalesQuoteDetailPage, { params: { id: "q1" } }));
    expect(await screen.findByText("Sales · Quote Detail")).toBeDefined();
  });

  it("renders orders page", async () => {
    renderWithQueryClient(React.createElement(SalesOrdersPage));
    expect(await screen.findByText("Sales · Orders")).toBeDefined();
  });

  it("renders order detail page", async () => {
    renderWithQueryClient(React.createElement(SalesOrderDetailPage, { params: { id: "o1" } }));
    expect(await screen.findByText("Sales · Order Detail")).toBeDefined();
  });

  it("renders contracts page", async () => {
    renderWithQueryClient(React.createElement(SalesContractsPage));
    expect(await screen.findByText("Sales · Contracts")).toBeDefined();
  });

  it("renders contract detail page", async () => {
    renderWithQueryClient(React.createElement(SalesContractDetailPage, { params: { id: "c1" } }));
    expect(await screen.findByText("Sales · Contract Detail")).toBeDefined();
  });
});
