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
import { createSubscriptionFromContract } from "../../../lib/api/subscription";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useOpsSubscriptions } from "../hooks";

export default function OpsSubscriptionsPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [createOpen, setCreateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [contractId, setContractId] = useState("");
  const [planId, setPlanId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [startDate, setStartDate] = useState("");

  const queryClient = useQueryClient();
  const subscriptionsQuery = useOpsSubscriptions(tenantId, companyCode);

  const createMutation = useMutation({
    mutationFn: () =>
      createSubscriptionFromContract(contractId, {
        plan_id: planId || null,
        account_id: accountId || null,
        start_date: startDate || null,
        auto_renew: true,
        renewal_term_count: 1,
        renewal_billing_period: "MONTHLY"
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.ops.subscriptions({ tenant_id: tenantId, company_code: companyCode })
      });
    }
  });

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Ops · Subscriptions</h1>
            <p className="text-sm text-slate-600">Subscriptions list and contract-to-subscription creation.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create from contract</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={subscriptionsQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={subscriptionsQuery.isLoading ? "Loading subscriptions..." : "No subscriptions found"}
          columns={[
            { key: "subscription_number", title: "Subscription #", render: (row) => safeText(row.subscription_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "contract_id", title: "Contract", render: (row) => safeText(row.contract_id) },
            { key: "account_id", title: "Account", render: (row) => safeText(row.account_id) },
            { key: "period_start", title: "Period Start", render: (row) => safeText(row.current_period_start) },
            { key: "period_end", title: "Period End", render: (row) => safeText(row.current_period_end) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/ops/subscriptions/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create subscription from contract"
          submitText="Create"
          pending={createMutation.isPending}
          onClose={() => setCreateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await createMutation.mutateAsync();
              setCreateOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="subscription-contract-id" className="mb-1 block text-xs font-medium text-slate-600">
                Contract ID
              </label>
              <Input
                id="subscription-contract-id"
                value={contractId}
                onChange={(event) => setContractId(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="subscription-plan-id" className="mb-1 block text-xs font-medium text-slate-600">
                Plan ID
              </label>
              <Input id="subscription-plan-id" value={planId} onChange={(event) => setPlanId(event.target.value)} />
            </div>
            <div>
              <label htmlFor="subscription-account-id" className="mb-1 block text-xs font-medium text-slate-600">
                Account ID
              </label>
              <Input id="subscription-account-id" value={accountId} onChange={(event) => setAccountId(event.target.value)} />
            </div>
            <div>
              <label htmlFor="subscription-start-date" className="mb-1 block text-xs font-medium text-slate-600">
                Start date
              </label>
              <Input
                id="subscription-start-date"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
