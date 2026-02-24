"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { getErrorMessage, getErrorToastMessage, getOpportunityRevenue, triggerRevenueHandoff } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { OpportunityRead, RevenueDocStatus, RevenueHandoffRequest } from "../../lib/types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Modal } from "../ui/modal";
import { Spinner } from "../ui/spinner";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

function statusTone(status: string): "default" | "success" | "warning" | "danger" {
  if (["APPROVED", "ORDERED", "FULFILLED"].includes(status)) {
    return "success";
  }
  if (status === "REJECTED") {
    return "danger";
  }
  if (status === "SUBMITTED") {
    return "warning";
  }
  return "default";
}

function RevenueRow({
  label,
  doc
}: {
  label: string;
  doc?: RevenueDocStatus;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        {doc ? (
          <p className="text-xs text-slate-500">Updated {doc.updated_at ? new Date(doc.updated_at).toLocaleString() : "-"}</p>
        ) : (
          <p className="text-xs text-slate-500">Not linked</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Badge tone={doc ? statusTone(doc.status) : "default"}>{doc?.status ?? "N/A"}</Badge>
        <Button variant="secondary" disabled>
          Open in Revenue
        </Button>
      </div>
    </div>
  );
}

export function OpportunityRevenuePanel({ opportunity }: { opportunity: OpportunityRead }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const [mode, setMode] = useState<RevenueHandoffRequest["mode"] | null>(null);
  const [sessionIdempotencyKey, setSessionIdempotencyKey] = useState<string | null>(null);

  const shouldLoadRevenue = Boolean(opportunity.closed_won_at || opportunity.revenue_quote_id || opportunity.revenue_order_id);
  const revenueQuery = useQuery({
    queryKey: queryKeys.opportunityRevenue(opportunity.id),
    queryFn: () => getOpportunityRevenue(opportunity.id),
    enabled: shouldLoadRevenue
  });

  const handoffMutation = useMutation({
    mutationFn: async () => {
      if (!mode) {
        throw new Error("Select handoff mode");
      }
      const key = sessionIdempotencyKey ?? crypto.randomUUID();
      if (!sessionIdempotencyKey) {
        setSessionIdempotencyKey(key);
      }
      return triggerRevenueHandoff(opportunity.id, { mode }, key);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunityRevenue(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: ["opportunities"] })
      ]);
      setMessage("Revenue handoff succeeded.");
      setMode(null);
      setSessionIdempotencyKey(null);
    },
    onError: (error) => {
      setMessage(getErrorToastMessage(error));
    }
  });

  const quote = revenueQuery.data?.quote;
  const order = revenueQuery.data?.order;
  const isClosedWon = Boolean(opportunity.closed_won_at);

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">Revenue</h3>
          <p className="text-xs text-slate-500">Handoff and linked quote/order status.</p>
        </div>
      </div>

      <Toast message={message} tone={toastText(message).toLowerCase().includes("succeeded") ? "success" : "error"} />

      {revenueQuery.isLoading ? <Spinner /> : null}
      {revenueQuery.isError ? <p className="text-sm text-red-600">{getErrorMessage(revenueQuery.error)}</p> : null}

      <RevenueRow label="Quote" doc={quote} />
      <RevenueRow label="Order" doc={order} />

      <div className="flex flex-wrap items-center gap-2">
        {!quote ? (
          <Button
            onClick={() => {
              setMode("CREATE_DRAFT_QUOTE");
              setSessionIdempotencyKey(crypto.randomUUID());
              setMessage(null);
            }}
            disabled={!isClosedWon}
            title={!isClosedWon ? "Opportunity must be ClosedWon" : undefined}
          >
            Create Draft Quote
          </Button>
        ) : null}

        {!order ? (
          <Button
            variant="secondary"
            onClick={() => {
              setMode("CREATE_DRAFT_ORDER");
              setSessionIdempotencyKey(crypto.randomUUID());
              setMessage(null);
            }}
            disabled={!isClosedWon}
            title={!isClosedWon ? "Opportunity must be ClosedWon" : undefined}
          >
            Create Draft Order
          </Button>
        ) : null}
      </div>

      <Modal
        open={Boolean(mode)}
        title={mode === "CREATE_DRAFT_QUOTE" ? "Create Draft Quote" : "Create Draft Order"}
        onClose={() => {
          setMode(null);
          setSessionIdempotencyKey(null);
        }}
      >
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Confirm revenue handoff for this ClosedWon opportunity.
          </p>
          <p className="text-xs text-slate-500">Idempotency-Key: {sessionIdempotencyKey}</p>
          <Button onClick={() => handoffMutation.mutate()} disabled={handoffMutation.isPending}>
            {handoffMutation.isPending ? "Submitting..." : "Confirm handoff"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
