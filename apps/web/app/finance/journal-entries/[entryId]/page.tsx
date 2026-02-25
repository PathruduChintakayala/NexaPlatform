"use client";

import { useEffect, useState } from "react";

import { getFinanceJournalDrilldown } from "../../../../lib/api";

export default function FinanceJournalDrilldownPage({ params }: { params: { entryId: string } }) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getFinanceJournalDrilldown(params.entryId).then((result) => {
      setPayload(result.journal_entry);
    });
  }, [params.entryId]);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Journal Entry Drilldown</h1>
      <p className="text-sm text-slate-600">Entry ID: {params.entryId}</p>
      <pre className="overflow-x-auto rounded border bg-slate-50 p-3 text-xs">{JSON.stringify(payload, null, 2)}</pre>
    </section>
  );
}
