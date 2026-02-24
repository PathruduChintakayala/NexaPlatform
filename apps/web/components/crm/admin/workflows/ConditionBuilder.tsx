"use client";

import React, { useMemo, useState } from "react";

import type { CustomFieldDefinitionRead, WorkflowCondition, WorkflowEntityType, WorkflowOperator } from "../../../../lib/types";
import { Button } from "../../../ui/button";
import { Input } from "../../../ui/input";
import { Select } from "../../../ui/select";

type GroupType = "all" | "any";

interface ConditionBuilderProps {
  value: WorkflowCondition;
  onChange: (value: WorkflowCondition) => void;
  entityType: WorkflowEntityType;
  customFieldDefinitions: CustomFieldDefinitionRead[];
  maxDepth?: number;
}

const operators: WorkflowOperator[] = ["eq", "neq", "in", "contains", "gt", "gte", "lt", "lte", "exists"];

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

function isGroup(condition: WorkflowCondition): condition is { all: WorkflowCondition[] } | { any: WorkflowCondition[] } {
  return "all" in condition || "any" in condition;
}

function groupChildren(condition: { all: WorkflowCondition[] } | { any: WorkflowCondition[] }) {
  return "all" in condition ? condition.all : condition.any;
}

function asGroup(type: GroupType, children: WorkflowCondition[]) {
  return type === "all" ? ({ all: children } as WorkflowCondition) : ({ any: children } as WorkflowCondition);
}

function isNot(condition: WorkflowCondition): condition is { not: WorkflowCondition } {
  return "not" in condition;
}

function isLeaf(condition: WorkflowCondition): condition is { path: string; op: WorkflowOperator; value?: unknown } {
  return "path" in condition && "op" in condition;
}

function getAtPath(condition: WorkflowCondition, path: number[]): WorkflowCondition {
  if (path.length === 0) {
    return condition;
  }

  const [head, ...rest] = path;
  if (isGroup(condition)) {
    const children = groupChildren(condition);
    return getAtPath(children[head], rest);
  }

  if (isNot(condition)) {
    return getAtPath(condition.not, rest);
  }

  return condition;
}

function replaceAtPath(condition: WorkflowCondition, path: number[], next: WorkflowCondition): WorkflowCondition {
  if (path.length === 0) {
    return next;
  }

  const [head, ...rest] = path;

  if (isGroup(condition)) {
    const clone = [...groupChildren(condition)];
    clone[head] = replaceAtPath(clone[head], rest, next);
    return "all" in condition ? { all: clone } : { any: clone };
  }

  if (isNot(condition)) {
    return { not: replaceAtPath(condition.not, rest, next) };
  }

  return condition;
}

function removeAtPath(condition: WorkflowCondition, path: number[]): WorkflowCondition {
  if (path.length === 0) {
    return condition;
  }

  const parentPath = path.slice(0, -1);
  const indexToRemove = path[path.length - 1];
  const parent = getAtPath(condition, parentPath);

  if (isGroup(parent)) {
    const clone = [...groupChildren(parent)];
    clone.splice(indexToRemove, 1);
    const fallbackLeaf: WorkflowCondition = { path: "status", op: "eq", value: "New" };
    const normalized: WorkflowCondition[] = clone.length > 0 ? clone : [fallbackLeaf];
    return replaceAtPath(condition, parentPath, "all" in parent ? { all: normalized } : { any: normalized });
  }

  if (isNot(parent)) {
    return replaceAtPath(condition, parentPath, { path: "status", op: "eq", value: "New" });
  }

  return condition;
}

