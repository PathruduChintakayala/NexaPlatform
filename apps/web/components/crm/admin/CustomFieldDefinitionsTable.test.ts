import { describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { CustomFieldDefinitionsTable } from "./CustomFieldDefinitionsTable";

describe("CustomFieldDefinitionsTable", () => {
  it("renders definition rows", () => {
    const html = renderToStaticMarkup(
      createElement(CustomFieldDefinitionsTable, {
        canManage: true,
        onEdit: vi.fn(),
        definitions: [
          {
            id: "def-1",
            entity_type: "lead",
            field_key: "priority",
            label: "Priority",
            data_type: "select",
            is_required: true,
            allowed_values: ["low", "high"],
            legal_entity_id: "11111111-1111-1111-1111-111111111111",
            is_active: true,
            created_at: "2026-02-24T00:00:00Z",
            updated_at: "2026-02-24T00:00:00Z"
          }
        ]
      })
    );

    expect(html).toContain("Priority");
    expect(html).toContain("priority");
    expect(html).toContain("LE:11111111-1111-1111-1111-111111111111");
    expect(html).toContain("Edit");
  });
});
