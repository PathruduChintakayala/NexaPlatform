"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { FormModal } from "../../../../components/admin/form-modal";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { allocatePayment, refundPayment } from "../../../../lib/api/payments";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useOpsPayment, useOpsPaymentAllocations } from "../../hooks";

interface PaymentDetailProps {
  params: { id: string };
}

export default function OpsPaymentDetailPage({ params }: PaymentDetailProps) {
  const paymentId = params.id;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [allocateOpen, setAllocateOpen] = useState(false);
  const [refundOpen, setRefundOpen] = useState(false);

  const [invoiceId, setInvoiceId] = useState("");
  const [allocateAmount, setAllocateAmount] = useState("0");

  const [refundAmount, setRefundAmount] = useState("0");
  const [refundReason, setRefundReason] = useState("");

  const queryClient = useQueryClient();
  const paymentQuery = useOpsPayment(paymentId);
  const allocationsQuery = useOpsPaymentAllocations(paymentId);
  const payment = paymentQuery.data;

  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.payment(paymentId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.paymentAllocations(paymentId) });
    if (payment) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.paymentList({ tenant_id: payment.tenant_id, company_code: payment.company_code }) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.invoices({ tenant_id: payment.tenant_id, company_code: payment.company_code }) });
    }
  };

  const allocateMutation = useMutation({
    mutationFn: () => allocatePayment(paymentId, { invoice_id: invoiceId, amount: allocateAmount }),
    onSuccess: invalidateAll
  });
  const refundMutation = useMutation({
    mutationFn: () => refundPayment(paymentId, { amount: refundAmount, reason: refundReason, fx_rate_to_company_base: "1" }),
    onSuccess: invalidateAll
  });

  const canAllocate = payment?.status === "CONFIRMED" || payment?.status === "INITIATED";
  const canRefund = payment?.status === "CONFIRMED";

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Payment Detail</h1>
          <p className="text-sm text-slate-600">Allocate payments to invoices and process refunds.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Payment #:</span> {safeText(payment?.payment_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(payment?.status)}
          </p>
          <p>
            <span className="font-medium">Method:</span> {safeText(payment?.payment_method)}
          </p>
          <p>
            <span className="font-medium">Amount:</span> {safeText(payment?.amount)}
          </p>

          <div className="mt-3 flex gap-2">
            <Button variant="secondary" disabled={!canAllocate || allocateMutation.isPending} onClick={() => setAllocateOpen(true)}>
              Allocate to invoice
            </Button>
            <Button variant="secondary" disabled={!canRefund || refundMutation.isPending} onClick={() => setRefundOpen(true)}>
              Refund
            </Button>
          </div>
        </article>

        <DataTable
          rows={allocationsQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={allocationsQuery.isLoading ? "Loading allocations..." : "No allocations"}
          columns={[
            { key: "invoice_id", title: "Invoice", render: (row) => safeText(row.invoice_id) },
            { key: "amount_allocated", title: "Allocated", render: (row) => safeText(row.amount_allocated) },
            { key: "created_at", title: "Created", render: (row) => safeText(row.created_at) }
          ]}
        />

        <DataTable
          rows={payment?.refunds ?? []}
          rowKey={(row) => row.id}
          emptyText={paymentQuery.isLoading ? "Loading refunds..." : "No refunds"}
          columns={[
            { key: "amount", title: "Amount", render: (row) => safeText(row.amount) },
            { key: "reason", title: "Reason", render: (row) => safeText(row.reason) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "created_at", title: "Created", render: (row) => safeText(row.created_at) }
          ]}
        />

        <FormModal
          open={allocateOpen}
          title="Allocate payment"
          submitText="Allocate"
          pending={allocateMutation.isPending}
          onClose={() => setAllocateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await allocateMutation.mutateAsync();
              setAllocateOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="allocate-invoice-id" className="mb-1 block text-xs font-medium text-slate-600">
                Invoice ID
              </label>
              <Input id="allocate-invoice-id" value={invoiceId} onChange={(event) => setInvoiceId(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="allocate-amount" className="mb-1 block text-xs font-medium text-slate-600">
                Amount
              </label>
              <Input id="allocate-amount" value={allocateAmount} onChange={(event) => setAllocateAmount(event.target.value)} required />
            </div>
          </div>
        </FormModal>

        <FormModal
          open={refundOpen}
          title="Refund payment"
          submitText="Refund"
          pending={refundMutation.isPending}
          onClose={() => setRefundOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await refundMutation.mutateAsync();
              setRefundOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="refund-amount" className="mb-1 block text-xs font-medium text-slate-600">
                Amount
              </label>
              <Input id="refund-amount" value={refundAmount} onChange={(event) => setRefundAmount(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="refund-reason" className="mb-1 block text-xs font-medium text-slate-600">
                Reason
              </label>
              <Input id="refund-reason" value={refundReason} onChange={(event) => setRefundReason(event.target.value)} required />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
