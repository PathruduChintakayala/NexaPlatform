"use client";

import type { CustomFieldDefinitionRead } from "../../lib/types";
import { Input } from "../ui/input";
import { Select } from "../ui/select";

interface CustomFieldsRendererProps {
  definitions: CustomFieldDefinitionRead[];
  values: Record<string, unknown>;
  errors?: Record<string, string>;
  onChange: (fieldKey: string, value: unknown) => void;
}

function fieldValueToString(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "";
}

export function CustomFieldsRenderer({ definitions, values, errors = {}, onChange }: CustomFieldsRendererProps) {
  const activeDefinitions = definitions.filter((item) => item.is_active);

  if (activeDefinitions.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-slate-800">Custom fields</p>
      <div className="grid gap-3 md:grid-cols-2">
        {activeDefinitions.map((definition) => {
          const value = values[definition.field_key];
          const error = errors[definition.field_key];

          return (
            <div key={definition.id} className={definition.data_type === "text" ? "md:col-span-2" : ""}>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                {definition.label}
                {definition.is_required ? " *" : ""}
              </label>

              {definition.data_type === "text" ? (
                <textarea
                  className="min-h-20 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                  value={fieldValueToString(value)}
                  onChange={(event) =>
                    onChange(definition.field_key, event.target.value === "" ? undefined : event.target.value)
                  }
                />
              ) : null}

              {definition.data_type === "number" ? (
                <Input
                  type="number"
                  step="0.01"
                  value={fieldValueToString(value)}
                  onChange={(event) =>
                    onChange(definition.field_key, event.target.value === "" ? undefined : event.target.value)
                  }
                />
              ) : null}

              {definition.data_type === "date" ? (
                <Input
                  type="date"
                  value={fieldValueToString(value)}
                  onChange={(event) =>
                    onChange(definition.field_key, event.target.value === "" ? undefined : event.target.value)
                  }
                />
              ) : null}

              {definition.data_type === "bool" ? (
                <Select
                  value={value === true ? "true" : value === false ? "false" : ""}
                  onChange={(event) =>
                    onChange(
                      definition.field_key,
                      event.target.value === "" ? undefined : event.target.value === "true"
                    )
                  }
                >
                  <option value="">{definition.is_required ? "Select" : "Unset"}</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </Select>
              ) : null}

              {definition.data_type === "select" ? (
                <Select
                  value={fieldValueToString(value)}
                  onChange={(event) =>
                    onChange(definition.field_key, event.target.value === "" ? undefined : event.target.value)
                  }
                >
                  <option value="">{definition.is_required ? "Select" : "Unset"}</option>
                  {(definition.allowed_values ?? []).map((allowedValue) => (
                    <option key={allowedValue} value={allowedValue}>
                      {allowedValue}
                    </option>
                  ))}
                </Select>
              ) : null}

              {error ? <p className="mt-1 text-xs text-red-600">{error}</p> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
