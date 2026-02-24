"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteWorkflowRule, getErrorToastMessage, getWorkflowRule, type ApiToastMessage, updateWorkflowRule } from "../../../../../lib/api";
import { getCurrentRoles, hasPermission } from "../../../../../lib/permissions";
import { queryKeys } from "../../../../../lib/queryKeys";
import { WorkflowCreateModal } from "../../../../../components/crm/admin/WorkflowCreateModal";
import { WorkflowDryRunForm } from "../../../../../components/crm/admin/WorkflowDryRunForm";
import { WorkflowExecutionsTable } from "../../../../../components/crm/admin/WorkflowExecutionsTable";
import { WorkflowRuleDetailHeader } from "../../../../../components/crm/admin/WorkflowRuleDetailHeader";
import { Spinner } from "../../../../../components/ui/spinner";
import { Tabs } from "../../../../../components/ui/tabs";
import { Toast, type ToastMessageValue } from "../../../../../components/ui/toast";

interface PageProps {
  params: { id: string };
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function WorkflowRuleDetailPage({ params }: PageProps) {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canRead = hasPermission("crm.workflows.read", roles);
  const canManage = hasPermission("crm.workflows.manage", roles);
  const canExecute = hasPermission("crm.workflows.execute", roles);

  const router = useRouter();
  const queryClient = useQueryClient();

  const [toast, setToast] = useState<ToastMessageValue>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [defaultTab, setDefaultTab] = useState("dry-run");
  const [tabsEpoch, setTabsEpoch] = useState(0);

  const ruleQuery = useQuery({
    queryKey: queryKeys.workflows.detail(params.id),
    queryFn: () => getWorkflowRule(params.id),
    enabled: canRead
  });

  const toggleMutation = useMutation({
    mutationFn: () => {
      if (!ruleQuery.data) {
        throw new Error("Workflow not loaded");
      }
      return updateWorkflowRule(ruleQuery.data.id, { is_active: !ruleQuery.data.is_active });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.detail(params.id) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.list({}) });
      setToast("Workflow status updated.");
    },
    onError: (error) => setToast(getErrorToastMessage(error))
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkflowRule(params.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.list({}) });
      setToast("Workflow deleted.");
      router.push("/crm/admin/workflows");
    },
    onError: (error) => setToast(getErrorToastMessage(error))
  });

  if (!canRead) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
        <h1 className="text-lg font-semibold">Workflow Rule</h1>
        <p className="mt-1 text-sm">Permission required: crm.workflows.read</p>
      </div>
    );
  }

  if (ruleQuery.isLoading || !ruleQuery.data) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="inline-flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading workflow rule...
        </div>
      </div>
    );
  }

  const rule = ruleQuery.data;

  const tabItems = [
    {
      id: "dry-run",
      label: "Dry Run",
      content: (
        <WorkflowDryRunForm
          ruleId={rule.id}
          canExecute={canExecute}
          onToast={(message) => setToast(message)}
          onShowExecutions={() => {
            setDefaultTab("executions");
            setTabsEpoch((value) => value + 1);
          }}
        />
      )
    },
    {
      id: "executions",
      label: "Executions",
      content: <WorkflowExecutionsTable ruleId={rule.id} onToast={(message: string | ApiToastMessage) => setToast(message)} />
    }
  ];

  return (
    <div className="space-y-6">
      <WorkflowRuleDetailHeader
        rule={rule}
        canManage={canManage}
        onToggleActive={() => toggleMutation.mutate()}
        togglePending={toggleMutation.isPending}
        onEdit={() => setEditOpen(true)}
        onDelete={() => {
          if (window.confirm(`Delete workflow "${rule.name}"?`)) {
            deleteMutation.mutate();
          }
        }}
        deletePending={deleteMutation.isPending}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div>
            <p className="text-xs font-medium text-slate-600">Rule JSON</p>
            <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
              {prettyJson(rule.condition_json)}
            </pre>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-600">Actions JSON</p>
            <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
              {prettyJson(rule.actions_json)}
            </pre>
          </div>
          {canManage ? <p className="text-xs text-slate-500">Manage permission enabled: use Edit to update this rule.</p> : null}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <Tabs key={tabsEpoch} items={tabItems} defaultTab={defaultTab} />
        </div>
      </div>

      {canManage ? (
        <WorkflowCreateModal
          open={editOpen}
          mode="edit"
          initialRule={rule}
          onClose={() => setEditOpen(false)}
          onSuccess={(message) => {
            setToast(message);
            void queryClient.invalidateQueries({ queryKey: queryKeys.workflows.detail(params.id) });
          }}
          onError={(message) => setToast(message)}
        />
      ) : null}

      <Toast message={toast} tone={typeof toast === "string" ? "success" : toast?.message ? "error" : "info"} />
    </div>
  );
}
