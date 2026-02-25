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
import { Select } from "../../../components/ui/select";
import { createPayment } from "../../../lib/api/payments";
import { queryKeys } from "../../../lib/queryKeys";
import { formatApiError, safeText, useOpsPayments } from "../hooks";

export default function OpsPaymentsPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [createOpen, setCreateOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [accountId, setAccountId] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [amount, setAmount] = useState("0");
  const [paymentMethod, setPaymentMethod] = useState<"MANUAL" | "BANK_TRANSFER" | "CARD">("MANUAL");

  const queryClient = useQueryClient();
  const paymentsQuery = useOpsPayments(tenantId, companyCode);

  const createMutation = useMutation({
    mutationFn: () =>
      createPayment({
        tenant_id: tenantId,
        company_code: companyCode,
        account_id: accountId || null,
        currency,
        amount,
        payment_method: paymentMethod,
        fx_rate_to_company_base: "1"
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.paymentList({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <header>
            <h1 className="text-2xl font-semibold">Ops · Payments</h1>
            <p className="text-sm text-slate-600">Payment creation and detail links.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create payment</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={paymentsQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={paymentsQuery.isLoading ? "Loading payments..." : "No payments found"}
          columns={[
            { key: "payment_number", title: "Payment #", render: (row) => safeText(row.payment_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "account_id", title: "Account", render: (row) => safeText(row.account_id) },
            { key: "method", title: "Method", render: (row) => safeText(row.payment_method) },
            { key: "amount", title: "Amount", render: (row) => safeText(row.amount) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/ops/payments/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create payment"
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
              <label htmlFor="payment-account-id" className="mb-1 block text-xs font-medium text-slate-600">
                Account ID
              </label>
              <Input id="payment-account-id" value={accountId} onChange={(event) => setAccountId(event.target.value)} />
            </div>
            <div>
              <label htmlFor="payment-currency" className="mb-1 block text-xs font-medium text-slate-600">
                Currency
              </label>
              <Input id="payment-currency" value={currency} onChange={(event) => setCurrency(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="payment-amount" className="mb-1 block text-xs font-medium text-slate-600">
                Amount
              </label>
              <Input id="payment-amount" value={amount} onChange={(event) => setAmount(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="payment-method" className="mb-1 block text-xs font-medium text-slate-600">
                Method
              </label>
              <Select id="payment-method" value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as typeof paymentMethod)}>
                <option value="MANUAL">MANUAL</option>
                <option value="BANK_TRANSFER">BANK_TRANSFER</option>
                <option value="CARD">CARD</option>
              </Select>
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
