"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import React from "react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  createWorkflowRule,
  getErrorToastMessage,
  updateWorkflowRule,
  type ApiToastMessage
} from "../../../lib/api";
import type { WorkflowRuleRead } from "../../../lib/types";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Modal } from "../../ui/modal";
import { Select } from "../../ui/select";

const triggerOptions = [
  "crm.lead.created",
  "crm.lead.updated",
  "crm.opportunity.stage_changed",
  "crm.opportunity.closed_won",
  "crm.opportunity.closed_lost",
  "crm.account.created",
  "crm.account.updated"
] as const;

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  trigger_event: z.string().min(1, "Trigger event is required"),
  legal_entity_id: z.string().optional(),
  is_active: z.boolean(),
  condition_json_text: z.string().min(1, "Condition JSON is required"),
  actions_json_text: z.string().min(1, "Actions JSON is required")
});

type FormValues = z.infer<typeof schema>;

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function parseJsonField<T>(raw: string, fieldLabel: string): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`${fieldLabel} must be valid JSON`);
  }
}

interface WorkflowFormModalProps {
  open: boolean;
  mode: "create" | "edit";
  initialRule?: WorkflowRuleRead | null;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: ApiToastMessage) => void;
}

export function WorkflowFormModal({ open, mode, initialRule, onClose, onSuccess, onError }: WorkflowFormModalProps) {
  const queryClient = useQueryClient();
  const [builderPath, setBuilderPath] = useState("status");
  const [builderOp, setBuilderOp] = useState("eq");
  const [builderValue, setBuilderValue] = useState("New");
  const [builderGroup, setBuilderGroup] = useState<"all" | "any">("all");
  const [builderNot, setBuilderNot] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      trigger_event: triggerOptions[0],
      legal_entity_id: "",
      is_active: true,
      condition_json_text: prettyJson({ path: "status", op: "eq", value: "New" }),
      actions_json_text: prettyJson([{ type: "SET_FIELD", path: "qualification_notes", value: "Workflow updated" }])
    }
  });

  useEffect(() => {
    if (mode === "edit" && initialRule) {
      form.reset({
        name: initialRule.name,
        description: initialRule.description ?? "",
        trigger_event: initialRule.trigger_event,
        legal_entity_id: initialRule.legal_entity_id ?? "",
        is_active: initialRule.is_active,
        condition_json_text: prettyJson(initialRule.condition_json),
        actions_json_text: prettyJson(initialRule.actions_json)
      });
      return;
    }

    form.reset({
      name: "",
      description: "",
      trigger_event: triggerOptions[0],
      legal_entity_id: "",
      is_active: true,
      condition_json_text: prettyJson({ path: "status", op: "eq", value: "New" }),
      actions_json_text: prettyJson([{ type: "SET_FIELD", path: "qualification_notes", value: "Workflow updated" }])
    });
  }, [form, initialRule, mode, open]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const conditionJson = parseJsonField<Record<string, unknown>>(values.condition_json_text, "Condition JSON");
      const actionsJson = parseJsonField<Record<string, unknown>[]>(values.actions_json_text, "Actions JSON");

      if (mode === "create") {
        return createWorkflowRule({
          name: values.name,
          description: values.description || null,
          trigger_event: values.trigger_event,
          legal_entity_id: values.legal_entity_id || null,
          is_active: values.is_active,
          condition_json: conditionJson,
          actions_json: actionsJson
        });
      }

      if (!initialRule) {
        throw new Error("Rule not loaded");
      }

      return updateWorkflowRule(initialRule.id, {
        name: values.name,
        description: values.description || null,
        trigger_event: values.trigger_event,
        legal_entity_id: values.legal_entity_id || null,
        is_active: values.is_active,
        condition_json: conditionJson,
        actions_json: actionsJson
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workflows"] });
      onSuccess(mode === "create" ? "Workflow rule created." : "Workflow rule updated.");
      onClose();
    },
    onError: (error) => {
      onError(getErrorToastMessage(error));
    }
  });

  const title = useMemo(() => (mode === "create" ? "Create Workflow" : "Edit Workflow"), [mode]);

  function applySimpleConditionBuilder() {
    const leaf: Record<string, unknown> = {
      path: builderPath,
      op: builderOp,
      value: builderValue
    };
    const grouped = { [builderGroup]: [leaf] };
    const next = builderNot ? { not: grouped } : grouped;
    form.setValue("condition_json_text", prettyJson(next), { shouldDirty: true });
  }

  function appendSetFieldAction() {
    const existing = parseJsonField<Record<string, unknown>[]>(form.getValues("actions_json_text"), "Actions JSON");
    existing.push({ type: "SET_FIELD", path: "qualification_notes", value: "Workflow updated" });
    form.setValue("actions_json_text", prettyJson(existing), { shouldDirty: true });
  }

  function appendCreateTaskAction() {
    const existing = parseJsonField<Record<string, unknown>[]>(form.getValues("actions_json_text"), "Actions JSON");
    existing.push({
      type: "CREATE_TASK",
      title: "Follow up",
      due_in_days: 3,
      assigned_to_user_id: "00000000-0000-0000-0000-000000000000",
      entity_ref: { type: "lead", id: "00000000-0000-0000-0000-000000000000" }
    });
    form.setValue("actions_json_text", prettyJson(existing), { shouldDirty: true });
  }

  function appendNotifyAction() {
    const existing = parseJsonField<Record<string, unknown>[]>(form.getValues("actions_json_text"), "Actions JSON");
    existing.push({
      type: "NOTIFY",
      notification_type: "WORKFLOW_ALERT",
      payload: { recipient_user_id: "00000000-0000-0000-0000-000000000000", message: "Workflow fired" }
    });
    form.setValue("actions_json_text", prettyJson(existing), { shouldDirty: true });
  }

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Name</label>
            <Input {...form.register("name")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Trigger event</label>
            <Select {...form.register("trigger_event")}>
              {triggerOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Description</label>
          <Input {...form.register("description")} />
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID (optional)</label>
            <Input {...form.register("legal_entity_id")} placeholder="UUID or empty for global" />
          </div>
          <label className="mt-6 flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_active")} /> Active
          </label>
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-xs font-medium text-slate-700">Simple condition builder</p>
          <div className="grid gap-2 md:grid-cols-2">
            <Input value={builderPath} onChange={(event) => setBuilderPath(event.target.value)} placeholder="status or custom_fields.key" />
            <Select value={builderOp} onChange={(event) => setBuilderOp(event.target.value)}>
              <option value="eq">eq</option>
              <option value="neq">neq</option>
              <option value="in">in</option>
              <option value="contains">contains</option>
              <option value="gt">gt</option>
              <option value="gte">gte</option>
              <option value="lt">lt</option>
              <option value="lte">lte</option>
              <option value="exists">exists</option>
            </Select>
            <Input value={builderValue} onChange={(event) => setBuilderValue(event.target.value)} placeholder="value" />
            <div className="flex items-center gap-2">
              <Select value={builderGroup} onChange={(event) => setBuilderGroup(event.target.value as "all" | "any")}>
                <option value="all">all</option>
                <option value="any">any</option>
              </Select>
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={builderNot} onChange={(event) => setBuilderNot(event.target.checked)} />
                not
              </label>
            </div>
          </div>
          <div className="mt-2">
            <Button type="button" variant="secondary" onClick={applySimpleConditionBuilder}>
              Apply to JSON
            </Button>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Condition JSON</label>
          <textarea
            className="min-h-32 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            {...form.register("condition_json_text")}
          />
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-xs font-medium text-slate-700">Actions builder</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={appendSetFieldAction}>
              Add SET_FIELD
            </Button>
            <Button type="button" variant="secondary" onClick={appendCreateTaskAction}>
              Add CREATE_TASK
            </Button>
            <Button type="button" variant="secondary" onClick={appendNotifyAction}>
              Add NOTIFY
            </Button>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Actions JSON</label>
          <textarea
            className="min-h-40 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            {...form.register("actions_json_text")}
          />
        </div>

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
