"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { FormModal } from "../../../../components/admin/form-modal";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import {
  acceptRevenueQuote,
  addRevenueQuoteLine,
  createRevenueOrderFromQuote,
  sendRevenueQuote
} from "../../../../lib/api/revenue";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useCatalogProducts, useRevenueQuote } from "../../hooks";

interface QuoteDetailProps {
  params: { id: string };
}

export default function SalesQuoteDetailPage({ params }: QuoteDetailProps) {
  const quoteId = params.id;
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [addLineOpen, setAddLineOpen] = useState(false);
  const [productId, setProductId] = useState("");
  const [pricebookItemId, setPricebookItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [lineDescription, setLineDescription] = useState("");

  const queryClient = useQueryClient();
  const quoteQuery = useRevenueQuote(quoteId);
  const productsQuery = useCatalogProducts(tenantId, companyCode);

  const sendMutation = useMutation({
    mutationFn: () => sendRevenueQuote(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quote(quoteId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quotes({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  const acceptMutation = useMutation({
    mutationFn: () => acceptRevenueQuote(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quote(quoteId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quotes({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  const createOrderMutation = useMutation({
    mutationFn: () => createRevenueOrderFromQuote(quoteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quote(quoteId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.orders({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  const addLineMutation = useMutation({
    mutationFn: () =>
      addRevenueQuoteLine(quoteId, {
        product_id: productId,
        pricebook_item_id: pricebookItemId,
        quantity,
        description: lineDescription || null
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quote(quoteId) });
    }
  });

  const quote = quoteQuery.data;
  const canCreateOrder = quote?.status === "ACCEPTED";

  const lineRows = useMemo(() => quote?.lines ?? [], [quote]);

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold">Sales · Quote Detail</h1>
          <p className="text-sm text-slate-600">Status and server-computed totals.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-4">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
          <Button variant="secondary" onClick={() => setAddLineOpen(true)}>
            Add line
          </Button>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              disabled={sendMutation.isPending}
              onClick={async () => {
                try {
                  await sendMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Send quote
            </Button>
            <Button
              variant="secondary"
              disabled={acceptMutation.isPending}
              onClick={async () => {
                try {
                  await acceptMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Accept quote
            </Button>
          </div>
        </div>

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Quote #:</span> {safeText(quote?.quote_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(quote?.status)}
          </p>
          <p>
            <span className="font-medium">Subtotal:</span> {safeText(quote?.subtotal)}
          </p>
          <p>
            <span className="font-medium">Discount:</span> {safeText(quote?.discount_total)}
          </p>
          <p>
            <span className="font-medium">Tax:</span> {safeText(quote?.tax_total)}
          </p>
          <p>
            <span className="font-medium">Total:</span> {safeText(quote?.total)}
          </p>
          <div className="mt-3">
            <Button
              disabled={!canCreateOrder || createOrderMutation.isPending}
              onClick={async () => {
                try {
                  const created = await createOrderMutation.mutateAsync();
                  setErrorMessage(null);
                  await queryClient.invalidateQueries({ queryKey: queryKeys.sales.order(created.id) });
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Create order
            </Button>
          </div>
        </article>

        <DataTable
          rows={lineRows}
          rowKey={(row) => row.id}
          emptyText={quoteQuery.isLoading ? "Loading lines..." : "No lines"}
          columns={[
            { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
            { key: "pricebook_item_id", title: "Pricebook Item", render: (row) => safeText(row.pricebook_item_id) },
            { key: "quantity", title: "Qty", render: (row) => safeText(row.quantity) },
            { key: "unit_price", title: "Unit", render: (row) => safeText(row.unit_price) },
            { key: "line_total", title: "Line Total", render: (row) => safeText(row.line_total) }
          ]}
        />

        <FormModal
          open={addLineOpen}
          title="Add quote line"
          submitText="Add"
          pending={addLineMutation.isPending}
          onClose={() => setAddLineOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await addLineMutation.mutateAsync();
              setAddLineOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="quote-line-product" className="mb-1 block text-xs font-medium text-slate-600">Product</label>
              <Select id="quote-line-product" value={productId} onChange={(event) => setProductId(event.target.value)}>
                <option value="">Select product</option>
                {(productsQuery.data ?? []).map((product) => (
                  <option key={product.id} value={product.id}>
                    {safeText(product.name)} ({safeText(product.sku)})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="quote-line-item" className="mb-1 block text-xs font-medium text-slate-600">Pricebook item ID</label>
              <Input id="quote-line-item" value={pricebookItemId} onChange={(event) => setPricebookItemId(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="quote-line-qty" className="mb-1 block text-xs font-medium text-slate-600">Quantity</label>
              <Input id="quote-line-qty" value={quantity} onChange={(event) => setQuantity(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="quote-line-desc" className="mb-1 block text-xs font-medium text-slate-600">Description</label>
              <Input id="quote-line-desc" value={lineDescription} onChange={(event) => setLineDescription(event.target.value)} />
            </div>
          </div>
          <p className="text-xs text-slate-500">Use the Pricebook detail page to upsert items and copy the pricebook item ID.</p>
          <div className="pt-1">
            <Link className="text-xs text-slate-700 underline" href="/sales/pricebooks">
              Open pricebooks
            </Link>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
