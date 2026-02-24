"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listWorkflowExecutions, type ApiToastMessage } from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import { Button } from "../../ui/button";
import { Spinner } from "../../ui/spinner";
import { Td, Th, Table } from "../../ui/table";

interface WorkflowExecutionsTableProps {
  ruleId: string;
  onToast: (message: string | ApiToastMessage) => void;
}

function getCorrelationId(job: { params: Record<string, unknown>; result: Record<string, unknown> | null }) {
  const fromParams = job.params?.correlation_id;
  const fromResult = job.result?.correlation_id;
  if (typeof fromParams === "string") {
    return fromParams;
  }
  if (typeof fromResult === "string") {
    return fromResult;
  }
  return null;
}

export function WorkflowExecutionsTable({ ruleId, onToast }: WorkflowExecutionsTableProps) {
  const [limit, setLimit] = useState(20);

  const executionsQuery = useQuery({
    queryKey: queryKeys.workflows.executions({ rule_id: ruleId, limit }),
    queryFn: () => listWorkflowExecutions({ rule_id: ruleId, limit })
  });

  const rows = executionsQuery.data ?? [];

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {executionsQuery.isLoading ? (
        <div className="inline-flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading executions...
        </div>
      ) : (
        <Table>
          <thead className="bg-slate-50">
            <tr>
              <Th>Job ID</Th>
              <Th>Status</Th>
              <Th>Started</Th>
              <Th>Finished</Th>
              <Th>Correlation</Th>
              <Th>Matched</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <Td>
                  <span className="text-slate-500">No executions found.</span>
                </Td>
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
                <Td />
              </tr>
            ) : (
              rows.map((job) => {
                const correlationId = getCorrelationId(job);
                const matched = job.result && typeof job.result.matched === "boolean" ? String(job.result.matched) : "-";
                const actionsExecutedCount =
                  job.result && typeof job.result.actions_executed_count === "number" ? String(job.result.actions_executed_count) : "-";

                return (
                  <tr key={job.id}>
                    <Td>
                      <Link href={`/crm/admin/workflows/executions/${job.id}`} className="font-mono text-xs text-slate-900 hover:underline">
                        {job.id}
                      </Link>
                    </Td>
                    <Td>{job.status}</Td>
                    <Td>{job.started_at ? new Date(job.started_at).toLocaleString() : "-"}</Td>
                    <Td>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}</Td>
                    <Td>
                      {correlationId ? (
                        <div className="inline-flex items-center gap-2">
                          <span className="font-mono text-xs">{correlationId}</span>
                          <button
                            type="button"
                            className="rounded border border-slate-300 px-1.5 py-0.5 text-xs"
                            onClick={() => {
                              void navigator.clipboard.writeText(correlationId);
                              onToast("Correlation ID copied.");
                            }}
                          >
                            Copy
                          </button>
                        </div>
                      ) : (
                        "-"
                      )}
                    </Td>
                    <Td>{matched}</Td>
                    <Td>{actionsExecutedCount}</Td>
                  </tr>
                );
              })
            )}
          </tbody>
        </Table>
      )}

      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => setLimit((value) => value + 20)}>
          Load more
        </Button>
      </div>
    </div>
  );
}
