import { describe, expect, test } from "vitest";
import { z } from "zod";

import { buildCustomFieldsSchema, normalizeCustomFieldPayload, zodErrorToFieldMap } from "./customFieldsZod";
import type { CustomFieldDefinitionRead } from "./types";

function definition(overrides: Partial<CustomFieldDefinitionRead>): CustomFieldDefinitionRead {
  return {
    id: "def-1",
    entity_type: "lead",
    field_key: "priority",
    label: "Priority",
    data_type: "select",
    is_required: true,
    allowed_values: ["High", "Medium", "Low"],
    legal_entity_id: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides
  };
}

describe("customFieldsZod", () => {
  test("validates required and typed custom fields", () => {
    const schema = buildCustomFieldsSchema([
      definition({ field_key: "priority", label: "Priority", data_type: "select", allowed_values: ["High", "Low"] }),
      definition({ id: "def-2", field_key: "budget", label: "Budget", data_type: "number", is_required: false, allowed_values: null }),
      definition({ id: "def-3", field_key: "go_live", label: "Go live", data_type: "date", is_required: true, allowed_values: null })
    ]);

    const valid = schema.parse({ priority: "High", budget: "1000", go_live: "2026-12-31" });
    expect(valid).toEqual({ priority: "High", budget: 1000, go_live: "2026-12-31" });

    expect(() => schema.parse({ priority: "Invalid", go_live: "2026-12-31" })).toThrow();
    expect(() => schema.parse({ priority: "High", go_live: "12/31/2026" })).toThrow();
  });

  test("rejects unknown keys", () => {
    const schema = buildCustomFieldsSchema([
      definition({ field_key: "priority", data_type: "text", allowed_values: null })
    ]);

    try {
      schema.parse({ priority: "P1", unexpected: "nope" });
      throw new Error("Expected validation error");
    } catch (error) {
      expect(error).toBeInstanceOf(z.ZodError);
      const mapped = zodErrorToFieldMap(error as z.ZodError);
      expect(mapped).toHaveProperty("unexpected");
    }
  });

  test("normalizes payload and preserves explicit clears", () => {
    const definitions = [
      definition({ field_key: "priority", data_type: "text", allowed_values: null }),
      definition({ id: "def-2", field_key: "budget", data_type: "number", is_required: false, allowed_values: null }),
      definition({ id: "def-3", field_key: "is_key", data_type: "bool", is_required: false, allowed_values: null })
    ];

    const payload = normalizeCustomFieldPayload(definitions, {
      priority: "Important",
      budget: undefined,
      is_key: "false"
    });

    expect(payload).toEqual({
      priority: "Important",
      budget: null,
      is_key: false
    });
  });
});
