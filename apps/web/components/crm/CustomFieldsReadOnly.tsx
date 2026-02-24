"use client";

import type { CustomFieldDefinitionRead } from "../../lib/types";

interface CustomFieldsReadOnlyProps {
  definitions: CustomFieldDefinitionRead[];
  values: Record<string, unknown> | undefined;
  emptyText?: string;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

export function CustomFieldsReadOnly({ definitions, values, emptyText = "No custom fields" }: CustomFieldsReadOnlyProps) {
  const entries = Object.entries(values ?? {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (entries.length === 0) {
    return <p className="text-sm text-slate-500">{emptyText}</p>;
  }

  const labelByKey = new Map<string, string>();
  for (const definition of definitions) {
    if (definition.is_active) {
      labelByKey.set(definition.field_key, definition.label);
    }
  }

  return (
    <div className="grid gap-2 text-sm text-slate-700 md:grid-cols-2">
      {entries.map(([key, value]) => (
        <p key={key}>
          <span className="font-medium">{labelByKey.get(key) ?? key}:</span> {formatValue(value)}
        </p>
      ))}
    </div>
  );
}
