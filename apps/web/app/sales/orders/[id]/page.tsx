"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiErrorBanner } from "../../../../components/admin/api-error-banner";
import { DataTable } from "../../../../components/admin/data-table";
import { RouteGuard } from "../../../../components/route-guard";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { confirmRevenueOrder, createRevenueContractFromOrder } from "../../../../lib/api/revenue";
import { queryKeys } from "../../../../lib/queryKeys";
import { formatApiError, safeText, useRevenueContract, useRevenueContracts, useRevenueOrder } from "../../hooks";

interface OrderDetailProps {
  params: { id: string };
}

export default function SalesOrderDetailPage({ params }: OrderDetailProps) {
  const orderId = params.id;
  const [tenantId, setTenantId] = useState("tenant-a");
  const [companyCode, setCompanyCode] = useState("C1");
  const [createdContractId, setCreatedContractId] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const orderQuery = useRevenueOrder(orderId);
  const contractsQuery = useRevenueContracts(tenantId, companyCode);
  const createdContractQuery = useRevenueContract(createdContractId);

  const confirmMutation = useMutation({
    mutationFn: () => confirmRevenueOrder(orderId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.order(orderId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.orders({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  const createContractMutation = useMutation({
    mutationFn: () => createRevenueContractFromOrder(orderId),
    onSuccess: async (contract) => {
      setCreatedContractId(contract.id);
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.order(orderId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.sales.contracts({ tenant_id: tenantId, company_code: companyCode }) });
    }
  });

  const order = orderQuery.data;
  const linkedContract = useMemo(() => {
    const fromList = (contractsQuery.data ?? []).find((item) => item.order_id === order?.id);
    return createdContractQuery.data ?? fromList ?? null;
  }, [contractsQuery.data, createdContractQuery.data, order?.id]);

  return (
    <RouteGuard requiredRoles={["sales", "admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Sales · Order Detail</h1>
          <p className="text-sm text-slate-600">Order status, totals, lines, and contract actions.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-3 md:grid-cols-2">
          <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" />
          <Input value={companyCode} onChange={(event) => setCompanyCode(event.target.value)} placeholder="Company" />
        </div>

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <p>
            <span className="font-medium">Order #:</span> {safeText(order?.order_number)}
          </p>
          <p>
            <span className="font-medium">Status:</span> {safeText(order?.status)}
          </p>
          <p>
            <span className="font-medium">Subtotal:</span> {safeText(order?.subtotal)}
          </p>
          <p>
            <span className="font-medium">Discount:</span> {safeText(order?.discount_total)}
          </p>
          <p>
            <span className="font-medium">Tax:</span> {safeText(order?.tax_total)}
          </p>
          <p>
            <span className="font-medium">Total:</span> {safeText(order?.total)}
          </p>

          <div className="mt-3 flex gap-2">
            <Button
              variant="secondary"
              disabled={order?.status !== "DRAFT" || confirmMutation.isPending}
              onClick={async () => {
                try {
                  await confirmMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Confirm order
            </Button>
            <Button
              disabled={order?.status !== "CONFIRMED" || createContractMutation.isPending}
              onClick={async () => {
                try {
                  await createContractMutation.mutateAsync();
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              Create contract
            </Button>
          </div>
        </article>

        <DataTable
          rows={order?.lines ?? []}
          rowKey={(row) => row.id}
          emptyText={orderQuery.isLoading ? "Loading lines..." : "No lines"}
          columns={[
            { key: "product_id", title: "Product", render: (row) => safeText(row.product_id) },
            { key: "pricebook_item_id", title: "Pricebook Item", render: (row) => safeText(row.pricebook_item_id) },
            { key: "quantity", title: "Qty", render: (row) => safeText(row.quantity) },
            { key: "unit_price", title: "Unit", render: (row) => safeText(row.unit_price) },
            { key: "line_total", title: "Line Total", render: (row) => safeText(row.line_total) }
          ]}
        />

        <article className="rounded-lg border border-slate-200 p-4 text-sm">
          <h2 className="font-semibold">Linked contract</h2>
          {linkedContract ? (
            <p className="mt-1">
              {safeText(linkedContract.contract_number)} · {safeText(linkedContract.status)} ·
              <Link className="ml-1 underline" href={`/sales/contracts/${linkedContract.id}`}>
                Open contract
              </Link>
            </p>
          ) : (
            <p className="mt-1 text-slate-500">No linked contract.</p>
          )}
        </article>
      </section>
    </RouteGuard>
  );
}
