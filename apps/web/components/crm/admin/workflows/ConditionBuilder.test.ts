import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowCondition } from "../../../../lib/types";
import { ConditionBuilder } from "./ConditionBuilder";

describe("ConditionBuilder", () => {
  it("renders and supports adding leaf and group", async () => {
    const user = userEvent.setup();
    let current: WorkflowCondition = { all: [{ path: "status", op: "eq", value: "New" }] };

    const onChange = vi.fn((next: WorkflowCondition) => {
      current = next;
      rerender(
        createElement(ConditionBuilder, {
          value: current,
          onChange,
          entityType: "lead",
          customFieldDefinitions: []
        })
      );
    });

    const { rerender } = render(
      createElement(ConditionBuilder, {
        value: current,
        onChange,
        entityType: "lead",
        customFieldDefinitions: []
      })
    );

    await user.click(screen.getByRole("button", { name: "Add leaf" }));
    await user.click(screen.getByRole("button", { name: "Add ANY" }));

    expect(onChange).toHaveBeenCalled();
    expect(screen.getAllByText("Group").length).toBeGreaterThan(1);
  });
});
