"use client";

import React from "react";
import Link from "next/link";

import { RouteGuard } from "../../components/route-guard";

export default function OpsHubPage() {
  return (
    <RouteGuard requiredRoles={["ops", "admin", "system.admin"]}>
      <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Ops Hub</h1>
          <p className="text-sm text-slate-600">Subscriptions, billing, payments, and ledger operations.</p>
        </header>

        <div className="grid gap-3 md:grid-cols-2">
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/ops/plans">
            Plans
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/ops/subscriptions">
            Subscriptions
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/ops/invoices">
            Invoices
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/ops/payments">
            Payments
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/ops/journal-entries">
            Journal Entries
          </Link>
        </div>
      </section>
    </RouteGuard>
  );
}
