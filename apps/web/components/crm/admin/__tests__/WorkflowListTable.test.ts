import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowRuleRead } from "../../../../lib/types";
import { WorkflowListTable } from "../WorkflowListTable";

vi.mock("../WorkflowActionMenu", () => ({
  WorkflowActionMenu: () => createElement("span", null, "Actions")
}));

describe("WorkflowListTable", () => {
  it("renders workflow names and scope", () => {
    const rules: WorkflowRuleRead[] = [
      {
        id: "rule-1",
        name: "Lead qualification",
        description: null,
        is_active: true,
        legal_entity_id: null,
        trigger_event: "crm.lead.created",
        condition_json: { path: "status", op: "eq", value: "New" },
        actions_json: [{ type: "SET_FIELD", path: "owner_user_id", value: "u1" }],
        created_at: "2026-02-24T00:00:00Z",
        updated_at: "2026-02-24T00:00:00Z",
        deleted_at: null
      },
      {
        id: "rule-2",
        name: "LE scoped workflow",
        description: null,
        is_active: true,
        legal_entity_id: "11111111-1111-1111-1111-111111111111",
        trigger_event: "crm.account.created",
        condition_json: { path: "status", op: "eq", value: "Active" },
        actions_json: [{ type: "NOTIFY", notification_type: "WORKFLOW_ALERT", payload: { a: 1 } }],
        created_at: "2026-02-24T00:00:00Z",
        updated_at: "2026-02-24T00:00:00Z",
        deleted_at: null
      }
    ];

    render(
      createElement(WorkflowListTable, {
        rules,
        canManage: true,
        canExecute: true,
        onEdit: vi.fn(),
        onToast: vi.fn()
      })
    );

    expect(screen.getByText("Lead qualification")).toBeTruthy();
    expect(screen.getByText("LE scoped workflow")).toBeTruthy();
    expect(screen.getByText("Global")).toBeTruthy();
    expect(screen.getByText("LE:11111111-1111-1111-1111-111111111111")).toBeTruthy();
  });
});
