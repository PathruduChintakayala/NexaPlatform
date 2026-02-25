"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { FormModal } from "../../../../components/admin/form-modal";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import {
  activateSubscription,
  cancelSubscription,
  changeSubscriptionQuantity,
  renewSubscription,
  resumeSubscription,
  suspendSubscription
} from "../../../../lib/api/subscription";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useOpsSubscription, useOpsSubscriptionChanges } from "../../hooks";

interface SubscriptionDetailProps {
  params: { id: string };
}

function todayDateValue() {
  return new Date().toISOString().slice(0, 10);
}

export default function OpsSubscriptionDetailPage({ params }: SubscriptionDetailProps) {
  const subscriptionId = params.id;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [effectiveDate, setEffectiveDate] = useState(todayDateValue());
  const [cancelReason, setCancelReason] = useState("");

  const [quantityOpen, setQuantityOpen] = useState(false);
  const [quantityProductId, setQuantityProductId] = useState("");
  const [quantityValue, setQuantityValue] = useState("1");

  const queryClient = useQueryClient();
  const subscriptionQuery = useOpsSubscription(subscriptionId);
  const changesQuery = useOpsSubscriptionChanges(subscriptionId);
  const subscription = subscriptionQuery.data;

  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.subscription(subscriptionId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.ops.subscriptionChanges(subscriptionId) });
    if (subscription) {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.ops.subscriptions({ tenant_id: subscription.tenant_id, company_code: subscription.company_code })
      });
    }
  };

  const activateMutation = useMutation({ mutationFn: () => activateSubscription(subscriptionId, { start_date: null }), onSuccess: invalidateAll });
  const renewMutation = useMutation({ mutationFn: () => renewSubscription(subscriptionId), onSuccess: invalidateAll });
  const suspendMutation = useMutation({
    mutationFn: () => suspendSubscription(subscriptionId, { effective_date: effectiveDate }),
    onSuccess: invalidateAll
  });
  const resumeMutation = useMutation({
    mutationFn: () => resumeSubscription(subscriptionId, { effective_date: effectiveDate }),
    onSuccess: invalidateAll
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelSubscription(subscriptionId, { effective_date: effectiveDate, reason: cancelReason || null }),
    onSuccess: invalidateAll
  });
  const quantityMutation = useMutation({
    mutationFn: () => changeSubscriptionQuantity(subscriptionId, quantityProductId, { new_qty: quantityValue, effective_date: effectiveDate }),
    onSuccess: invalidateAll
  });

  const canActivate = subscription?.status === "DRAFT";
  const canRenew = subscription?.status === "ACTIVE";
  const canSuspend = subscription?.status === "ACTIVE";
  const canResume = subscription?.status === "SUSPENDED";
  const canCancel = subscription?.status === "ACTIVE" || subscription?.status === "SUSPENDED";
  const canChangeQuantity = subscription?.status === "ACTIVE";

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Subscription Detail</h1>
          <p className="text-sm text-slate-600">Lifecycle transitions and item quantity updates.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Subscription #:</span> {safeText(subscription?.subscription_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(subscription?.status)}
          </p>
          <p>
            <span className="font-medium">Contract:</span> {safeText(subscription?.contract_id)}
          </p>
          <p>
            <span className="font-medium">Account:</span> {safeText(subscription?.account_id)}
          </p>
          <p>
            <span className="font-medium">Current period:</span> {safeText(subscription?.current_period_start)} → {safeText(subscription?.current_period_end)}
          </p>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <Input type="date" value={effectiveDate} onChange={(event) => setEffectiveDate(event.target.value)} />
            <Input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Cancel reason (optional)" />
            <Button variant="secondary" disabled={!canChangeQuantity} onClick={() => setQuantityOpen(true)}>
              Change quantity
            </Button>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!canActivate || activateMutation.isPending}
              onClick={async () => {
                try {
                  await activateMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Activate
            </Button>
            <Button
              variant="secondary"
              disabled={!canRenew || renewMutation.isPending}
              onClick={async () => {
                try {
                  await renewMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Renew
            </Button>
            <Button
              variant="secondary"
              disabled={!canSuspend || suspendMutation.isPending}
              onClick={async () => {
                try {
                  await suspendMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Suspend
            </Button>
            <Button
              variant="secondary"
              disabled={!canResume || resumeMutation.isPending}
              onClick={async () => {
                try {
                  await resumeMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Resume
            </Button>
            <Button
              variant="danger"
              disabled={!canCancel || cancelMutation.isPending}
              onClick={async () => {
                try {
                  await cancelMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Cancel
            </Button>
          </div>
        </article>

        <DataTable
          rows={subscription?.items ?? []}
          rowKey={(row) => row.id}
          emptyText={subscriptionQuery.isLoading ? "Loading items..." : "No items"}
          columns={[
            { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
            { key: "pricebook_item_id", title: "Pricebook Item", render: (row) => safeText(row.pricebook_item_id) },
            { key: "quantity", title: "Qty", render: (row) => safeText(row.quantity) },
            { key: "unit_price_snapshot", title: "Unit", render: (row) => safeText(row.unit_price_snapshot) }
          ]}
        />

        <DataTable
          rows={changesQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={changesQuery.isLoading ? "Loading changes..." : "No changes"}
          columns={[
            { key: "change_type", title: "Change", render: (row) => safeText(row.change_type) },
            { key: "effective_date", title: "Effective", render: (row) => safeText(row.effective_date) },
            { key: "created_at", title: "Created", render: (row) => safeText(row.created_at) }
          ]}
        />

        <FormModal
          open={quantityOpen}
          title="Change quantity"
          submitText="Apply"
          pending={quantityMutation.isPending}
          onClose={() => setQuantityOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await quantityMutation.mutateAsync();
              setQuantityOpen(false);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="change-qty-product" className="mb-1 block text-xs font-medium text-slate-600">
                Product ID
              </label>
              <Input
                id="change-qty-product"
                value={quantityProductId}
                onChange={(event) => setQuantityProductId(event.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="change-qty-value" className="mb-1 block text-xs font-medium text-slate-600">
                New quantity
              </label>
              <Input
                id="change-qty-value"
                value={quantityValue}
                onChange={(event) => setQuantityValue(event.target.value)}
                required
              />
            </div>
          </div>
        </FormModal>
      </section>
    </RouteGuard>
  );
}
