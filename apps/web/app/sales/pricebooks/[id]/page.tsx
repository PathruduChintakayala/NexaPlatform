"use client";

import React, { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { FormModal } from "../../../../components/admin/form-modal";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { getCatalogPrice, upsertCatalogPricebookItem } from "../../../../lib/api/catalog";
import { queryKeys } from "../../../../lib/queryKeys";
import type { BillingPeriod, CatalogPricebookItemRead } from "../../../../lib/types";
import { formatApiError, safeText, useCatalogPricebooks, useCatalogProducts } from "../../hooks";

const BILLING_PERIODS: BillingPeriod[] = ["ONE_TIME", "MONTHLY", "QUARTERLY", "ANNUAL"];

interface PricebookDetailProps {
  params: { id: string };
}

export default function SalesPricebookDetailPage({ params }: PricebookDetailProps) {
  const pricebookId = params.id;
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [addItemOpen, setAddItemOpen] = useState(false);

  const [productId, setProductId] = useState("");
  const [billingPeriod, setBillingPeriod] = useState<BillingPeriod>("MONTHLY");
  const [itemCurrency, setItemCurrency] = useState("USD");
  const [unitPrice, setUnitPrice] = useState("0.00");
  const [usageUnit, setUsageUnit] = useState("");

  const [lookupProductId, setLookupProductId] = useState("");
  const [lookupBillingPeriod, setLookupBillingPeriod] = useState<BillingPeriod>("MONTHLY");
  const [lookupCurrency, setLookupCurrency] = useState("USD");
  const [lookupResult, setLookupResult] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const productsQuery = useCatalogProducts(tenantId, companyCode);
  const pricebooksQuery = useCatalogPricebooks(tenantId, companyCode);
  const itemsQueryKey = queryKeys.sales.pricebookItems(pricebookId);

  const pricebookItems = useMemo(
    () => (queryClient.getQueryData(itemsQueryKey) as CatalogPricebookItemRead[] | undefined) ?? [],
    [itemsQueryKey, queryClient]
  );

  const selectedPricebook = (pricebooksQuery.data ?? []).find((item) => item.id === pricebookId) ?? null;

  const upsertItemMutation = useMutation({
    mutationFn: upsertCatalogPricebookItem,
    onSuccess: (created) => {
      queryClient.setQueryData(itemsQueryKey, (prev: CatalogPricebookItemRead[] | undefined) => {
        const existing = prev ?? [];
        const next = existing.filter((item) => item.id !== created.id);
        return [...next, created];
      });
    }
  });

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales · Pricebook Detail</h1>
          <p className="text-sm text-slate-600">Pricebook items and price lookup for {safeText(selectedPricebook?.name)}.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-3">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
          <Button onClick={() => setAddItemOpen(true)}>Add item</Button>
        </div>

        <article className="space-y-2 rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">Pricebook items</h2>
          <p className="text-xs text-slate-500">Only items upserted in this UI session are listed because the backend does not expose a list-items endpoint.</p>
          <DataTable
            rows={pricebookItems}
            rowKey={(row) => row.id}
            emptyText="No items in current session"
            columns={[
              { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
              { key: "billing_period", title: "Billing", render: (row) => safeText(row.billing_period) },
              { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
              { key: "unit_price", title: "Unit Price", render: (row) => safeText(row.unit_price) },
              { key: "id", title: "ID", render: (row) => safeText(row.id) }
            ]}
          />
        </article>

        <article className="space-y-3 rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">Price lookup</h2>
          <div className="grid gap-3 md:grid-cols-4">
            <Select value={lookupProductId} onChange={(event) => setLookupProductId(event.target.value)}>
              <option value="">Select product</option>
              {(productsQuery.data ?? []).map((product) => (
                <option key={product.id} value={product.id}>
                  {safeText(product.name)} ({safeText(product.sku)})
                </option>
              ))}
            </Select>
            <Select value={lookupBillingPeriod} onChange={(event) => setLookupBillingPeriod(event.target.value as BillingPeriod)}>
              {BILLING_PERIODS.map((period) => (
                <option key={period} value={period}>
                  {period}
                </option>
              ))}
            </Select>
            <Input value={lookupCurrency} onChange={(event) => setLookupCurrency(event.target.value)} placeholder="Currency" />
            <Button
              onClick={async () => {
                const selectedProduct = (productsQuery.data ?? []).find((item) => item.id === lookupProductId);
                if (!selectedProduct?.sku) {
                  setErrorMessage("Select a product first.");
                  return;
                }
                try {
                  const result = await getCatalogPrice({
                    tenant_id: tenantId,
                    company_code: companyCode,
                    sku: selectedProduct.sku,
                    currency: lookupCurrency,
                    billing_period: lookupBillingPeriod
                  });
                  setLookupResult(`Unit price: ${safeText(result.unit_price)} (${safeText(result.currency)})`);
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Lookup price
            </Button>
          </div>
          {lookupResult ? <p className="text-sm text-slate-700">{lookupResult}</p> : null}
        </article>

        <FormModal
          open={addItemOpen}
          title="Add pricebook item"
          submitText="Save"
          pending={upsertItemMutation.isPending}
          onClose={() => setAddItemOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await upsertItemMutation.mutateAsync({
                pricebook_id: pricebookId,
                product_id: productId,
                billing_period: billingPeriod,
                currency: itemCurrency,
                unit_price: unitPrice,
                usage_unit: usageUnit || null
              });
              setAddItemOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="item-product" className="mb-1 block text-xs font-medium text-slate-600">Product</label>
              <Select id="item-product" value={productId} onChange={(event) => setProductId(event.target.value)}>
                <option value="">Select product</option>
                {(productsQuery.data ?? []).map((product) => (
                  <option key={product.id} value={product.id}>
                    {safeText(product.name)} ({safeText(product.sku)})
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="item-billing" className="mb-1 block text-xs font-medium text-slate-600">Billing period</label>
              <Select id="item-billing" value={billingPeriod} onChange={(event) => setBillingPeriod(event.target.value as BillingPeriod)}>
                {BILLING_PERIODS.map((period) => (
                  <option key={period} value={period}>
                    {period}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="item-currency" className="mb-1 block text-xs font-medium text-slate-600">Currency</label>
              <Input id="item-currency" value={itemCurrency} onChange={(event) => setItemCurrency(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="item-price" className="mb-1 block text-xs font-medium text-slate-600">Unit price</label>
              <Input id="item-price" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} required />
            </div>
            <div className="md:col-span-2">
              <label htmlFor="item-usage" className="mb-1 block text-xs font-medium text-slate-600">Usage unit</label>
              <Input id="item-usage" value={usageUnit} onChange={(event) => setUsageUnit(event.target.value)} />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
