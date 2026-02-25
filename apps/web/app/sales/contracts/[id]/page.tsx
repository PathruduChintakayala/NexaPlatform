"use client";

import React from "react";
import Link from "next/link";

import { RouteGuard } from "../../../../components/route-guard";
import { safeText, useRevenueContract } from "../../hooks";

interface ContractDetailProps {
  params: { id: string };
}

export default function SalesContractDetailPage({ params }: ContractDetailProps) {
  const contractQuery = useRevenueContract(params.id);
  const contract = contractQuery.data;

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales · Contract Detail</h1>
          <p className="text-sm text-slate-600">Contract status, dates, and linked order.</p>
        </header>

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Contract #:</span> {safeText(contract?.contract_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(contract?.status)}
          </p>
          <p>
            <span className="font-medium">Start date:</span> {safeText(contract?.start_date)}
          </p>
          <p>
            <span className="font-medium">End date:</span> {safeText(contract?.end_date)}
          </p>
          <p>
            <span className="font-medium">Linked order:</span>{" "}
            {contract?.order_id ? (
              <Link className="underline" href={`/sales/orders/${contract.order_id}`}>
                {contract.order_id}
              </Link>
            ) : (
              "—"
            )}
          </p>
        </article>
      </section>
    </RouteGuard>
  );
}
