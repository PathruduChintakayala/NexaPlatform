"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { FormModal } from "../../../../components/admin/form-modal";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { createCreditNote, issueInvoice, markInvoicePaid, voidInvoice } from "../../../../lib/api/billing";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useOpsInvoice, useOpsInvoiceLines } from "../../hooks";

interface InvoiceDetailProps {
  params: { id: string };
}

function nowValue() {
  return new Date().toISOString();
}

export default function OpsInvoiceDetailPage({ params }: InvoiceDetailProps) {
  const invoiceId = params.id;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [voidReason, setVoidReason] = useState("");
  const [paidAmount, setPaidAmount] = useState("0");

  const [creditOpen, setCreditOpen] = useState(false);
  const [creditDescription, setCreditDescription] = useState("");
  const [creditQuantity, setCreditQuantity] = useState("1");
  const [creditUnitPrice, setCreditUnitPrice] = useState("0");
  const [creditTaxTotal, setCreditTaxTotal] = useState("0");

  const queryClient = useQueryClient();
  const invoiceQuery = useOpsInvoice(invoiceId);
  const linesQuery = useOpsInvoiceLines(invoiceId);
  const invoice = invoiceQuery.data;

  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.invoice(invoiceId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.invoiceLines(invoiceId) });
    if (invoice) {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.invoices({ tenant_id: invoice.tenant_id, company_code: invoice.company_code }) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.creditNotes({ tenant_id: invoice.tenant_id, company_code: invoice.company_code }) });
    }
  };

  const issueMutation = useMutation({ mutationFn: () => issueInvoice(invoiceId), onSuccess: invalidateAll });
  const voidMutation = useMutation({ mutationFn: () => voidInvoice(invoiceId, voidReason), onSuccess: invalidateAll });
  const markPaidMutation = useMutation({
    mutationFn: () => markInvoicePaid(invoiceId, { amount: paidAmount, paid_at: nowValue() }),
    onSuccess: invalidateAll
  });
  const creditMutation = useMutation({
    mutationFn: () =>
      createCreditNote(invoiceId, {
        tax_total: creditTaxTotal,
        lines: [
          {
            description: creditDescription || null,
            quantity: creditQuantity,
            unit_price_snapshot: creditUnitPrice
          }
        ]
      }),
    onSuccess: invalidateAll
  });

  const canIssue = invoice?.status === "DRAFT";
  const canVoid = invoice?.status === "DRAFT" || invoice?.status === "ISSUED";
  const canMarkPaid = invoice?.status === "ISSUED" || invoice?.status === "OVERDUE";

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Invoice Detail</h1>
          <p className="text-sm text-slate-600">Issue, void, mark paid, and credit note actions.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Invoice #:</span> {safeText(invoice?.invoice_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(invoice?.status)}
          </p>
          <p>
            <span className="font-medium">Subscription:</span> {safeText(invoice?.subscription_id)}
          </p>
          <p>
            <span className="font-medium">Issue:</span> {safeText(invoice?.issue_date)}
          </p>
          <p>
            <span className="font-medium">Due:</span> {safeText(invoice?.due_date)}
          </p>
          <p>
            <span className="font-medium">Subtotal:</span> {safeText(invoice?.subtotal)}
          </p>
          <p>
            <span className="font-medium">Discount:</span> {safeText(invoice?.discount_total)}
          </p>
          <p>
            <span className="font-medium">Tax:</span> {safeText(invoice?.tax_total)}
          </p>
          <p>
            <span className="font-medium">Total:</span> {safeText(invoice?.total)}
          </p>
          <p>
            <span className="font-medium">Amount due:</span> {safeText(invoice?.amount_due)}
          </p>

          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <Input value={voidReason} onChange={(event) => setVoidReason(event.target.value)} placeholder="Void reason" />
            <Input value={paidAmount} onChange={(event) => setPaidAmount(event.target.value)} placeholder="Paid amount" />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!canIssue || issueMutation.isPending}
              onClick={async () => {
                try {
                  await issueMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Issue
            </Button>
            <Button
              variant="secondary"
              disabled={!canMarkPaid || markPaidMutation.isPending}
              onClick={async () => {
                try {
                  await markPaidMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Mark paid
            </Button>
            <Button
              variant="danger"
              disabled={!canVoid || !voidReason || voidMutation.isPending}
              onClick={async () => {
                try {
                  await voidMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Void
            </Button>
            <Button variant="secondary" disabled={!invoice || creditMutation.isPending} onClick={() => setCreditOpen(true)}>
              Create credit note
            </Button>
          </div>
        </article>

        <DataTable
          rows={linesQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={linesQuery.isLoading ? "Loading invoice lines..." : "No lines"}
          columns={[
            { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
            { key: "description", title: "Description", render: (row) => safeText(row.description) },
            { key: "quantity", title: "Qty", render: (row) => safeText(row.quantity) },
            { key: "unit_price_snapshot", title: "Unit", render: (row) => safeText(row.unit_price_snapshot) },
            { key: "line_total", title: "Line Total", render: (row) => safeText(row.line_total) }
          ]}
        />

        <FormModal
          open={creditOpen}
          title="Create credit note"
          submitText="Create"
          pending={creditMutation.isPending}
          onClose={() => setCreditOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await creditMutation.mutateAsync();
              setCreditOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <label htmlFor="credit-description" className="mb-1 block text-xs font-medium text-slate-600">
                Description
              </label>
              <Input
                id="credit-description"
                value={creditDescription}
                onChange={(event) => setCreditDescription(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="credit-quantity" className="mb-1 block text-xs font-medium text-slate-600">
                Quantity
              </label>
              <Input id="credit-quantity" value={creditQuantity} onChange={(event) => setCreditQuantity(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="credit-unit" className="mb-1 block text-xs font-medium text-slate-600">
                Unit price
              </label>
              <Input id="credit-unit" value={creditUnitPrice} onChange={(event) => setCreditUnitPrice(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="credit-tax" className="mb-1 block text-xs font-medium text-slate-600">
                Tax total
              </label>
              <Input id="credit-tax" value={creditTaxTotal} onChange={(event) => setCreditTaxTotal(event.target.value)} required />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
