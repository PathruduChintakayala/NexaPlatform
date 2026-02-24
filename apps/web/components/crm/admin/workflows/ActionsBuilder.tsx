"use client";

import React, { useEffect, useMemo, useState } from "react";

import type { CustomFieldDefinitionRead, WorkflowAction, WorkflowActionCreateTask, WorkflowActionNotify, WorkflowActionSetField, WorkflowEntityType } from "../../../../lib/types";
import { Button } from "../../../ui/button";
import { Input } from "../../../ui/input";

type ActionKind = WorkflowAction["type"];

interface ActionsBuilderProps {
  value: WorkflowAction[];
  onChange: (value: WorkflowAction[]) => void;
  entityType: WorkflowEntityType;
  customFieldDefinitions: CustomFieldDefinitionRead[];
  onValidityChange?: (isValid: boolean) => void;
}

const staticSuggestions: Record<WorkflowEntityType, string[]> = {
  lead: ["status", "source", "owner_user_id", "selling_legal_entity_id", "region_code"],
  opportunity: [
    "stage_id",
    "amount",
    "probability",
    "forecast_category",
    "expected_close_date",
    "owner_user_id",
    "selling_legal_entity_id"
  ],
  account: ["name", "status", "owner_user_id", "primary_region_code"],
  contact: ["email", "phone", "is_primary", "owner_user_id"]
};

function defaultSetField(): WorkflowActionSetField {
  return { type: "SET_FIELD", path: "status", value: "Updated" };
}

function defaultCreateTask(): WorkflowActionCreateTask {
  return {
    type: "CREATE_TASK",
    title: "Follow up",
    due_in_days: 3,
    assigned_to_user_id: "",
    entity_ref: { type: "lead", id: "" }
  };
}

function defaultNotify(): WorkflowActionNotify {
  return {
    type: "NOTIFY",
    notification_type: "WORKFLOW_ALERT",
    payload: {}
  };
}

