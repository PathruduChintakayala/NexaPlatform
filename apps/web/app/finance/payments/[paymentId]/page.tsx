"use client";

import { useEffect, useState } from "react";

import { getFinancePaymentDrilldown } from "../../../../lib/api";

export default function FinancePaymentDrilldownPage({ params }: { params: { paymentId: string } }) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getFinancePaymentDrilldown(params.paymentId).then((result) => {
      setPayload(result.payment);
    });
  }, [params.paymentId]);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">Payment Drilldown</h1>
      <p className="text-sm text-slate-600">Payment ID: {params.paymentId}</p>
      <pre className="overflow-x-auto rounded border bg-slate-50 p-3 text-xs">{JSON.stringify(payload, null, 2)}</pre>
    </section>
  );
}
