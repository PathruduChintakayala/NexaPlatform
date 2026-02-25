"use client";

import React from "react";
import Link from "next/link";

import { RouteGuard } from "../../components/route-guard";

export default function SalesHubPage() {
  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales Hub</h1>
          <p className="text-sm text-slate-600">Catalog and revenue workflows.</p>
        </header>
        <div className="grid gap-3 md:grid-cols-2">
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/sales/products">
            Products
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/sales/pricebooks">
            Pricebooks
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/sales/quotes">
            Quotes
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/sales/orders">
            Orders
          </Link>
          <Link className="rounded border border-slate-300 p-3 text-sm hover:bg-slate-100" href="/sales/contracts">
            Contracts
          </Link>
        </div>
      </section>
    </RouteGuard>
  );
}
