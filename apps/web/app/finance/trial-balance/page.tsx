"use client";

import React from "react";
import { useState } from "react";

import { getFinanceTrialBalance } from "../../../lib/api";
import type { FinanceTrialBalanceReport } from "../../../lib/types";

export default function FinanceTrialBalancePage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [startDate, setStartDate] = useState("2026-02-01");
  const [endDate, setEndDate] = useState("2026-02-28");
  const [report, setReport] = useState<FinanceTrialBalanceReport | null>(null);

  async function loadReport() {
    const result = await getFinanceTrialBalance({
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
        <h1 className="text-xl font-semibold">Trial Balance</h1>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <input className="rounded border p-2 text-sm" value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
        <input className="rounded border p-2 text-sm" value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        <input className="rounded border p-2 text-sm" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        <input className="rounded border p-2 text-sm" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
      </div>

      <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white" onClick={loadReport} type="button">
        Load Trial Balance
      </button>

      <p className="text-sm">
        Debits: {report?.total_debits ?? "-"} | Credits: {report?.total_credits ?? "-"}
      </p>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2">Account</th>
            <th className="py-2">Debit</th>
            <th className="py-2">Credit</th>
            <th className="py-2">Net</th>
          </tr>
        </thead>
        <tbody>
          {report?.rows.map((row) => (
            <tr key={row.account_id} className="border-b">
              <td className="py-2">{row.account_code} - {row.account_name}</td>
              <td className="py-2">{row.debit_total}</td>
              <td className="py-2">{row.credit_total}</td>
              <td className="py-2">{row.net_balance}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
