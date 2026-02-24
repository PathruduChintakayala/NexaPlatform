"use client";

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listWorkflowRules, type ApiToastMessage } from "../../../../lib/api";
import { getCurrentRoles, hasPermission } from "../../../../lib/permissions";
import { queryKeys } from "../../../../lib/queryKeys";
import type { WorkflowRuleRead } from "../../../../lib/types";
import { WorkflowFormModal } from "../../../../components/crm/admin/WorkflowFormModal";
import { WorkflowListTable } from "../../../../components/crm/admin/WorkflowListTable";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Spinner } from "../../../../components/ui/spinner";
import { Toast, type ToastMessageValue } from "../../../../components/ui/toast";

const triggerEventOptions = [
  "",
  "crm.lead.created",
  "crm.lead.updated",
  "crm.opportunity.stage_changed",
  "crm.opportunity.closed_won",
  "crm.account.created"
] as const;

const pageSize = 25;

interface WorkflowFilters {
  trigger_event?: string;
  legal_entity_id?: string;
  active?: boolean;
}

export default function WorkflowRulesPage() {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canRead = hasPermission("crm.workflows.read", roles);
  const canManage = hasPermission("crm.workflows.manage", roles);
  const canExecute = hasPermission("crm.workflows.execute", roles);

  const [toast, setToast] = useState<ToastMessageValue>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<WorkflowRuleRead | null>(null);

  const [triggerDraft, setTriggerDraft] = useState("");
  const [legalEntityDraft, setLegalEntityDraft] = useState("");
  const [globalScope, setGlobalScope] = useState(true);
  const [activeDraft, setActiveDraft] = useState<"all" | "active" | "inactive">("all");

  const [appliedFilters, setAppliedFilters] = useState<WorkflowFilters>({});
  const [page, setPage] = useState(1);

  const listQuery = useQuery({
    queryKey: queryKeys.workflows.list({ ...appliedFilters, page, page_size: pageSize }),
    queryFn: () => listWorkflowRules({ ...appliedFilters, limit: 500 }),
    enabled: canRead
  });

  const filteredRules = useMemo(() => {
    const rules = listQuery.data ?? [];
    if (appliedFilters.active === undefined) {
      return rules;
    }
    return rules.filter((rule) => rule.is_active === appliedFilters.active);
  }, [appliedFilters.active, listQuery.data]);

  const totalPages = Math.max(1, Math.ceil(filteredRules.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedRules = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filteredRules.slice(start, start + pageSize);
  }, [filteredRules, safePage]);

  function applyFilters() {
    const nextFilters: WorkflowFilters = {
      trigger_event: triggerDraft || undefined,
      legal_entity_id: globalScope ? undefined : legalEntityDraft || undefined,
      active: activeDraft === "all" ? undefined : activeDraft === "active"
    };
    setAppliedFilters(nextFilters);
    setPage(1);
  }

  function clearFilters() {
    setTriggerDraft("");
    setLegalEntityDraft("");
    setGlobalScope(true);
    setActiveDraft("all");
    setAppliedFilters({});
    setPage(1);
  }

  if (!canRead) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
        <h1 className="text-lg font-semibold">Workflow Rules</h1>
        <p className="mt-1 text-sm">Permission required: crm.workflows.read</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Workflow Rules</h1>
            <p className="mt-1 text-sm text-slate-500">Manage workflow rules, scopes, and execution actions.</p>
          </div>
          {canManage ? <Button onClick={() => setCreateOpen(true)}>Create</Button> : null}
        </div>

        <div className="mt-4 grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Trigger event</label>
            <Select value={triggerDraft} onChange={(event) => setTriggerDraft(event.target.value)}>
              {triggerEventOptions.map((eventName) => (
                <option key={eventName || "all"} value={eventName}>
                  {eventName || "All events"}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID</label>
            <Input
              value={legalEntityDraft}
              onChange={(event) => setLegalEntityDraft(event.target.value)}
              placeholder="UUID"
              disabled={globalScope}
            />
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={globalScope}
                onChange={(event) => {
                  setGlobalScope(event.target.checked);
                  if (event.target.checked) {
                    setLegalEntityDraft("");
                  }
                }}
              />
              Global
            </label>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Active</label>
            <Select value={activeDraft} onChange={(event) => setActiveDraft(event.target.value as typeof activeDraft)}>
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </div>

          <div className="flex items-end gap-2">
            <Button variant="secondary" onClick={applyFilters}>
              Apply
            </Button>
            <Button variant="secondary" onClick={clearFilters}>
              Clear
            </Button>
          </div>
        </div>
      </div>

      {listQuery.isLoading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="inline-flex items-center gap-2 text-sm text-slate-600">
            <Spinner />
            Loading workflow rules...
          </div>
        </div>
      ) : (
        <WorkflowListTable
          rules={pagedRules}
          canManage={canManage}
          canExecute={canExecute}
          onEdit={(rule) => setEditingRule(rule)}
          onToast={(message) => setToast(message)}
        />
      )}

      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
        <span>
          Page {safePage} of {totalPages} · {filteredRules.length} total
        </span>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={safePage <= 1}>
            Prev
          </Button>
          <Button
            variant="secondary"
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            disabled={safePage >= totalPages}
          >
            Next
          </Button>
        </div>
      </div>

      {canManage ? (
        <WorkflowFormModal
          open={createOpen}
          mode="create"
          onClose={() => setCreateOpen(false)}
          onSuccess={(message: string) => setToast(message)}
          onError={(message: ApiToastMessage) => setToast(message)}
        />
      ) : null}

      {canManage ? (
        <WorkflowFormModal
          open={Boolean(editingRule)}
          mode="edit"
          initialRule={editingRule}
          onClose={() => setEditingRule(null)}
          onSuccess={(message: string) => setToast(message)}
          onError={(message: ApiToastMessage) => setToast(message)}
        />
      ) : null}

      <Toast message={toast} tone={typeof toast === "string" ? "success" : toast?.message ? "error" : "info"} />
    </div>
  );
}
