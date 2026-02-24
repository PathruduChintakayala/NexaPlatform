"use client";

import React from "react";
import Link from "next/link";

import type { ApiToastMessage } from "../../../lib/api";
import type { WorkflowRuleRead } from "../../../lib/types";
import { Td, Th, Table } from "../../ui/table";
import { WorkflowActionMenu } from "./WorkflowActionMenu";

interface WorkflowListTableProps {
  rules: WorkflowRuleRead[];
  canManage: boolean;
  canExecute: boolean;
  onEdit: (rule: WorkflowRuleRead) => void;
  onToast: (message: string | ApiToastMessage) => void;
}

function truncate(value: string, max = 120) {
  if (value.length <= max) {
    return value;
  }
  return `${value.slice(0, max - 1)}…`;
}

function getConditionSummary(condition: Record<string, unknown>) {
  if (typeof condition.path === "string" && typeof condition.op === "string") {
    return truncate(`${condition.path} ${condition.op} ${JSON.stringify(condition.value)}`);
  }

  const json = JSON.stringify(condition);
  return truncate(json ?? "{}");
}

function getScope(legalEntityId: string | null) {
  return legalEntityId ? `LE:${legalEntityId}` : "Global";
}

export function WorkflowListTable({ rules, canManage, canExecute, onEdit, onToast }: WorkflowListTableProps) {
  return (
    <Table>
      <thead className="bg-slate-50">
        <tr>
          <Th>Name</Th>
          <Th>Trigger event</Th>
          <Th>Scope</Th>
          <Th>Condition summary</Th>
          <Th>Actions</Th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rules.length === 0 ? (
          <tr>
            <Td>
              <span className="text-slate-500">No workflow rules found.</span>
            </Td>
            <Td />
            <Td />
            <Td />
            <Td />
          </tr>
        ) : (
          rules.map((rule) => (
            <tr key={rule.id}>
              <Td>
                <Link href={`/crm/admin/workflows/${rule.id}`} className="font-medium text-slate-900 hover:underline">
                  {rule.name}
                </Link>
              </Td>
              <Td>{rule.trigger_event}</Td>
              <Td>{getScope(rule.legal_entity_id)}</Td>
              <Td>
                <span title={JSON.stringify(rule.condition_json)}>{getConditionSummary(rule.condition_json)}</span>
              </Td>
              <Td>
                <div className="flex justify-end">
                  <WorkflowActionMenu
                    rule={rule}
                    canManage={canManage}
                    canExecute={canExecute}
                    onEdit={onEdit}
                    onToast={onToast}
                  />
                </div>
              </Td>
            </tr>
          ))
        )}
      </tbody>
    </Table>
  );
}