function parseLeafValue(op: WorkflowOperator, rawValue: string): unknown {
  if (op === "exists") {
    return undefined;
  }
  if (op === "in") {
    return rawValue
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return rawValue;
}

function serializeLeafValue(op: WorkflowOperator, value: unknown): string {
  if (op === "exists") {
    return "";
  }
  if (op === "in" && Array.isArray(value)) {
    return value.join(", ");
  }
  return typeof value === "string" ? value : value === undefined || value === null ? "" : String(value);
}

export function ConditionBuilder({ value, onChange, entityType, customFieldDefinitions, maxDepth = 3 }: ConditionBuilderProps) {
  const [activePathInput, setActivePathInput] = useState<string | null>(null);

  const suggestions = useMemo(() => {
    const custom = customFieldDefinitions.map((item) => `custom_fields.${item.field_key}`);
    return [...staticSuggestions[entityType], ...custom];
  }, [customFieldDefinitions, entityType]);

  function updateLeaf(path: number[], patch: Partial<{ path: string; op: WorkflowOperator; value?: unknown }>) {
    const current = getAtPath(value, path);
    if (!isLeaf(current)) {
      return;
    }
    onChange(replaceAtPath(value, path, { ...current, ...patch }));
  }

  function addChild(path: number[], kind: "leaf" | "all" | "any" | "not") {
    const current = getAtPath(value, path);
    if (!isGroup(current)) {
      return;
    }

    const key: GroupType = "all" in current ? "all" : "any";
    const next = [...groupChildren(current)];
    if (kind === "leaf") {
      next.push({ path: "status", op: "eq", value: "New" });
    }
    if (kind === "all") {
      next.push({ all: [{ path: "status", op: "eq", value: "New" }] });
    }
    if (kind === "any") {
      next.push({ any: [{ path: "status", op: "eq", value: "New" }] });
    }
    if (kind === "not") {
      next.push({ not: { path: "status", op: "eq", value: "New" } });
    }

    onChange(replaceAtPath(value, path, asGroup(key, next)));
  }

  function renderNode(node: WorkflowCondition, path: number[], depth: number): React.ReactNode {
    const pathKey = path.join(".") || "root";

    if (isGroup(node)) {
      const key: GroupType = "all" in node ? "all" : "any";
      const children = groupChildren(node);
      return (
        <div key={pathKey} className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="inline-flex items-center gap-2 text-xs">
              <span className="font-medium text-slate-700">Group</span>
              <Select
                className="w-24"
                value={key}
                onChange={(event) => {
                  const nextType = event.target.value as GroupType;
                  onChange(replaceAtPath(value, path, asGroup(nextType, children)));
                }}
              >
                <option value="all">ALL</option>
                <option value="any">ANY</option>
              </Select>
            </div>
            <div className="flex flex-wrap gap-1">
              <Button type="button" variant="secondary" onClick={() => addChild(path, "leaf")}>Add leaf</Button>
              {depth < maxDepth ? (
                <>
                  <Button type="button" variant="secondary" onClick={() => addChild(path, "all")}>Add ALL</Button>
                  <Button type="button" variant="secondary" onClick={() => addChild(path, "any")}>Add ANY</Button>
                  <Button type="button" variant="secondary" onClick={() => addChild(path, "not")}>Add NOT</Button>
                </>
              ) : null}
            </div>
          </div>
          <div className="space-y-2">
            {children.map((child: WorkflowCondition, index: number) => (
              <div key={`${pathKey}.${index}`} className="space-y-1">
                {renderNode(child, [...path, index], depth + 1)}
                {path.length > 0 ? (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      className="text-xs text-red-600 underline"
                      onClick={() => onChange(removeAtPath(value, [...path, index]))}
                    >
                      Remove
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (isNot(node)) {
      return (
        <div key={pathKey} className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-700">NOT</p>
            {path.length > 0 ? (
              <button
                type="button"
                className="text-xs text-red-600 underline"
                onClick={() => onChange(removeAtPath(value, path))}
              >
                Remove
              </button>
            ) : null}
          </div>
          {renderNode(node.not, [...path, 0], depth + 1)}
        </div>
      );
    }

    const active = activePathInput === pathKey;
    const filteredSuggestions = suggestions
      .filter((item) => item.toLowerCase().includes(node.path.toLowerCase()))
      .slice(0, 8);

    return (
      <div key={pathKey} className="space-y-2 rounded-md border border-slate-200 bg-white p-3">
        <div className="grid gap-2 md:grid-cols-3">
          <div className="relative md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-slate-600">Path</label>
            <Input
              value={node.path}
              onFocus={() => setActivePathInput(pathKey)}
              onBlur={() => {
                setTimeout(() => setActivePathInput((current) => (current === pathKey ? null : current)), 120);
              }}
              onChange={(event) => updateLeaf(path, { path: event.target.value })}
            />
            {active && filteredSuggestions.length > 0 ? (
              <div className="absolute z-10 mt-1 max-h-40 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow">
                {filteredSuggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="block w-full px-2 py-1 text-left text-xs text-slate-700 hover:bg-slate-100"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      updateLeaf(path, { path: item });
                      setActivePathInput(null);
                    }}
                  >
                    {item}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Operator</label>
            <Select
              value={node.op}
              onChange={(event) => {
                const op = event.target.value as WorkflowOperator;
                updateLeaf(path, { op, value: op === "exists" ? undefined : node.value ?? "" });
              }}
            >
              {operators.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {node.op !== "exists" ? (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Value{node.op === "in" ? " (comma separated)" : ""}</label>
            <Input
              value={serializeLeafValue(node.op, node.value)}
              onChange={(event) => updateLeaf(path, { value: parseLeafValue(node.op, event.target.value) })}
            />
          </div>
        ) : null}
      </div>
    );
  }

  return <div className="space-y-2">{renderNode(value, [], 1)}</div>;
}
