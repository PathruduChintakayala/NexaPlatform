"use client";

import { useEffect, useState } from "react";

import { getFinanceInvoiceDrilldown } from "../../../../lib/api";

export default function FinanceInvoiceDrilldownPage({ params }: { params: { invoiceId: string } }) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getFinanceInvoiceDrilldown(params.invoiceId).then((result) => {
      setPayload(result.invoice);
    });
  }, [params.invoiceId]);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Invoice Drilldown</h1>
      <p className="text-sm text-slate-600">Invoice ID: {params.invoiceId}</p>
      <pre className="overflow-x-auto rounded border bg-slate-50 p-3 text-xs">{JSON.stringify(payload, null, 2)}</pre>
    </section>
  );
}
