"use client";

import React, { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createWorkflowRule, getErrorToastMessage, listCustomFieldDefinitions, updateWorkflowRule } from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import type { ApiToastMessage, CustomFieldEntityType } from "../../../lib/api";
import type { WorkflowAction, WorkflowCondition, WorkflowEntityType, WorkflowRuleRead } from "../../../lib/types";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { Modal } from "../../ui/modal";
import { Select } from "../../ui/select";
import { ActionsBuilder } from "./workflows/ActionsBuilder";
import { ConditionBuilder } from "./workflows/ConditionBuilder";

const triggerEvents = [
  "crm.lead.created",
  "crm.lead.updated",
  "crm.opportunity.stage_changed",
  "crm.opportunity.closed_won",
  "crm.account.created"
] as const;

const conditionPlaceholder = JSON.stringify({ all: [{ path: "status", op: "eq", value: "Qualified" }] }, null, 2);
const actionsPlaceholder = JSON.stringify(
  [{ type: "SET_FIELD", path: "qualification_notes", value: "Workflow updated lead" }],
  null,
  2
);

const schema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  description: z.string().optional(),
  trigger_event: z.string().trim().min(1, "Trigger event is required"),
  legal_entity_id: z.string().optional(),
  is_active: z.boolean(),
  condition_json_text: z.string().trim().min(1, "Condition JSON is required"),
  actions_json_text: z.string().trim().min(1, "Actions JSON is required")
});

type FormValues = z.infer<typeof schema>;

type EditorMode = "builder" | "json";

interface WorkflowCreateModalProps {
  open: boolean;
  mode: "create" | "edit";
  initialRule?: WorkflowRuleRead | null;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: ApiToastMessage) => void;
}

function toPrettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function defaultCondition(): WorkflowCondition {
  return { all: [{ path: "status", op: "eq", value: "New" }] };
}

function defaultActions(): WorkflowAction[] {
  return [{ type: "SET_FIELD", path: "qualification_notes", value: "Workflow updated lead" }];
}

function isConditionShape(value: unknown, depth = 0): value is WorkflowCondition {
  if (!value || typeof value !== "object") {
    return false;
  }
  if (depth > 3) {
    return false;
  }

  const current = value as Record<string, unknown>;
  if ("all" in current) {
    return Array.isArray(current.all) && current.all.every((item) => isConditionShape(item, depth + 1));
  }
  if ("any" in current) {
    return Array.isArray(current.any) && current.any.every((item) => isConditionShape(item, depth + 1));
  }
  if ("not" in current) {
    return isConditionShape(current.not, depth + 1);
  }
  return typeof current.path === "string" && typeof current.op === "string";
}

function isWorkflowActionShape(value: unknown): value is WorkflowAction {
  if (!value || typeof value !== "object") {
    return false;
  }
  const current = value as Record<string, unknown>;
  if (current.type === "SET_FIELD") {
    return typeof current.path === "string" && "value" in current;
  }
  if (current.type === "CREATE_TASK") {
    return (
      typeof current.title === "string" &&
      typeof current.due_in_days === "number" &&
      typeof current.assigned_to_user_id === "string"
    );
  }
  if (current.type === "NOTIFY") {
    return (
      typeof current.notification_type === "string" &&
      !!current.payload &&
      typeof current.payload === "object" &&
      !Array.isArray(current.payload)
    );
  }
  return false;
}

function serializeBuilderState(condition: WorkflowCondition, actions: WorkflowAction[]) {
  return {
    condition_json_text: toPrettyJson(condition),
    actions_json_text: toPrettyJson(actions)
  };
}

