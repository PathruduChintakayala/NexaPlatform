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
import { generateInvoiceFromSubscription } from "../../../lib/api/billing";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useOpsCreditNotes, useOpsInvoices } from "../hooks";

export default function OpsInvoicesPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [generateOpen, setGenerateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [subscriptionId, setSubscriptionId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");

  const queryClient = useQueryClient();
  const invoicesQuery = useOpsInvoices(tenantId, companyCode);
  const creditNotesQuery = useOpsCreditNotes(tenantId, companyCode);

  const generateMutation = useMutation({
    mutationFn: () => generateInvoiceFromSubscription(subscriptionId, { period_start: periodStart, period_end: periodEnd }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.invoices({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Ops · Invoices</h1>
            <p className="text-sm text-slate-600">Invoice lifecycle and credit note visibility.</p>
          </header>
          <Button onClick={() => setGenerateOpen(true)}>Generate from subscription</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={invoicesQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={invoicesQuery.isLoading ? "Loading invoices..." : "No invoices found"}
          columns={[
            { key: "invoice_number", title: "Invoice #", render: (row) => safeText(row.invoice_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "subscription_id", title: "Subscription", render: (row) => safeText(row.subscription_id) },
            { key: "issue_date", title: "Issue", render: (row) => safeText(row.issue_date) },
            { key: "due_date", title: "Due", render: (row) => safeText(row.due_date) },
            { key: "total", title: "Total", render: (row) => safeText(row.total) },
            { key: "amount_due", title: "Amount Due", render: (row) => safeText(row.amount_due) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/ops/invoices/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />

        <article className="space-y-2 rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">Credit notes</h2>
          <DataTable
            rows={creditNotesQuery.data ?? []}
            rowKey={(row) => row.id}
            emptyText={creditNotesQuery.isLoading ? "Loading credit notes..." : "No credit notes"}
            columns={[
              { key: "credit_note_number", title: "Credit #", render: (row) => safeText(row.credit_note_number) },
              { key: "status", title: "Status", render: (row) => safeText(row.status) },
              { key: "invoice_id", title: "Invoice", render: (row) => safeText(row.invoice_id) },
              { key: "total", title: "Total", render: (row) => safeText(row.total) },
              { key: "issue_date", title: "Issue", render: (row) => safeText(row.issue_date) }
            ]}
          />
        </article>

        <FormModal
          open={generateOpen}
          title="Generate invoice from subscription"
          submitText="Generate"
          pending={generateMutation.isPending}
          onClose={() => setGenerateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await generateMutation.mutateAsync();
              setGenerateOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <label htmlFor="invoice-subscription-id" className="mb-1 block text-xs font-medium text-slate-600">
                Subscription ID
              </label>
              <Input
                id="invoice-subscription-id"
                value={subscriptionId}
                onChange={(event) => setSubscriptionId(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="invoice-period-start" className="mb-1 block text-xs font-medium text-slate-600">
                Period start
              </label>
              <Input
                id="invoice-period-start"
                type="date"
                value={periodStart}
                onChange={(event) => setPeriodStart(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="invoice-period-end" className="mb-1 block text-xs font-medium text-slate-600">
                Period end
              </label>
              <Input
                id="invoice-period-end"
                type="date"
                value={periodEnd}
                onChange={(event) => setPeriodEnd(event.target.value)}
                required
              />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
