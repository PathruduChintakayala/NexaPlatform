import { createElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowDryRunForm } from "../WorkflowDryRunForm";

const dryRunWorkflowRuleMock = vi.fn();
const executeWorkflowRuleMock = vi.fn();

vi.mock("../../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../../lib/api")>();
  return {
    ...actual,
    dryRunWorkflowRule: (...args: unknown[]) => dryRunWorkflowRuleMock(...args),
    executeWorkflowRule: (...args: unknown[]) => executeWorkflowRuleMock(...args)
  };
});

function renderWithQuery(ui: ReturnType<typeof createElement>) {
  const client = new QueryClient();
  return render(createElement(QueryClientProvider, { client }, ui));
}

afterEach(() => {
  cleanup();
});

describe("WorkflowDryRunForm", () => {
  it("renders core inputs and actions", () => {
    renderWithQuery(
      createElement(WorkflowDryRunForm, {
        ruleId: "rule-1",
        canExecute: true,
        onToast: vi.fn()
      })
    );

    expect(screen.getByText("Entity type")).toBeTruthy();
    expect(screen.getByText("Entity ID")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run Dry Run" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Execute" })).toBeTruthy();
  });

  it("renders readable dry-run results", async () => {
    const user = userEvent.setup();
    dryRunWorkflowRuleMock.mockResolvedValueOnce({
      matched: true,
      planned_mutations: {
        qualification_notes: { before: "Old", after: "New" }
      },
      planned_actions: [
        { type: "SET_FIELD", path: "qualification_notes", value: "New" },
        { type: "CREATE_TASK", title: "Follow up", due_in_days: 3 },
        { type: "NOTIFY", notification_type: "WORKFLOW_ALERT", payload: { recipient: "u1" } }
      ]
    });

    renderWithQuery(
      createElement(WorkflowDryRunForm, {
        ruleId: "rule-1",
        canExecute: true,
        onToast: vi.fn()
      })
    );

    await user.type(screen.getAllByPlaceholderText("UUID")[0], "00000000-0000-0000-0000-000000000001");
    await user.click(screen.getByRole("button", { name: "Run Dry Run" }));

    await waitFor(() => {
      expect(screen.getByText("SET_FIELD")).toBeTruthy();
      expect(screen.getByText("CREATE_TASK")).toBeTruthy();
      expect(screen.getByText("NOTIFY")).toBeTruthy();
    });
  });
});
