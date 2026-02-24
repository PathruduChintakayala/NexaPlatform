import { z } from "zod";

import type { CustomFieldDefinitionRead } from "./types";

export type CustomFieldValues = Record<string, unknown>;

const dateRegex = /^\d{4}-\d{2}-\d{2}$/;

function isValidDateOnly(value: string): boolean {
  if (!dateRegex.test(value)) {
    return false;
  }
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

function normalizeEmpty(value: unknown): unknown {
  if (value === "") {
    return undefined;
  }
  return value;
}

function fieldSchema(definition: CustomFieldDefinitionRead): z.ZodTypeAny {
  const base = (() => {
    switch (definition.data_type) {
      case "text":
        return z.preprocess(normalizeEmpty, z.string().min(1, `${definition.label} is required`));
      case "number":
        return z.preprocess((value) => {
          if (value === "" || value === null || value === undefined) {
            return undefined;
          }
          if (typeof value === "number") {
            return value;
          }
          if (typeof value === "string") {
            const parsed = Number(value);
            return Number.isFinite(parsed) ? parsed : value;
          }
          return value;
        }, z.number({ invalid_type_error: `${definition.label} must be a number` }).finite(`${definition.label} must be a number`));
      case "bool":
        return z.preprocess((value) => {
          if (value === "" || value === null || value === undefined) {
            return undefined;
          }
          if (typeof value === "boolean") {
            return value;
          }
          if (value === "true") {
            return true;
          }
          if (value === "false") {
            return false;
          }
          return value;
        }, z.boolean({ invalid_type_error: `${definition.label} must be true or false` }));
      case "date":
        return z
          .preprocess(normalizeEmpty, z.string().refine(isValidDateOnly, `${definition.label} must be YYYY-MM-DD`));
      case "select":
        return z.preprocess(
          normalizeEmpty,
          z
            .string()
            .min(1, `${definition.label} is required`)
            .refine(
              (value) => (definition.allowed_values ?? []).includes(value),
              `${definition.label} must be one of the allowed values`
            )
        );
      default:
        return z.unknown();
    }
  })();

  if (definition.is_required) {
    return base;
  }

  return z.union([base, z.null()]).optional();
}

export function buildCustomFieldsSchema(definitions: CustomFieldDefinitionRead[]) {
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const definition of definitions) {
    if (!definition.is_active) {
      continue;
    }
    shape[definition.field_key] = fieldSchema(definition);
  }
  return z.object(shape).strict();
}

export function normalizeCustomFieldPayload(
  definitions: CustomFieldDefinitionRead[],
  rawValues: CustomFieldValues | undefined
): CustomFieldValues {
  const parsed = buildCustomFieldsSchema(definitions).parse(rawValues ?? {});
  const payload: CustomFieldValues = {};
  const raw = rawValues ?? {};

  for (const definition of definitions) {
    if (!definition.is_active) {
      continue;
    }

    const key = definition.field_key;
    const parsedValue = parsed[key];
    if (parsedValue !== undefined) {
      payload[key] = parsedValue;
      continue;
    }

    const rawValue = raw[key];
    if (rawValue === "" || rawValue === null || (rawValue === undefined && Object.prototype.hasOwnProperty.call(raw, key))) {
      payload[key] = null;
    }
  }

  return payload;
}

export function zodErrorToFieldMap(error: z.ZodError): Record<string, string> {
  const fieldErrors: Record<string, string> = {};

  for (const issue of error.issues) {
    if (issue.code === "unrecognized_keys") {
      for (const key of issue.keys) {
        fieldErrors[key] = "Unknown custom field";
      }
      continue;
    }

    const field = typeof issue.path[0] === "string" ? issue.path[0] : null;
    if (field && !fieldErrors[field]) {
      fieldErrors[field] = issue.message;
    }
  }

  return fieldErrors;
}
