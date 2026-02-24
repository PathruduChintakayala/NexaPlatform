"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  createCustomFieldDefinition,
  getErrorToastMessage,
  updateCustomFieldDefinition,
  type CustomFieldEntityType
} from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import type { CustomFieldDataType, CustomFieldDefinitionRead } from "../../../lib/types";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Modal } from "../../ui/modal";
import { Select } from "../../ui/select";

const fieldKeyRegex = /^[a-z][a-z0-9_]*$/;

const schema = z
  .object({
    label: z.string().min(1, "Label is required"),
    field_key: z.string().regex(fieldKeyRegex, "Field key must be snake_case"),
    data_type: z.enum(["text", "number", "bool", "date", "select"]),
    is_required: z.boolean(),
    is_active: z.boolean(),
    scope_mode: z.enum(["global", "legal_entity"]),
    legal_entity_id: z.string().optional(),
    allowed_values_text: z.string().optional()
  })
  .superRefine((value, ctx) => {
    if (value.scope_mode === "legal_entity" && !value.legal_entity_id) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["legal_entity_id"], message: "Legal entity ID is required" });
    }
    const allowed = (value.allowed_values_text ?? "")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

    if (value.data_type === "select" && allowed.length === 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["allowed_values_text"], message: "At least one allowed value is required" });
    }
    if (value.data_type !== "select" && allowed.length > 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["allowed_values_text"],
        message: "Allowed values are only valid for select"
      });
    }
  });

type FormValues = z.infer<typeof schema>;

interface CustomFieldDefinitionFormModalProps {
  open: boolean;
  mode: "create" | "edit";
  entityType: CustomFieldEntityType;
  legalEntityId?: string;
  initialDefinition?: CustomFieldDefinitionRead | null;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: { message: string; correlationId: string | null }) => void;
}

function normalizeAllowedValues(input: string | undefined): string[] {
  return (input ?? "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CustomFieldDefinitionFormModal({
  open,
  mode,
  entityType,
  legalEntityId,
  initialDefinition,
  onClose,
  onSuccess,
  onError
}: CustomFieldDefinitionFormModalProps) {
  const queryClient = useQueryClient();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      label: "",
      field_key: "",
      data_type: "text",
      is_required: false,
      is_active: true,
      scope_mode: "global",
      legal_entity_id: legalEntityId ?? "",
      allowed_values_text: ""
    }
  });

  const dataType = form.watch("data_type") as CustomFieldDataType;
  const scopeMode = form.watch("scope_mode");

  useEffect(() => {
    if (mode === "edit" && initialDefinition) {
      form.reset({
        label: initialDefinition.label,
        field_key: initialDefinition.field_key,
        data_type: initialDefinition.data_type,
        is_required: initialDefinition.is_required,
        is_active: initialDefinition.is_active,
        scope_mode: initialDefinition.legal_entity_id ? "legal_entity" : "global",
        legal_entity_id: initialDefinition.legal_entity_id ?? "",
        allowed_values_text: initialDefinition.allowed_values?.join("\n") ?? ""
      });
      return;
    }

    form.reset({
      label: "",
      field_key: "",
      data_type: "text",
      is_required: false,
      is_active: true,
      scope_mode: legalEntityId ? "legal_entity" : "global",
      legal_entity_id: legalEntityId ?? "",
      allowed_values_text: ""
    });
  }, [form, initialDefinition, legalEntityId, mode, open]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const allowedValues = normalizeAllowedValues(values.allowed_values_text);
      if (mode === "create") {
        return createCustomFieldDefinition(entityType, {
          field_key: values.field_key,
          label: values.label,
          data_type: values.data_type,
          is_required: values.is_required,
          is_active: values.is_active,
          legal_entity_id: values.scope_mode === "legal_entity" ? values.legal_entity_id : null,
          allowed_values: values.data_type === "select" ? allowedValues : undefined
        });
      }

      if (!initialDefinition) {
        throw new Error("Missing initial definition for edit");
      }

      return updateCustomFieldDefinition(initialDefinition.id, {
        label: values.label,
        is_required: values.is_required,
        is_active: values.is_active,
        allowed_values: values.data_type === "select" ? allowedValues : undefined
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.customFieldDefinitions(entityType, legalEntityId)
      });
      onSuccess(mode === "create" ? "Custom field definition created." : "Custom field definition updated.");
      onClose();
    },
    onError: (error) => {
      onError(getErrorToastMessage(error));
    }
  });

  const title = useMemo(() => (mode === "create" ? "Create Custom Field" : "Edit Custom Field"), [mode]);

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Label</label>
          <Input {...form.register("label")} />
          {form.formState.errors.label ? <p className="mt-1 text-xs text-red-600">{form.formState.errors.label.message}</p> : null}
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Field key</label>
          <Input {...form.register("field_key")} disabled={mode === "edit"} />
          {form.formState.errors.field_key ? (
            <p className="mt-1 text-xs text-red-600">{form.formState.errors.field_key.message}</p>
          ) : null}
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Data type</label>
          <Select {...form.register("data_type")} disabled={mode === "edit"}>
            <option value="text">text</option>
            <option value="number">number</option>
            <option value="bool">bool</option>
            <option value="date">date</option>
            <option value="select">select</option>
          </Select>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_required")} /> Required
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_active")} /> Active
          </label>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Scope</label>
          <Select {...form.register("scope_mode")} disabled={mode === "edit"}>
            <option value="global">Global</option>
            <option value="legal_entity">Legal entity scoped</option>
          </Select>
        </div>

        {scopeMode === "legal_entity" ? (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID</label>
            <Input {...form.register("legal_entity_id")} placeholder="UUID" disabled={mode === "edit"} />
            {form.formState.errors.legal_entity_id ? (
              <p className="mt-1 text-xs text-red-600">{form.formState.errors.legal_entity_id.message}</p>
            ) : null}
          </div>
        ) : null}

        {dataType === "select" ? (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Allowed values (one per line)</label>
            <textarea
              className="min-h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
              {...form.register("allowed_values_text")}
            />
            {form.formState.errors.allowed_values_text ? (
              <p className="mt-1 text-xs text-red-600">{form.formState.errors.allowed_values_text.message}</p>
            ) : null}
          </div>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving..." : mode === "create" ? "Create" : "Update"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
