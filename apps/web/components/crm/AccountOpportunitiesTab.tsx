"use client";

import { useQuery } from "@tanstack/react-query";

import { getErrorMessage, listOpportunities } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Badge } from "../ui/badge";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";

function opportunityStatus(row: { closed_won_at: string | null; closed_lost_at: string | null }) {
  if (row.closed_won_at) {
    return "Won";
  }
  if (row.closed_lost_at) {
    return "Lost";
  }
  return "Open";
}

export function AccountOpportunitiesTab({ accountId }: { accountId: string }) {
  const query = useQuery({
    queryKey: queryKeys.opportunities({ account_id: accountId }),
    queryFn: () => listOpportunities({ account_id: accountId })
  });

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold">Opportunities</h3>
      {query.isLoading ? (
        <Spinner />
      ) : query.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(query.error)}</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Stage</Th>
              <Th>Amount</Th>
              <Th>Expected Close</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {query.data?.map((item) => {
              const status = opportunityStatus(item);
              return (
                <tr key={item.id}>
                  <Td>{item.name}</Td>
                  <Td>{item.stage_id}</Td>
                  <Td>{`${item.amount} ${item.currency_code}`}</Td>
                  <Td>{item.expected_close_date ?? "-"}</Td>
                  <Td>
                    <Badge tone={status === "Won" ? "success" : status === "Lost" ? "danger" : "default"}>{status}</Badge>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </div>
  );
}
