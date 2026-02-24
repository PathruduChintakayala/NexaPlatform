import { describe, expect, it } from "vitest";

import { queryKeys } from "./queryKeys";

describe("queryKeys workflows", () => {
  it("builds stable keys for workflow list/detail/executions", () => {
    expect(queryKeys.workflowsList({ trigger_event: "crm.lead.updated" })).toEqual([
      "workflows",
      "list",
      { trigger_event: "crm.lead.updated" }
    ]);

    expect(queryKeys.workflowDetail("rule-1")).toEqual(["workflows", "detail", "rule-1"]);

    expect(queryKeys.workflowExecutions({ rule_id: "rule-1", limit: 20 })).toEqual([
      "workflows",
      "executions",
      { rule_id: "rule-1", limit: 20 }
    ]);

    expect(queryKeys.workflowExecution("job-1")).toEqual(["workflows", "execution", "job-1"]);
  });
});
