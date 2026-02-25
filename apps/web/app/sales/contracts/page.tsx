"use client";

import React, { useState } from "react";
import Link from "next/link";

import { DataTable } from "../../../components/admin/data-table";
import { RouteGuard } from "../../../components/route-guard";
import { Input } from "../../../components/ui/input";
import { safeText, useRevenueContracts } from "../hooks";

export default function SalesContractsPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const contractsQuery = useRevenueContracts(tenantId, companyCode);

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales · Contracts</h1>
          <p className="text-sm text-slate-600">Contract list and detail links.</p>
        </header>

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={contractsQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={contractsQuery.isLoading ? "Loading contracts..." : "No contracts found"}
          columns={[
            { key: "contract_number", title: "Contract #", render: (row) => safeText(row.contract_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "start_date", title: "Start", render: (row) => safeText(row.start_date) },
            { key: "end_date", title: "End", render: (row) => safeText(row.end_date) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/sales/contracts/${row.id}`}>
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
