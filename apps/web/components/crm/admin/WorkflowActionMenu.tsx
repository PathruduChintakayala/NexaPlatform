"use client";

import React, { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  deleteWorkflowRule,
  dryRunWorkflowRule,
  executeWorkflowRule,
  getErrorToastMessage,
  updateWorkflowRule,
  type ApiToastMessage
} from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import type { WorkflowRuleRead } from "../../../lib/types";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Modal } from "../../ui/modal";
import { Select } from "../../ui/select";

interface WorkflowActionMenuProps {
  rule: WorkflowRuleRead;
  canManage: boolean;
  canExecute: boolean;
  onEdit: (rule: WorkflowRuleRead) => void;
  onToast: (message: string | ApiToastMessage) => void;
}

function summarizeDryRunOutput(result: unknown): string {
  const typed = result as { matched?: boolean; planned_actions?: unknown[] };
  const actionCount = typed.planned_actions?.length ?? 0;
  return typed.matched ? `Matched. Planned actions: ${actionCount}.` : "No match for current inputs.";
}

export function WorkflowActionMenu({ rule, canManage, canExecute, onEdit, onToast }: WorkflowActionMenuProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [dryRunOpen, setDryRunOpen] = useState(false);
  const [executeOpen, setExecuteOpen] = useState(false);
  const [entityType, setEntityType] = useState<"account" | "contact" | "lead" | "opportunity">("lead");
  const [entityId, setEntityId] = useState("");
  const [dryRunResult, setDryRunResult] = useState<unknown>(null);

  const invalidateList = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.list({}) });
  };

  const toggleMutation = useMutation({
    mutationFn: () => updateWorkflowRule(rule.id, { is_active: !rule.is_active }),
    onSuccess: async () => {
      await invalidateList();
      onToast(rule.is_active ? "Workflow disabled." : "Workflow enabled.");
      setOpen(false);
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkflowRule(rule.id),
    onSuccess: async () => {
      await invalidateList();
      onToast("Workflow deleted.");
      setOpen(false);
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const dryRunMutation = useMutation({
    mutationFn: () => dryRunWorkflowRule(rule.id, { entity_type: entityType, entity_id: entityId }),
    onSuccess: (response) => {
      setDryRunResult(response);
      onToast(summarizeDryRunOutput(response));
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const executeMutation = useMutation({
    mutationFn: () => executeWorkflowRule(rule.id, { entity_type: entityType, entity_id: entityId }),
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
      onToast(response.matched ? "Workflow execute matched and planned actions." : "Workflow execute completed with no match.");
      setExecuteOpen(false);
      setOpen(false);
    },
    onError: (error) => onToast(getErrorToastMessage(error))
  });

  const hasActions = canManage || canExecute;

  const dryRunSummary = useMemo(() => {
    const typed = dryRunResult as
      | {
          matched?: boolean;
          planned_actions?: Array<Record<string, unknown>>;
          planned_mutations?: Record<string, unknown>;
        }
      | undefined;

    return {
      matched: typed?.matched ?? false,
      actionCount: typed?.planned_actions?.length ?? 0,
      plannedActions: typed?.planned_actions ?? [],
      plannedMutations: typed?.planned_mutations ?? {}
    };
  }, [dryRunResult]);

  if (!hasActions) {
    return <span className="text-xs text-slate-400">No actions</span>;
  }

  return (
    <>
      <div className="relative">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
          onClick={() => setOpen((value) => !value)}
          aria-label="Open workflow actions"
        >
          ⋯
        </button>

        {open ? (
          <div className="absolute right-0 z-10 mt-1 w-44 rounded-md border border-slate-200 bg-white p-1 shadow-lg">
            {canManage ? (
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100"
                onClick={() => {
                  setOpen(false);
                  onEdit(rule);
                }}
              >
                Edit
              </button>
            ) : null}
            {canManage ? (
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100"
                onClick={() => toggleMutation.mutate()}
                disabled={toggleMutation.isPending}
              >
                {rule.is_active ? "Disable" : "Enable"}
              </button>
            ) : null}
            {canManage ? (
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left text-sm text-red-700 hover:bg-red-50"
                onClick={() => {
                  if (window.confirm(`Delete workflow "${rule.name}"?`)) {
                    deleteMutation.mutate();
                  }
                }}
                disabled={deleteMutation.isPending}
              >
                Delete
              </button>
            ) : null}
            {canExecute ? (
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100"
                onClick={() => {
                  setDryRunResult(null);
                  setDryRunOpen(true);
                  setOpen(false);
                }}
              >
                Dry Run
              </button>
            ) : null}
            {canExecute ? (
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100"
                onClick={() => {
                  setExecuteOpen(true);
                  setOpen(false);
                }}
              >
                Execute
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <Modal open={dryRunOpen} title={`Dry Run: ${rule.name}`} onClose={() => setDryRunOpen(false)}>
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Entity type</label>
              <Select value={entityType} onChange={(event) => setEntityType(event.target.value as typeof entityType)}>
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
          </div>

          <div className="flex justify-end">
            <Button onClick={() => dryRunMutation.mutate()} disabled={dryRunMutation.isPending || !entityId}>
              {dryRunMutation.isPending ? "Running..." : "Run Dry Run"}
            </Button>
          </div>

          {dryRunResult ? (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <p className="text-sm text-slate-700">
                Matched: <strong>{String(dryRunSummary.matched)}</strong> · Planned actions: <strong>{dryRunSummary.actionCount}</strong>
              </p>
              <div>
                <p className="text-xs font-medium text-slate-600">Planned mutations</p>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                  {JSON.stringify(dryRunSummary.plannedMutations, null, 2)}
                </pre>
              </div>
              <div>
                <p className="text-xs font-medium text-slate-600">Planned actions</p>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100">
                  {JSON.stringify(dryRunSummary.plannedActions, null, 2)}
                </pre>
              </div>
            </div>
          ) : null}
        </div>
      </Modal>

      <Modal open={executeOpen} title={`Execute: ${rule.name}`} onClose={() => setExecuteOpen(false)}>
        <div className="space-y-3">
          <p className="text-sm text-slate-600">This will run workflow execution against the selected entity.</p>

          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Entity type</label>
              <Select value={entityType} onChange={(event) => setEntityType(event.target.value as typeof entityType)}>
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
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setExecuteOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => executeMutation.mutate()} disabled={executeMutation.isPending || !entityId}>
              {executeMutation.isPending ? "Executing..." : "Confirm Execute"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
