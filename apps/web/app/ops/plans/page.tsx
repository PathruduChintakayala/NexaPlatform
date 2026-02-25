"use client";

import React, { useState } from "react";
import Link from "next/link";

import { DataTable } from "../../../components/admin/data-table";
import { RouteGuard } from "../../../components/route-guard";
import { Input } from "../../../components/ui/input";
import { safeText, useOpsPlans } from "../hooks";

export default function OpsPlansPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const plansQuery = useOpsPlans(tenantId, companyCode);

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Plans</h1>
          <p className="text-sm text-slate-600">Plan catalog and detail links.</p>
        </header>

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={plansQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={plansQuery.isLoading ? "Loading plans..." : "No plans found"}
          columns={[
            { key: "code", title: "Code", render: (row) => safeText(row.code) },
            { key: "name", title: "Name", render: (row) => safeText(row.name) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "period", title: "Billing", render: (row) => safeText(row.billing_period) },
            { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/ops/plans/${row.id}`}>
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
