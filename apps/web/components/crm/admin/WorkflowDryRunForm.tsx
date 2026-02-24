"use client";

import React, { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { dryRunWorkflowRule, executeWorkflowRule, getErrorToastMessage, type ApiToastMessage } from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import type { WorkflowDryRunResponse, WorkflowEntityType } from "../../../lib/types";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Select } from "../../ui/select";

interface WorkflowDryRunFormProps {
  ruleId: string;
  canExecute: boolean;
  onToast: (message: string | ApiToastMessage) => void;
  onShowExecutions?: () => void;
}

function extractBeforeAfter(path: string, plannedMutations: Record<string, unknown>) {
  const value = plannedMutations[path] as { before?: unknown; after?: unknown } | undefined;
  return {
    before: value?.before,
    after: value?.after
  };
}

export function WorkflowDryRunForm({ ruleId, canExecute, onToast, onShowExecutions }: WorkflowDryRunFormProps) {
  const queryClient = useQueryClient();
  const [entityType, setEntityType] = useState<WorkflowEntityType>("lead");
  const [entityId, setEntityId] = useState("");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [result, setResult] = useState<WorkflowDryRunResponse | null>(null);

  const dryRunMutation = useMutation({
    mutationFn: () => dryRunWorkflowRule(ruleId, { entity_type: entityType, entity_id: entityId }),
    onSuccess: (response) => {
      setResult(response);
      onToast(response.matched ? "Dry-run matched conditions." : "No conditions matched.");
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const executeMutation = useMutation({
    mutationFn: () => executeWorkflowRule(ruleId, { entity_type: entityType, entity_id: entityId }),
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.executions({ rule_id: ruleId }) });
      onToast(response.matched ? "Execution completed. Review Executions tab." : "Execution queued — check Executions tab.");
      onShowExecutions?.();
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const plannedMutations = result?.planned_mutations ?? {};
  const plannedActions = useMemo(() => result?.planned_actions ?? [], [result?.planned_actions]);

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="grid gap-3 md:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Entity type</label>
          <Select value={entityType} onChange={(event) => setEntityType(event.target.value as WorkflowEntityType)}>
            <option value="account">account</option>
            <option value="contact">contact</option>
            <option value="lead">lead</option>
            <option value="opportunity">opportunity</option>
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Entity ID</label>
          <Input value={entityId} onChange={(event) => setEntityId(event.target.value)} placeholder="UUID" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID (optional)</label>
          <Input value={legalEntityId} onChange={(event) => setLegalEntityId(event.target.value)} placeholder="UUID" />
        </div>
      </div>

      <div className="flex gap-2">
        <Button onClick={() => dryRunMutation.mutate()} disabled={!entityId || dryRunMutation.isPending}>
          {dryRunMutation.isPending ? "Running..." : "Run Dry Run"}
        </Button>
        {canExecute ? (
          <Button variant="secondary" onClick={() => executeMutation.mutate()} disabled={!entityId || executeMutation.isPending}>
            {executeMutation.isPending ? "Executing..." : "Execute"}
          </Button>
        ) : null}
      </div>

      {result && !result.matched ? <p className="text-sm text-slate-600">No conditions matched.</p> : null}

      {result ? (
        <div className="space-y-3">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
            Matched: <strong>{String(result.matched)}</strong> · Planned actions: <strong>{plannedActions.length}</strong>
          </div>

          {plannedActions.map((action, index) => {
            const typed = action as { type?: string; path?: string; title?: string; due_in_days?: number; notification_type?: string; payload?: unknown };
            if (typed.type === "SET_FIELD") {
              const mutation = extractBeforeAfter(typed.path ?? "", plannedMutations);
              return (
                <div key={`set-${index}`} className="rounded-md border border-slate-200 p-3">
                  <p className="text-sm font-medium text-slate-900">SET_FIELD</p>
                  <p className="text-xs text-slate-600">Path: {typed.path}</p>
                  <p className="text-xs text-slate-600">Before: {JSON.stringify(mutation.before)}</p>
                  <p className="text-xs text-slate-600">After: {JSON.stringify(mutation.after)}</p>
                </div>
              );
            }

            if (typed.type === "CREATE_TASK") {
              return (
                <div key={`task-${index}`} className="rounded-md border border-slate-200 p-3">
                  <p className="text-sm font-medium text-slate-900">CREATE_TASK</p>
                  <p className="text-xs text-slate-600">Would create task: {typed.title ?? "Untitled"}</p>
                  <p className="text-xs text-slate-600">Due in days: {typed.due_in_days ?? "-"}</p>
                </div>
              );
            }

            if (typed.type === "NOTIFY") {
              return (
                <div key={`notify-${index}`} className="rounded-md border border-slate-200 p-3">
                  <p className="text-sm font-medium text-slate-900">NOTIFY</p>
                  <p className="text-xs text-slate-600">Would send: {typed.notification_type ?? "Unknown"}</p>
                  <pre className="mt-1 max-h-28 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                    {JSON.stringify(typed.payload ?? {}, null, 2)}
                  </pre>
                </div>
              );
            }

            return (
              <div key={`raw-${index}`} className="rounded-md border border-slate-200 p-3">
                <p className="text-sm font-medium text-slate-900">Action</p>
                <pre className="mt-1 max-h-28 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                  {JSON.stringify(action, null, 2)}
                </pre>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
