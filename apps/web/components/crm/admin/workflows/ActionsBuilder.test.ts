import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowAction } from "../../../../lib/types";
import { ActionsBuilder } from "./ActionsBuilder";

describe("ActionsBuilder", () => {
  it("adds SET_FIELD and CREATE_TASK actions", async () => {
    const user = userEvent.setup();
    let current: WorkflowAction[] = [];

    const onChange = vi.fn((next: WorkflowAction[]) => {
      current = next;
      rerender(
        createElement(ActionsBuilder, {
          value: current,
          onChange,
          entityType: "lead",
          customFieldDefinitions: []
        })
      );
    });

    const { rerender } = render(
      createElement(ActionsBuilder, {
        value: current,
        onChange,
        entityType: "lead",
        customFieldDefinitions: []
      })
    );

    await user.click(screen.getByRole("button", { name: "Add SET_FIELD" }));
    await user.click(screen.getByRole("button", { name: "Add CREATE_TASK" }));

    expect(onChange).toHaveBeenCalled();
    expect(screen.getByText("SET_FIELD")).toBeTruthy();
    expect(screen.getByText("CREATE_TASK")).toBeTruthy();
  });
});
