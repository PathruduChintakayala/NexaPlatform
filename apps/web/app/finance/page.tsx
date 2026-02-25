"use client";

import React from "react";
import { useState } from "react";

import { getFinanceCashSummary, getFinanceRevenueSummary } from "../../lib/api/reports";
import type { FinanceCashSummaryReport, FinanceRevenueSummaryReport } from "../../lib/types";

export default function FinancePage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [startDate, setStartDate] = useState("2026-02-01");
  const [endDate, setEndDate] = useState("2026-02-28");
  const [cashSummary, setCashSummary] = useState<FinanceCashSummaryReport | null>(null);
  const [revenueSummary, setRevenueSummary] = useState<FinanceRevenueSummaryReport | null>(null);

  async function load() {
    const params = { tenant_id: tenantId, company_code: companyCode, start_date: startDate, end_date: endDate };
    const [cash, revenue] = await Promise.all([getFinanceCashSummary(params), getFinanceRevenueSummary(params)]);
    setCashSummary(cash);
    setRevenueSummary(revenue);
  }

  return (
    <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header>
        <h1 className="text-xl font-semibold">Finance Reporting</h1>
        <p className="text-sm text-slate-600">Reporting and reconciliation overview with drilldowns.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <input className="rounded border p-2 text-sm" value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
        <input className="rounded border p-2 text-sm" value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        <input className="rounded border p-2 text-sm" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        <input className="rounded border p-2 text-sm" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
      </div>

      <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white" onClick={load} type="button">
        Load summaries
      </button>

      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-lg border border-slate-200 p-4">
          <h2 className="font-medium">Cash Summary</h2>
          <p className="mt-2 text-sm">Received: {cashSummary?.received_total ?? "-"}</p>
          <p className="text-sm">Refunded: {cashSummary?.refunded_total ?? "-"}</p>
          <p className="text-sm">Net Cash: {cashSummary?.net_cash_total ?? "-"}</p>
        </article>
        <article className="rounded-lg border border-slate-200 p-4">
          <h2 className="font-medium">Revenue Summary</h2>
          <p className="mt-2 text-sm">Invoiced: {revenueSummary?.invoiced_total ?? "-"}</p>
          <p className="text-sm">Credits: {revenueSummary?.credit_note_total ?? "-"}</p>
          <p className="text-sm">Net Revenue: {revenueSummary?.net_revenue_total ?? "-"}</p>
        </article>
      </div>

      <nav className="flex flex-wrap gap-3 text-sm text-slate-700">
        <a className="rounded border border-slate-300 px-3 py-2 hover:bg-slate-100" href="/finance/ar-aging">
          AR Aging
        </a>
        <a className="rounded border border-slate-300 px-3 py-2 hover:bg-slate-100" href="/finance/trial-balance">
          Trial Balance
        </a>
        <a className="rounded border border-slate-300 px-3 py-2 hover:bg-slate-100" href="/finance/reconciliation">
          Reconciliation
        </a>
      </nav>
    </section>
  );
}
