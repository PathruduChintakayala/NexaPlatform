"use client";

import React from "react";
import { useState } from "react";

import { getFinanceReconciliation } from "../../../lib/api";
import type { FinanceReconciliationReport } from "../../../lib/types";

export default function FinanceReconciliationPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [startDate, setStartDate] = useState("2026-02-01");
  const [endDate, setEndDate] = useState("2026-02-28");
  const [report, setReport] = useState<FinanceReconciliationReport | null>(null);

  async function loadReport() {
    const result = await getFinanceReconciliation({
      tenant_id: tenantId,
      company_code: companyCode,
      start_date: startDate,
      end_date: endDate
    });
    setReport(result);
  }

  return (
    <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header>
        <h1 className="text-xl font-semibold">Reconciliation</h1>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <input className="rounded border p-2 text-sm" value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
        <input className="rounded border p-2 text-sm" value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        <input className="rounded border p-2 text-sm" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        <input className="rounded border p-2 text-sm" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
      </div>

      <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white" onClick={loadReport} type="button">
        Load Reconciliation
      </button>

      <article className="space-y-2">
        <h2 className="text-sm font-semibold">Invoice vs Payment mismatches</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Invoice</th>
              <th className="py-2">Delta</th>
              <th className="py-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {report?.invoice_payment_mismatches.map((row) => (
              <tr key={row.invoice_id} className="border-b">
                <td className="py-2">{row.invoice_number}</td>
                <td className="py-2">{row.delta}</td>
                <td className="py-2">
                  <a className="text-slate-700 underline" href={`/finance/invoices/${row.invoice_id}`}>
                    Invoice
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      <article className="space-y-2">
        <h2 className="text-sm font-semibold">Ledger link mismatches</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Type</th>
              <th className="py-2">Issue</th>
              <th className="py-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {report?.ledger_link_mismatches.map((row) => (
              <tr key={`${row.entity_type}-${row.entity_id}-${row.issue}`} className="border-b">
                <td className="py-2">{row.entity_type}</td>
                <td className="py-2">{row.issue}</td>
                <td className="py-2">
                  {row.entity_type === "invoice" && (
                    <a className="text-slate-700 underline" href={`/finance/invoices/${row.entity_id}`}>
                      Invoice
                    </a>
                  )}
                  {row.entity_type === "payment" && (
                    <a className="text-slate-700 underline" href={`/finance/payments/${row.entity_id}`}>
                      Payment
                    </a>
                  )}
                  {row.ledger_journal_entry_id && (
                    <a className="ml-3 text-slate-700 underline" href={`/finance/journal-entries/${row.ledger_journal_entry_id}`}>
                      Journal
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