export function ActionsBuilder({ value, onChange, entityType, customFieldDefinitions, onValidityChange }: ActionsBuilderProps) {
  const [activePathIndex, setActivePathIndex] = useState<number | null>(null);
  const [notifyPayloadTextByIndex, setNotifyPayloadTextByIndex] = useState<Record<number, string>>({});
  const [notifyErrorsByIndex, setNotifyErrorsByIndex] = useState<Record<number, string | null>>({});

  const pathSuggestions = useMemo(() => {
    const custom = customFieldDefinitions.map((item) => `custom_fields.${item.field_key}`);
    return [...staticSuggestions[entityType], ...custom];
  }, [customFieldDefinitions, entityType]);

  useEffect(() => {
    const hasErrors = Object.values(notifyErrorsByIndex).some(Boolean);
    onValidityChange?.(!hasErrors);
  }, [notifyErrorsByIndex, onValidityChange]);

  function addAction(kind: ActionKind) {
    if (kind === "SET_FIELD") {
      onChange([...value, defaultSetField()]);
      return;
    }
    if (kind === "CREATE_TASK") {
      onChange([...value, defaultCreateTask()]);
      return;
    }
    onChange([...value, defaultNotify()]);
  }

  function removeAction(index: number) {
    const clone = [...value];
    clone.splice(index, 1);
    onChange(clone);
    setNotifyPayloadTextByIndex((current) => {
      const next = { ...current };
      delete next[index];
      return next;
    });
    setNotifyErrorsByIndex((current) => {
      const next = { ...current };
      delete next[index];
      return next;
    });
  }

  function updateAction(index: number, nextAction: WorkflowAction) {
    const clone = [...value];
    clone[index] = nextAction;
    onChange(clone);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={() => addAction("SET_FIELD")}>Add SET_FIELD</Button>
        <Button type="button" variant="secondary" onClick={() => addAction("CREATE_TASK")}>Add CREATE_TASK</Button>
        <Button type="button" variant="secondary" onClick={() => addAction("NOTIFY")}>Add NOTIFY</Button>
      </div>

      {value.length === 0 ? <p className="text-sm text-slate-500">No actions added yet.</p> : null}

      <div className="space-y-3">
        {value.map((action, index) => {
          if (action.type === "SET_FIELD") {
            const filtered = pathSuggestions.filter((item) => item.toLowerCase().includes(action.path.toLowerCase())).slice(0, 8);
            return (
              <div key={`action-${index}`} className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-slate-700">SET_FIELD</p>
                  <button type="button" className="text-xs text-red-600 underline" onClick={() => removeAction(index)}>Remove</button>
                </div>
                <div className="relative">
                  <label className="mb-1 block text-xs font-medium text-slate-600">Path</label>
                  <Input
                    value={action.path}
                    onFocus={() => setActivePathIndex(index)}
                    onBlur={() => {
                      setTimeout(() => setActivePathIndex((current) => (current === index ? null : current)), 120);
                    }}
                    onChange={(event) => updateAction(index, { ...action, path: event.target.value })}
                  />
                  {activePathIndex === index && filtered.length > 0 ? (
                    <div className="absolute z-10 mt-1 max-h-40 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow">
                      {filtered.map((item) => (
                        <button
                          key={item}
                          type="button"
                          className="block w-full px-2 py-1 text-left text-xs text-slate-700 hover:bg-slate-100"
                          onMouseDown={(event) => {
                            event.preventDefault();
                            updateAction(index, { ...action, path: item });
                            setActivePathIndex(null);
                          }}
                        >
                          {item}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">Value</label>
                  <Input
                    value={typeof action.value === "string" ? action.value : JSON.stringify(action.value ?? "")}
                    onChange={(event) => updateAction(index, { ...action, value: event.target.value })}
                  />
                </div>
              </div>
            );
          }

          if (action.type === "CREATE_TASK") {
            return (
              <div key={`action-${index}`} className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-slate-700">CREATE_TASK</p>
                  <button type="button" className="text-xs text-red-600 underline" onClick={() => removeAction(index)}>Remove</button>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-600">Title</label>
                  <Input
                    value={action.title}
                    onChange={(event) => updateAction(index, { ...action, title: event.target.value })}
                  />
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Due in days</label>
                    <Input
                      type="number"
                      value={String(action.due_in_days)}
                      onChange={(event) =>
                        updateAction(index, {
                          ...action,
                          due_in_days: Number.isNaN(Number(event.target.value)) ? 0 : Number(event.target.value)
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Assigned to user ID</label>
                    <Input
                      value={action.assigned_to_user_id}
                      onChange={(event) => updateAction(index, { ...action, assigned_to_user_id: event.target.value })}
                    />
                  </div>
                </div>
              </div>
            );
          }

          const rawPayloadText =
            notifyPayloadTextByIndex[index] !== undefined
              ? notifyPayloadTextByIndex[index]
              : JSON.stringify(action.payload, null, 2);

          return (
            <div key={`action-${index}`} className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-slate-700">NOTIFY</p>
                <button type="button" className="text-xs text-red-600 underline" onClick={() => removeAction(index)}>Remove</button>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600">Notification type</label>
                <Input
                  value={action.notification_type}
                  onChange={(event) => updateAction(index, { ...action, notification_type: event.target.value })}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600">Payload JSON</label>
                <textarea
                  className="min-h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                  value={rawPayloadText}
                  onChange={(event) => {
                    const raw = event.target.value;
                    setNotifyPayloadTextByIndex((current) => ({ ...current, [index]: raw }));

                    try {
                      const parsed = JSON.parse(raw) as unknown;
                      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                        setNotifyErrorsByIndex((current) => ({ ...current, [index]: "Payload must be a JSON object" }));
                        return;
                      }

                      setNotifyErrorsByIndex((current) => ({ ...current, [index]: null }));
                      updateAction(index, { ...action, payload: parsed as Record<string, unknown> });
                    } catch {
                      setNotifyErrorsByIndex((current) => ({ ...current, [index]: "Payload must be valid JSON" }));
                    }
                  }}
                />
                {notifyErrorsByIndex[index] ? <p className="mt-1 text-xs text-red-600">{notifyErrorsByIndex[index]}</p> : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
