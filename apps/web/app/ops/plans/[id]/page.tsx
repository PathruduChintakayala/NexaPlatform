"use client";

import React from "react";

import { DataTable } from "../../../../components/admin/data-table";
import { RouteGuard } from "../../../../components/route-guard";
import { safeText, useOpsPlan } from "../../hooks";

interface PlanDetailProps {
  params: { id: string };
}

export default function OpsPlanDetailPage({ params }: PlanDetailProps) {
  const planQuery = useOpsPlan(params.id);
  const plan = planQuery.data;

  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops · Plan Detail</h1>
          <p className="text-sm text-slate-600">Plan metadata and included items.</p>
        </header>

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Name:</span> {safeText(plan?.name)}
          </p>
          <p>
            <span className="font-medium">Code:</span> {safeText(plan?.code)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(plan?.status)}
          </p>
          <p>
            <span className="font-medium">Billing period:</span> {safeText(plan?.billing_period)}
          </p>
          <p>
            <span className="font-medium">Currency:</span> {safeText(plan?.currency)}
          </p>
          <p>
            <span className="font-medium">Default pricebook:</span> {safeText(plan?.default_pricebook_id)}
          </p>
        </article>

        <DataTable
          rows={plan?.items ?? []}
          rowKey={(row) => row.id}
          emptyText={planQuery.isLoading ? "Loading plan items..." : "No items found"}
          columns={[
            { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
            { key: "pricebook_item_id", title: "Pricebook Item", render: (row) => safeText(row.pricebook_item_id) },
            { key: "quantity_default", title: "Default Qty", render: (row) => safeText(row.quantity_default) },
            { key: "unit_price_snapshot", title: "Unit", render: (row) => safeText(row.unit_price_snapshot) }
          ]}
        />
      </section>
    </RouteGuard>
  );
}
