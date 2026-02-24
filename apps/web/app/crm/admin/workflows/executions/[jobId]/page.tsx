"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getJob } from "../../../../../../lib/api";
import { getCurrentRoles, hasPermission } from "../../../../../../lib/permissions";
import { queryKeys } from "../../../../../../lib/queryKeys";
import { Badge } from "../../../../../../components/ui/badge";
import { Button } from "../../../../../../components/ui/button";
import { Spinner } from "../../../../../../components/ui/spinner";

interface PageProps {
  params: { jobId: string };
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function getCorrelationId(job: { params: Record<string, unknown>; result: Record<string, unknown> | null }) {
  const paramsCorrelation = job.params?.correlation_id;
  const resultCorrelation = job.result?.correlation_id;
  if (typeof paramsCorrelation === "string") {
    return paramsCorrelation;
  }
  if (typeof resultCorrelation === "string") {
    return resultCorrelation;
  }
  return null;
}

function getBadgeTone(status: string): "default" | "success" | "warning" | "danger" {
  if (status === "Succeeded") {
    return "success";
  }
  if (status === "Running" || status === "Queued") {
    return "warning";
  }
  if (status === "Failed") {
    return "danger";
  }
  return "default";
}

export default function WorkflowExecutionDetailPage({ params }: PageProps) {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canRead = hasPermission("crm.workflows.read", roles);
  const [showFullError, setShowFullError] = useState(false);

  const jobQuery = useQuery({
    queryKey: queryKeys.workflows.executionsDetail(params.jobId),
    queryFn: () => getJob(params.jobId),
    enabled: canRead
  });

  if (!canRead) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
        <h1 className="text-lg font-semibold">Workflow Execution</h1>
        <p className="mt-1 text-sm">Permission required: crm.workflows.read</p>
      </div>
    );
  }

  if (jobQuery.isLoading || !jobQuery.data) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="inline-flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading execution...
        </div>
      </div>
    );
  }

  const job = jobQuery.data;
  const paramsPayload = job.params ?? {};
  const resultPayload = job.result ?? {};
  const ruleId = typeof paramsPayload.rule_id === "string" ? paramsPayload.rule_id : null;
  const correlationId = getCorrelationId(job);
  const errorMessage =
    typeof resultPayload.error_message === "string"
      ? resultPayload.error_message
      : typeof paramsPayload.error_message === "string"
        ? paramsPayload.error_message
        : null;

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-mono text-lg text-slate-900">{job.id}</h1>
              <Badge tone={getBadgeTone(job.status)}>{job.status}</Badge>
            </div>
            <p className="mt-1 text-xs text-slate-600">
              Started: {job.started_at ? new Date(job.started_at).toLocaleString() : "-"} · Finished: {job.finished_at ? new Date(job.finished_at).toLocaleString() : "-"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {ruleId ? (
              <Link href={`/crm/admin/workflows/${ruleId}`}>
                <Button variant="secondary">Back to rule</Button>
              </Link>
            ) : null}
            <Link href="/crm/admin/workflows">
              <Button variant="secondary">Back to workflows</Button>
            </Link>
          </div>
        </div>

        {correlationId ? (
          <div className="mt-3 inline-flex items-center gap-2 text-xs text-slate-600">
            <span className="font-mono">Correlation: {correlationId}</span>
            <button
              type="button"
              className="rounded border border-slate-300 px-1.5 py-0.5"
              onClick={() => void navigator.clipboard.writeText(correlationId)}
            >
              Copy
            </button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-medium text-slate-900">Params</p>
          <div className="mt-2 space-y-1 text-sm text-slate-700">
            <p>rule_id: {typeof paramsPayload.rule_id === "string" ? paramsPayload.rule_id : "-"}</p>
            <p>entity_type: {typeof paramsPayload.entity_type === "string" ? paramsPayload.entity_type : "-"}</p>
            <p>entity_id: {typeof paramsPayload.entity_id === "string" ? paramsPayload.entity_id : "-"}</p>
            <p>event_id: {typeof paramsPayload.event_id === "string" ? paramsPayload.event_id : "-"}</p>
          </div>
          <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{prettyJson(paramsPayload)}</pre>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-medium text-slate-900">Result JSON</p>
          <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{prettyJson(resultPayload)}</pre>

          {resultPayload && typeof resultPayload === "object" && "planned_mutations" in resultPayload ? (
            <div className="mt-3">
              <p className="text-xs font-medium text-slate-600">Mutation diffs</p>
              <pre className="mt-1 max-h-36 overflow-auto rounded-md bg-slate-900 p-2 text-xs text-slate-100">
                {prettyJson((resultPayload as { planned_mutations?: unknown }).planned_mutations)}
              </pre>
            </div>
          ) : null}
        </div>
      </div>

      {job.status === "Failed" && errorMessage ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium">Execution failed</p>
          <p className="mt-1">{showFullError ? errorMessage : `${errorMessage.slice(0, 180)}${errorMessage.length > 180 ? "…" : ""}`}</p>
          {errorMessage.length > 180 ? (
            <button type="button" className="mt-2 text-xs underline" onClick={() => setShowFullError((value) => !value)}>
              {showFullError ? "Hide full" : "Show full"}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
