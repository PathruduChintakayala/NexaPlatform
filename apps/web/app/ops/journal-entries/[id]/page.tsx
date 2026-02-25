"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { reverseJournalEntry } from "../../../../lib/api/ledger";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useOpsJournalEntry } from "../../hooks";

interface JournalEntryDetailProps {
  params: { id: string };
}

export default function OpsJournalEntryDetailPage({ params }: JournalEntryDetailProps) {
  const entryId = params.id;
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [createdBy, setCreatedBy] = useState("ops.user");

  const queryClient = useQueryClient();
  const entryQuery = useOpsJournalEntry(entryId);
  const entry = entryQuery.data;

  const reverseMutation = useMutation({
    mutationFn: () => reverseJournalEntry(entryId, { reason, created_by: createdBy }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.ops.journalEntry(entryId) });
      if (entry) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.ops.journalEntries({ tenant_id: entry.tenant_id, company_code: entry.company_code }) });
      }
    }
  });

  const canReverse = entry?.posting_status === "POSTED";

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Journal Entry Detail</h1>
          <p className="text-sm text-slate-600">Ledger lines and reversal control.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Entry date:</span> {safeText(entry?.entry_date)}
          </p>
          <p>
            <span className="font-medium">Description:</span> {safeText(entry?.description)}
          </p>
          <p>
            <span className="font-medium">Posting status:</span> {safeText(entry?.posting_status)}
          </p>
          <p>
            <span className="font-medium">Source:</span> {safeText(entry?.source_module)} · {safeText(entry?.source_type)} · {safeText(entry?.source_id)}
          </p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <Input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reverse reason" />
            <Input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} placeholder="Created by" />
          </div>
          <div className="mt-3">
            <Button
              variant="secondary"
              disabled={!canReverse || !reason || reverseMutation.isPending}
              onClick={async () => {
                try {
                  await reverseMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Reverse entry
            </Button>
          </div>
        </article>

        <DataTable
          rows={entry?.lines ?? []}
          rowKey={(row) => row.id}
          emptyText={entryQuery.isLoading ? "Loading lines..." : "No lines"}
          columns={[
            { key: "account_id", title: "Account", render: (row) => safeText(row.account_id) },
            { key: "debit_amount", title: "Debit", render: (row) => safeText(row.debit_amount) },
            { key: "credit_amount", title: "Credit", render: (row) => safeText(row.credit_amount) },
            { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
            { key: "amount_company_base", title: "Base", render: (row) => safeText(row.amount_company_base) },
            { key: "memo", title: "Memo", render: (row) => safeText(row.memo) }
          ]}
        />
      </section>
    </RouteGuard>
  );
}
