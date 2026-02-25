"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../components/admin/api-error-banner";
import { DataTable } from "../../../components/admin/data-table";
import { FormModal } from "../../../components/admin/form-modal";
import { RouteGuard } from "../../../components/route-guard";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { createCatalogPricebook } from "../../../lib/api/catalog";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useCatalogPricebooks } from "../hooks";

export default function SalesPricebooksPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [currencyFilter, setCurrencyFilter] = useState("USD");
  const [createOpen, setCreateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [isDefault, setIsDefault] = useState(false);
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");

  const queryClient = useQueryClient();
  const pricebooksQuery = useCatalogPricebooks(tenantId, companyCode, currencyFilter || undefined);
  const createMutation = useMutation({
    mutationFn: createCatalogPricebook,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.sales.pricebooks({ tenant_id: tenantId, company_code: companyCode, currency: currencyFilter })
      });
    }
  });

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Sales · Pricebooks</h1>
            <p className="text-sm text-slate-600">Pricebook list and create flow.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create pricebook</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-3">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
          <Input value={currencyFilter} onChange={(event) => setCurrencyFilter(event.target.value)} placeholder="Currency filter" />
        </div>

        <DataTable
          rows={pricebooksQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={pricebooksQuery.isLoading ? "Loading pricebooks..." : "No pricebooks found"}
          columns={[
            { key: "name", title: "Name", render: (row) => safeText(row.name) },
            { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
            { key: "default", title: "Default", render: (row) => (row.is_default ? "Yes" : "No") },
            { key: "valid_from", title: "Valid From", render: (row) => safeText(row.valid_from) },
            { key: "valid_to", title: "Valid To", render: (row) => safeText(row.valid_to) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/sales/pricebooks/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create pricebook"
          submitText="Create"
          pending={createMutation.isPending}
          onClose={() => setCreateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await createMutation.mutateAsync({
                tenant_id: tenantId,
                company_code: companyCode,
                name,
                currency,
                is_default: isDefault,
                valid_from: validFrom || null,
                valid_to: validTo || null
              });
              setCreateOpen(false);
              setName("");
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="pb-name" className="mb-1 block text-xs font-medium text-slate-600">Name</label>
              <Input id="pb-name" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="pb-currency" className="mb-1 block text-xs font-medium text-slate-600">Currency</label>
              <Input id="pb-currency" value={currency} onChange={(event) => setCurrency(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="pb-valid-from" className="mb-1 block text-xs font-medium text-slate-600">Valid from</label>
              <Input id="pb-valid-from" type="date" value={validFrom} onChange={(event) => setValidFrom(event.target.value)} />
            </div>
            <div>
              <label htmlFor="pb-valid-to" className="mb-1 block text-xs font-medium text-slate-600">Valid to</label>
              <Input id="pb-valid-to" type="date" value={validTo} onChange={(event) => setValidTo(event.target.value)} />
            </div>
            <div className="flex items-end gap-2 pb-1">
              <input id="pb-default" type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} />
              <label htmlFor="pb-default" className="text-sm text-slate-700">Is default</label>
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
