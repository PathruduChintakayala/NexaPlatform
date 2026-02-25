"use client";

import React, { useMemo, useState } from "react";

import { ApiErrorBanner } from "../../../components/admin/api-error-banner";
import { ConfirmDialog } from "../../../components/admin/confirm-dialog";
import { DataTable } from "../../../components/admin/data-table";
import { FormModal } from "../../../components/admin/form-modal";
import { RouteGuard } from "../../../components/route-guard";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import type { AdminPermissionRead } from "../../../lib/types";
import { formatApiError, safeText, useAdminPermissionsData } from "../hooks";

const EFFECT_OPTIONS: Array<"allow" | "deny"> = ["allow", "deny"];

export default function AdminPermissionsPage() {
  const { permissionsQuery, createPermissionMutation, updatePermissionMutation, deletePermissionMutation } = useAdminPermissionsData();

  const [createOpen, setCreateOpen] = useState(false);
  const [editPermission, setEditPermission] = useState<AdminPermissionRead | null>(null);
  const [deletePermission, setDeletePermission] = useState<AdminPermissionRead | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [createResource, setCreateResource] = useState("");
  const [createAction, setCreateAction] = useState("");
  const [createField, setCreateField] = useState("");
  const [createEffect, setCreateEffect] = useState<"allow" | "deny">("allow");
  const [createScopeType, setCreateScopeType] = useState("");
  const [createScopeValue, setCreateScopeValue] = useState("");

  const [editResource, setEditResource] = useState("");
  const [editAction, setEditAction] = useState("");
  const [editField, setEditField] = useState("");
  const [editEffect, setEditEffect] = useState<"allow" | "deny">("allow");
  const [editScopeType, setEditScopeType] = useState("");
  const [editScopeValue, setEditScopeValue] = useState("");

  const rows = useMemo(
    () =>
      (permissionsQuery.data ?? []).map((permission) => ({
        ...permission,
        resource: safeText(permission.resource),
        action: safeText(permission.action),
        field: safeText(permission.field),
        effect: safeText(permission.effect),
        scope_type: safeText(permission.scope_type),
        scope_value: safeText(permission.scope_value)
      })),
    [permissionsQuery.data]
  );

  return (
    <RouteGuard requiredRoles={["admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <header>
            <h1 className="text-2xl font-semibold">Admin · Permissions</h1>
            <p className="text-sm text-slate-600">Manage permission definitions and scopes.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create permission</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <DataTable
          rows={rows}
          rowKey={(row) => row.id}
          emptyText={permissionsQuery.isLoading ? "Loading permissions..." : "No permissions found"}
          columns={[
            { key: "resource", title: "Resource", render: (row) => row.resource },
            { key: "action", title: "Action", render: (row) => row.action },
            { key: "field", title: "Field", render: (row) => row.field },
            { key: "effect", title: "Effect", render: (row) => row.effect },
            { key: "scope_type", title: "Scope Type", render: (row) => row.scope_type },
            { key: "scope_value", title: "Scope Value", render: (row) => row.scope_value },
            {
              key: "actions",
              title: "Actions",
              render: (row) => (
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setEditPermission(row);
                      setEditResource(row.resource === "—" ? "" : row.resource);
                      setEditAction(row.action === "—" ? "" : row.action);
                      setEditField(row.field === "—" ? "" : row.field);
                      setEditEffect(row.effect === "deny" ? "deny" : "allow");
                      setEditScopeType(row.scope_type === "—" ? "" : row.scope_type);
                      setEditScopeValue(row.scope_value === "—" ? "" : row.scope_value);
                    }}
                  >
                    Edit
                  </Button>
                  <Button variant="danger" onClick={() => setDeletePermission(row)}>
                    Delete
                  </Button>
                </div>
              )
            }
          ]}
        />

        <FormModal
          open={createOpen}
          title="Create permission"
          submitText="Create"
          pending={createPermissionMutation.isPending}
          onClose={() => setCreateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await createPermissionMutation.mutateAsync({
                resource: createResource,
                action: createAction,
                field: createField.trim() ? createField : null,
                effect: createEffect,
                scope_type: createScopeType.trim() ? createScopeType : null,
                scope_value: createScopeValue.trim() ? createScopeValue : null
              });
              setCreateOpen(false);
              setCreateResource("");
              setCreateAction("");
              setCreateField("");
              setCreateScopeType("");
              setCreateScopeValue("");
              setCreateEffect("allow");
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Resource</label>
              <Input value={createResource} onChange={(event) => setCreateResource(event.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Action</label>
              <Input value={createAction} onChange={(event) => setCreateAction(event.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Field</label>
              <Input value={createField} onChange={(event) => setCreateField(event.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Effect</label>
              <Select value={createEffect} onChange={(event) => setCreateEffect(event.target.value as "allow" | "deny")}>
                {EFFECT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Scope type</label>
              <Input value={createScopeType} onChange={(event) => setCreateScopeType(event.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Scope value</label>
              <Input value={createScopeValue} onChange={(event) => setCreateScopeValue(event.target.value)} />
            </div>
          </div>
        </FormModal>

        <FormModal
          open={Boolean(editPermission)}
          title="Edit permission"
          submitText="Save"
          pending={updatePermissionMutation.isPending}
          onClose={() => setEditPermission(null)}
          onSubmit={async (event) => {
            event.preventDefault();
            if (!editPermission) {
              return;
            }
            try {
              await updatePermissionMutation.mutateAsync({
                permissionId: editPermission.id,
                body: {
                  resource: editResource,
                  action: editAction,
                  field: editField.trim() ? editField : null,
                  effect: editEffect,
                  scope_type: editScopeType.trim() ? editScopeType : null,
                  scope_value: editScopeValue.trim() ? editScopeValue : null
                }
              });
              setEditPermission(null);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Resource</label>
              <Input value={editResource} onChange={(event) => setEditResource(event.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Action</label>
              <Input value={editAction} onChange={(event) => setEditAction(event.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Field</label>
              <Input value={editField} onChange={(event) => setEditField(event.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Effect</label>
              <Select value={editEffect} onChange={(event) => setEditEffect(event.target.value as "allow" | "deny")}>
                {EFFECT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Scope type</label>
              <Input value={editScopeType} onChange={(event) => setEditScopeType(event.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Scope value</label>
              <Input value={editScopeValue} onChange={(event) => setEditScopeValue(event.target.value)} />
            </div>
          </div>
        </FormModal>

        <ConfirmDialog
          open={Boolean(deletePermission)}
          title="Delete permission"
          description={`Delete permission ${safeText(deletePermission?.resource)}.${safeText(deletePermission?.action)}?`}
          confirmText="Delete"
          pending={deletePermissionMutation.isPending}
          onClose={() => setDeletePermission(null)}
          onConfirm={async () => {
            if (!deletePermission) {
              return;
            }
            try {
              await deletePermissionMutation.mutateAsync(deletePermission.id);
              setDeletePermission(null);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        />
      </section>
    </RouteGuard>
  );
}
