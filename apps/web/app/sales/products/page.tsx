"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../components/admin/api-error-banner";
import { DataTable } from "../../../components/admin/data-table";
import { FormModal } from "../../../components/admin/form-modal";
import { RouteGuard } from "../../../components/route-guard";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { createCatalogProduct } from "../../../lib/api/catalog";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useCatalogProducts } from "../hooks";

export default function SalesProductsPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [regionCode, setRegionCode] = useState("US");
  const [defaultCurrency, setDefaultCurrency] = useState("USD");
  const [createOpen, setCreateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [productType, setProductType] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);

  const queryClient = useQueryClient();
  const productsQuery = useCatalogProducts(tenantId, companyCode);
  const createMutation = useMutation({
    mutationFn: createCatalogProduct,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.products({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Sales · Products</h1>
            <p className="text-sm text-slate-600">Product catalog list and create flow.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create product</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-4">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
          <Input value={regionCode} onChange={(event) => setRegionCode(event.target.value)} placeholder="Region" />
          <Input value={defaultCurrency} onChange={(event) => setDefaultCurrency(event.target.value)} placeholder="Currency" />
        </div>

        <DataTable
          rows={productsQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={productsQuery.isLoading ? "Loading products..." : "No products found"}
          columns={[
            { key: "name", title: "Name", render: (row) => safeText(row.name) },
            { key: "code", title: "Code", render: (row) => safeText(row.sku) },
            { key: "type", title: "Type", render: (row) => safeText(row.product_type) },
            { key: "active", title: "Active", render: (row) => (row.is_active ? "Yes" : "No") },
            { key: "description", title: "Description", render: (row) => safeText(row.description) },
            { key: "id", title: "ID", render: (row) => safeText(row.id) }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create product"
          submitText="Create"
          pending={createMutation.isPending}
          onClose={() => setCreateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await createMutation.mutateAsync({
                tenant_id: tenantId,
                company_code: companyCode,
                region_code: regionCode || null,
                sku,
                name,
                product_type: productType || null,
                description: description || null,
                default_currency: defaultCurrency,
                is_active: isActive
              });
              setCreateOpen(false);
              setName("");
              setSku("");
              setProductType("");
              setDescription("");
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="product-name" className="mb-1 block text-xs font-medium text-slate-600">Name</label>
              <Input id="product-name" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="product-code" className="mb-1 block text-xs font-medium text-slate-600">Code</label>
              <Input id="product-code" value={sku} onChange={(event) => setSku(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="product-type" className="mb-1 block text-xs font-medium text-slate-600">Type</label>
              <Input id="product-type" value={productType} onChange={(event) => setProductType(event.target.value)} />
            </div>
            <div className="flex items-end gap-2 pb-1">
              <input id="product-active" type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
              <label htmlFor="product-active" className="text-sm text-slate-700">Is active</label>
            </div>
            <div className="md:col-span-2">
              <label htmlFor="product-description" className="mb-1 block text-xs font-medium text-slate-600">Description</label>
              <Input id="product-description" value={description} onChange={(event) => setDescription(event.target.value)} />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