export function WorkflowCreateModal({
  open,
  mode,
  initialRule,
  onClose,
  onSuccess,
  onError
}: WorkflowCreateModalProps) {
  const queryClient = useQueryClient();
  const title = useMemo(() => (mode === "create" ? "Create Workflow" : "Edit Workflow"), [mode]);

  const [editorMode, setEditorMode] = useState<EditorMode>("builder");
  const [builderEntityType, setBuilderEntityType] = useState<WorkflowEntityType>("lead");
  const [builderCondition, setBuilderCondition] = useState<WorkflowCondition>(defaultCondition());
  const [builderActions, setBuilderActions] = useState<WorkflowAction[]>(defaultActions());
  const [actionsValid, setActionsValid] = useState(true);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      trigger_event: triggerEvents[0],
      legal_entity_id: "",
      is_active: true,
      condition_json_text: conditionPlaceholder,
      actions_json_text: actionsPlaceholder
    }
  });

  const legalEntityId = form.watch("legal_entity_id") || undefined;

  const customFieldsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions(builderEntityType, legalEntityId),
    queryFn: () => listCustomFieldDefinitions(builderEntityType as CustomFieldEntityType, legalEntityId),
    enabled: open
  });

  useEffect(() => {
    if (mode === "edit" && initialRule) {
      form.reset({
        name: initialRule.name,
        description: initialRule.description ?? "",
        trigger_event: initialRule.trigger_event,
        legal_entity_id: initialRule.legal_entity_id ?? "",
        is_active: initialRule.is_active,
        condition_json_text: toPrettyJson(initialRule.condition_json),
        actions_json_text: toPrettyJson(initialRule.actions_json)
      });
      setBuilderCondition(isConditionShape(initialRule.condition_json) ? initialRule.condition_json : defaultCondition());
      const initialActions = Array.isArray(initialRule.actions_json)
        ? initialRule.actions_json.filter((item) => isWorkflowActionShape(item))
        : [];
      setBuilderActions(initialActions.length > 0 ? initialActions : defaultActions());
      setActionsValid(true);
      setEditorMode("builder");
      return;
    }

    form.reset({
      name: "",
      description: "",
      trigger_event: triggerEvents[0],
      legal_entity_id: "",
      is_active: true,
      condition_json_text: conditionPlaceholder,
      actions_json_text: actionsPlaceholder
    });
    setBuilderCondition(defaultCondition());
    setBuilderActions(defaultActions());
    setActionsValid(true);
    setEditorMode("builder");
  }, [form, initialRule, mode, open]);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      let condition_json: Record<string, unknown>;
      let actions_json: Record<string, unknown>[];

      if (editorMode === "builder") {
        if (!isConditionShape(builderCondition)) {
          throw new Error("Condition builder state is invalid");
        }
        if (!Array.isArray(builderActions) || builderActions.length === 0) {
          throw new Error("At least one action is required");
        }
        if (!actionsValid) {
          throw new Error("One or more NOTIFY payloads are invalid JSON objects");
        }

        condition_json = builderCondition as unknown as Record<string, unknown>;
        actions_json = builderActions as unknown as Record<string, unknown>[];
      } else {
        try {
          const parsedCondition = JSON.parse(values.condition_json_text) as unknown;
          if (!isConditionShape(parsedCondition)) {
            throw new Error("Condition JSON does not match expected workflow schema");
          }
          condition_json = parsedCondition as unknown as Record<string, unknown>;
        } catch (error) {
          throw new Error(error instanceof Error ? error.message : "Condition JSON is invalid");
        }

        try {
          const parsedActions = JSON.parse(values.actions_json_text) as unknown;
          if (!Array.isArray(parsedActions) || parsedActions.length === 0) {
            throw new Error("Actions JSON must be a non-empty array");
          }
          const valid = parsedActions.every((item) => isWorkflowActionShape(item));
          if (!valid) {
            throw new Error("Actions JSON includes unsupported action shape");
          }
          actions_json = parsedActions as unknown as Record<string, unknown>[];
        } catch (error) {
          throw new Error(error instanceof Error ? error.message : "Actions JSON is invalid");
        }
      }

      if (mode === "create") {
        return createWorkflowRule({
          name: values.name,
          description: values.description || null,
          trigger_event: values.trigger_event,
          legal_entity_id: values.legal_entity_id || null,
          is_active: values.is_active,
          condition_json,
          actions_json
        });
      }

      if (!initialRule) {
        throw new Error("Workflow rule not available for edit");
      }

      return updateWorkflowRule(initialRule.id, {
        name: values.name,
        description: values.description || null,
        trigger_event: values.trigger_event,
        legal_entity_id: values.legal_entity_id || null,
        is_active: values.is_active,
        condition_json,
        actions_json
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.workflows.list({}) });
      onSuccess(mode === "create" ? "Workflow created." : "Workflow updated.");
      onClose();
    },
    onError: (error) => onError(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Name</label>
            <Input {...form.register("name")} />
            {form.formState.errors.name ? <p className="mt-1 text-xs text-red-600">{form.formState.errors.name.message}</p> : null}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Description</label>
            <Input {...form.register("description")} />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Trigger event</label>
            <Select {...form.register("trigger_event")}>
              {triggerEvents.map((eventName) => (
                <option key={eventName} value={eventName}>
                  {eventName}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID (optional)</label>
            <Input {...form.register("legal_entity_id")} placeholder="UUID or empty for global" />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" {...form.register("is_active")} />
            Active
          </label>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Editor mode</label>
            <Select value={editorMode} onChange={(event) => setEditorMode(event.target.value as EditorMode)}>
              <option value="builder">Builder</option>
              <option value="json">JSON (advanced)</option>
            </Select>
          </div>
        </div>

        {editorMode === "builder" ? (
          <div className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Entity type (for suggestions only)</label>
              <Select value={builderEntityType} onChange={(event) => setBuilderEntityType(event.target.value as WorkflowEntityType)}>
                <option value="account">account</option>
                <option value="contact">contact</option>
                <option value="lead">lead</option>
                <option value="opportunity">opportunity</option>
              </Select>
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-slate-700">Condition Builder</p>
              <ConditionBuilder
                value={builderCondition}
                onChange={setBuilderCondition}
                entityType={builderEntityType}
                customFieldDefinitions={customFieldsQuery.data ?? []}
              />
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-slate-700">Actions Builder</p>
              <ActionsBuilder
                value={builderActions}
                onChange={setBuilderActions}
                entityType={builderEntityType}
                customFieldDefinitions={customFieldsQuery.data ?? []}
                onValidityChange={setActionsValid}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  const serialized = serializeBuilderState(builderCondition, builderActions);
                  form.setValue("condition_json_text", serialized.condition_json_text);
                  form.setValue("actions_json_text", serialized.actions_json_text);
                }}
              >
                Sync from Builder
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  try {
                    const parsedCondition = JSON.parse(form.getValues("condition_json_text"));
                    const parsedActions = JSON.parse(form.getValues("actions_json_text"));

                    if (!isConditionShape(parsedCondition)) {
                      throw new Error("Condition JSON shape is invalid");
                    }
                    if (!Array.isArray(parsedActions) || !parsedActions.every((item) => isWorkflowActionShape(item))) {
                      throw new Error("Actions JSON shape is invalid");
                    }

                    setBuilderCondition(parsedCondition);
                    setBuilderActions(parsedActions);
                    setActionsValid(true);
                    onSuccess("Loaded JSON into Builder.");
                  } catch (error) {
                    onError({ message: error instanceof Error ? error.message : "Unable to load JSON", correlationId: null });
                  }
                }}
              >
                Load into Builder
              </Button>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Condition JSON</label>
              <textarea
                className="min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder={conditionPlaceholder}
                {...form.register("condition_json_text")}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Actions JSON</label>
              <textarea
                className="min-h-28 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                placeholder={actionsPlaceholder}
                {...form.register("actions_json_text")}
              />
            </div>
          </div>
        )}

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
