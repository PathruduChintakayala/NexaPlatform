"use client";

import React from "react";
import { useState } from "react";

import { getFinanceArAging } from "../../../lib/api";
import type { FinanceARAgingReport } from "../../../lib/types";

export default function FinanceARAgingPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [asOfDate, setAsOfDate] = useState("2026-02-25");
  const [report, setReport] = useState<FinanceARAgingReport | null>(null);

  async function loadReport() {
    const result = await getFinanceArAging({
      tenant_id: tenantId,
      company_code: companyCode,
      as_of_date: asOfDate
    });
    setReport(result);
  }

  return (
    <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header>
        <h1 className="text-xl font-semibold">AR Aging</h1>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <input className="rounded border p-2 text-sm" value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
        <input className="rounded border p-2 text-sm" value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        <input className="rounded border p-2 text-sm" type="date" value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} />
      </div>

      <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white" onClick={loadReport} type="button">
        Load AR Aging
      </button>

      <p className="text-sm">Total amount due: {report?.total_amount_due ?? "-"}</p>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2">Invoice</th>
            <th className="py-2">Due</th>
            <th className="py-2">Days</th>
            <th className="py-2">Amount Due</th>
            <th className="py-2">Detail</th>
          </tr>
        </thead>
        <tbody>
          {report?.rows.map((row) => (
            <tr key={row.invoice_id} className="border-b">
              <td className="py-2">{row.invoice_number}</td>
              <td className="py-2">{row.due_date ?? "-"}</td>
              <td className="py-2">{row.days_overdue}</td>
              <td className="py-2">{row.amount_due}</td>
              <td className="py-2">
                <a className="text-slate-700 underline" href={`/finance/invoices/${row.invoice_id}`}>
                  Open
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
