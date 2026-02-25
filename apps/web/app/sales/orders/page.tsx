"use client";

import React, { useState } from "react";
import Link from "next/link";

import { DataTable } from "../../../components/admin/data-table";
import { RouteGuard } from "../../../components/route-guard";
import { Input } from "../../../components/ui/input";
import { safeText, useRevenueOrders } from "../hooks";

export default function SalesOrdersPage() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const ordersQuery = useRevenueOrders(tenantId, companyCode);

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales · Orders</h1>
          <p className="text-sm text-slate-600">Order list and detail links.</p>
        </header>

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <DataTable
          rows={ordersQuery.data ?? []}
          rowKey={(row) => row.id}
          emptyText={ordersQuery.isLoading ? "Loading orders..." : "No orders found"}
          columns={[
            { key: "order_number", title: "Order #", render: (row) => safeText(row.order_number) },
            { key: "status", title: "Status", render: (row) => safeText(row.status) },
            { key: "currency", title: "Currency", render: (row) => safeText(row.currency) },
            { key: "total", title: "Total", render: (row) => safeText(row.total) },
            {
              key: "detail",
              title: "Detail",
              render: (row) => (
                <Link className="text-sm text-slate-700 underline" href={`/sales/orders/${row.id}`}>
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
