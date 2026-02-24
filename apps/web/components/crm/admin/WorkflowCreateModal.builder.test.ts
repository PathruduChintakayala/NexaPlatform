import { createElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowCreateModal } from "./WorkflowCreateModal";

const createWorkflowRuleMock = vi.fn();
const updateWorkflowRuleMock = vi.fn();
const listCustomFieldDefinitionsMock = vi.fn();

vi.mock("../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api")>();
  return {
    ...actual,
    createWorkflowRule: (...args: unknown[]) => createWorkflowRuleMock(...args),
    updateWorkflowRule: (...args: unknown[]) => updateWorkflowRuleMock(...args),
    listCustomFieldDefinitions: (...args: unknown[]) => listCustomFieldDefinitionsMock(...args)
  };
});

function renderWithQuery(ui: ReturnType<typeof createElement>) {
  const client = new QueryClient();
  return render(createElement(QueryClientProvider, { client }, ui));
}

afterEach(() => {
  cleanup();
});

describe("WorkflowCreateModal builder mode", () => {
  it("submits create payload with condition_json and actions_json", async () => {
    const user = userEvent.setup();
    listCustomFieldDefinitionsMock.mockResolvedValue([]);
    createWorkflowRuleMock.mockResolvedValue({ id: "rule-1" });

    const onSuccess = vi.fn();

    renderWithQuery(
      createElement(WorkflowCreateModal, {
        open: true,
        mode: "create",
        onClose: vi.fn(),
        onSuccess,
        onError: vi.fn()
      })
    );

    const nameInput = screen.getAllByRole("textbox")[0];
    await user.clear(nameInput);
    await user.type(nameInput, "Builder rule");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createWorkflowRuleMock).toHaveBeenCalled();
    });

    const payload = createWorkflowRuleMock.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.name).toBe("Builder rule");
    expect(payload).toHaveProperty("condition_json");
    expect(payload).toHaveProperty("actions_json");
    expect(Array.isArray(payload.actions_json)).toBe(true);
  });
});
