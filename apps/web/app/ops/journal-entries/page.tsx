"use client";

import React, { useState } from "react";
import Link from "next/link";

import { DataTable } from "../../../components/admin/data-table";
import { RouteGuard } from "../../../components/route-guard";
import { Input } from "../../../components/ui/input";
import { safeText, useOpsJournalEntries } from "../hooks";

export default function OpsJournalEntriesPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const entriesQuery = useOpsJournalEntries({
    tenant_id: tenantId,
    company_code: companyCode,
    start_date: startDate || undefined,
    end_date: endDate || undefined
  });

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Journal Entries</h1>
          <p className="text-sm text-slate-600">Journal posting history and detail links.</p>
        </header>

        <div className="grid gap-3 md:grid-cols-4">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
          <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </div>

        <DataTable
          rows={entriesQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={entriesQuery.isLoading ? "Loading journal entries..." : "No journal entries found"}
          columns={[
            { key: "entry_date", title: "Date", render: (row) => safeText(row.entry_date) },
            { key: "posting_status", title: "Posting", render: (row) => safeText(row.posting_status) },
            { key: "source_module", title: "Module", render: (row) => safeText(row.source_module) },
            { key: "source_type", title: "Type", render: (row) => safeText(row.source_type) },
            { key: "source_id", title: "Source", render: (row) => safeText(row.source_id) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/ops/journal-entries/${row.id}`}>
                  Open
                </Link>
              )
            }
          ]}
        />
      </section>
    </RouteGuard>
  );
}
