import React from "react";
import Link from "next/link";

import { RouteGuard } from "../../components/route-guard";

export default function ReportsHubPage() {
  return (
    <RouteGuard requiredRoles={["finance", "ops", "admin", "system.admin"]}>
      <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Reports Hub</h1>
          <p className="text-sm text-slate-600">Finance reports and reconciliation views.</p>
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/finance">
            Finance Overview
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/finance/ar-aging">
            AR Aging
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/finance/trial-balance">
            Trial Balance
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/finance/reconciliation">
            Reconciliation
          </Link>
        </div>
      </section>
    </RouteGuard>
  );
}
