"use client";

import Link from "next/link";

import type { WorkflowRuleRead } from "../../../lib/types";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";

interface WorkflowRuleDetailHeaderProps {
  rule: WorkflowRuleRead;
  canManage: boolean;
  onToggleActive: () => void;
  togglePending: boolean;
  onEdit: () => void;
  onDelete: () => void;
  deletePending: boolean;
}

export function WorkflowRuleDetailHeader({
  rule,
  canManage,
  onToggleActive,
  togglePending,
  onEdit,
  onDelete,
  deletePending
}: WorkflowRuleDetailHeaderProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-slate-900">{rule.name}</h1>
            <Badge tone={rule.is_active ? "success" : "default"}>{rule.is_active ? "Active" : "Inactive"}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500">{rule.description || "No description"}</p>
          <p className="mt-1 text-xs text-slate-500">Trigger: {rule.trigger_event}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link href="/crm/admin/workflows">
            <Button variant="secondary">Back to list</Button>
          </Link>
          {canManage ? (
            <Button variant="secondary" onClick={onToggleActive} disabled={togglePending}>
              {togglePending ? "Saving..." : rule.is_active ? "Disable" : "Enable"}
            </Button>
          ) : null}
          {canManage ? (
            <Button variant="secondary" onClick={onEdit}>
              Edit
            </Button>
          ) : null}
          {canManage ? (
            <Button variant="danger" onClick={onDelete} disabled={deletePending}>
              {deletePending ? "Deleting..." : "Delete"}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
