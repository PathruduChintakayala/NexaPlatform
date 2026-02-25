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
import { createRevenueQuote } from "../../../lib/api/revenue";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useRevenueQuotes } from "../hooks";

export default function SalesQuotesPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [createOpen, setCreateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [regionCode, setRegionCode] = useState("US");
  const [currency, setCurrency] = useState("USD");
  const [validUntil, setValidUntil] = useState("");

  const queryClient = useQueryClient();
  const quotesQuery = useRevenueQuotes(tenantId, companyCode);
  const createMutation = useMutation({
    mutationFn: createRevenueQuote,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.quotes({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Sales · Quotes</h1>
            <p className="text-sm text-slate-600">Quote list and create flow.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create quote</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={quotesQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={quotesQuery.isLoading ? "Loading quotes..." : "No quotes found"}
          columns={[
            { key: "quote_number", title: "Quote #", render: (row) => safeText(row.quote_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
            { key: "total", title: "Total", render: (row) => safeText(row.total) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/sales/quotes/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create quote"
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
                currency,
                valid_until: validUntil || null
              });
              setCreateOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="quote-region" className="mb-1 block text-xs font-medium text-slate-600">Region</label>
              <Input id="quote-region" value={regionCode} onChange={(event) => setRegionCode(event.target.value)} />
            </div>
            <div>
              <label htmlFor="quote-currency" className="mb-1 block text-xs font-medium text-slate-600">Currency</label>
              <Input id="quote-currency" value={currency} onChange={(event) => setCurrency(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="quote-valid-until" className="mb-1 block text-xs font-medium text-slate-600">Valid until</label>
              <Input id="quote-valid-until" type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
