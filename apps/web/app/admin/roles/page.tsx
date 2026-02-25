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
import type { AdminRoleRead } from "../../../lib/types";
import { formatApiError, safeText, useAdminRolesData, useRolePermissions } from "../hooks";

export default function AdminRolesPage() {
  const {
    rolesQuery,
    permissionsQuery,
    createRoleMutation,
    updateRoleMutation,
    deleteRoleMutation,
    attachPermissionMutation,
    detachPermissionMutation
  } = useAdminRolesData();

  const [createOpen, setCreateOpen] = useState(false);
  const [editRole, setEditRole] = useState<AdminRoleRead | null>(null);
  const [deleteRole, setDeleteRole] = useState<AdminRoleRead | null>(null);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [detachPermissionId, setDetachPermissionId] = useState<string | null>(null);

  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");

  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const [attachPermissionId, setAttachPermissionId] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const roles = rolesQuery.data ?? [];
  const permissions = permissionsQuery.data ?? [];
  const selectedRole = roles.find((role) => role.id === selectedRoleId) ?? null;
  const rolePermissionsQuery = useRolePermissions(selectedRole?.id ?? null);
  const rolePermissions = rolePermissionsQuery.data ?? [];

  const attachablePermissions = useMemo(() => {
    const attached = new Set(rolePermissions.map((item) => item.permission_id));
    return permissions.filter((item) => !attached.has(item.id));
  }, [permissions, rolePermissions]);

  const tableRows = useMemo(
    () =>
      roles.map((role) => ({
        ...role,
        description: safeText(role.description)
      })),
    [roles]
  );

  return (
    <RouteGuard requiredRoles={["admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <header>
            <h1 className="text-2xl font-semibold">Admin · Roles</h1>
            <p className="text-sm text-slate-600">Manage role definitions and role-permission mappings.</p>
          </header>
          <Button onClick={() => setCreateOpen(true)}>Create role</Button>
        </div>

        <ApiErrorBanner message={errorMessage} />

        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <DataTable
            rows={tableRows}
            rowKey={(row) => row.id}
            emptyText={rolesQuery.isLoading ? "Loading roles..." : "No roles found"}
            columns={[
              { key: "name", title: "Name", render: (row) => row.name },
              { key: "description", title: "Description", render: (row) => row.description },
              { key: "is_system", title: "System", render: (row) => (row.is_system ? "Yes" : "No") },
              { key: "id", title: "ID", render: (row) => row.id },
              {
                key: "actions",
                title: "Actions",
                render: (row) => (
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSelectedRoleId(row.id);
                        setErrorMessage(null);
                      }}
                    >
                      Details
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setEditRole(row);
                        setEditName(row.name);
                        setEditDescription(row.description ?? "");
                      }}
                    >
                      Edit
                    </Button>
                    <Button variant="danger" disabled={row.is_system} onClick={() => setDeleteRole(row)}>
                      Delete
                    </Button>
                  </div>
                )
              }
            ]}
          />

          <aside className="space-y-3 rounded-lg border border-slate-200 p-4">
            <h2 className="text-base font-semibold">Role detail</h2>
            {selectedRole ? (
              <>
                <div className="space-y-1 text-sm">
                  <p>
                    <span className="font-medium">Name:</span> {safeText(selectedRole.name)}
                  </p>
                  <p>
                    <span className="font-medium">Description:</span> {safeText(selectedRole.description)}
                  </p>
                  <p>
                    <span className="font-medium">ID:</span> {safeText(selectedRole.id)}
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700">Attach permission</label>
                  <Select value={attachPermissionId} onChange={(event) => setAttachPermissionId(event.target.value)}>
                    <option value="">Select permission</option>
                    {attachablePermissions.map((permission) => (
                      <option key={permission.id} value={permission.id}>
                        {safeText(permission.resource)}.{safeText(permission.action)}
                      </option>
                    ))}
                  </Select>
                  <Button
                    className="w-full"
                    disabled={!attachPermissionId || attachPermissionMutation.isPending}
                    onClick={async () => {
                      try {
                        await attachPermissionMutation.mutateAsync({ roleId: selectedRole.id, permissionId: attachPermissionId });
                        setAttachPermissionId("");
                        setErrorMessage(null);
                      } catch (error) {
                        setErrorMessage(formatApiError(error));
                      }
                    }}
                  >
                    Attach permission
                  </Button>
                </div>

                <div className="space-y-2">
                  <p className="text-sm font-medium text-slate-700">Attached permissions</p>
                  {rolePermissionsQuery.isLoading ? <p className="text-sm text-slate-500">Loading...</p> : null}
                  {rolePermissions.map((item) => (
                    <div key={item.permission_id} className="flex items-center justify-between rounded border border-slate-200 px-2 py-1 text-sm">
                      <span>
                        {safeText(item.resource)}.{safeText(item.action)} ({safeText(item.field)})
                      </span>
                      <Button variant="secondary" onClick={() => setDetachPermissionId(item.permission_id)}>
                        Detach
                      </Button>
                    </div>
                  ))}
                  {!rolePermissionsQuery.isLoading && rolePermissions.length === 0 ? (
                    <p className="text-sm text-slate-500">No permissions attached.</p>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">Select a role to view permission mappings.</p>
            )}
          </aside>
        </div>

        <FormModal
          open={createOpen}
          title="Create role"
          submitText="Create"
          pending={createRoleMutation.isPending}
          onClose={() => setCreateOpen(false)}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await createRoleMutation.mutateAsync({
                name: createName,
                description: createDescription.trim() ? createDescription : null
              });
              setCreateOpen(false);
              setCreateName("");
              setCreateDescription("");
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="space-y-3">
            <div>
              <label htmlFor="create-role-name" className="mb-1 block text-xs font-medium text-slate-600">
                Name
              </label>
              <Input id="create-role-name" value={createName} onChange={(event) => setCreateName(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="create-role-description" className="mb-1 block text-xs font-medium text-slate-600">
                Description
              </label>
              <Input id="create-role-description" value={createDescription} onChange={(event) => setCreateDescription(event.target.value)} />
            </div>
          </div>
        </FormModal>

        <FormModal
          open={Boolean(editRole)}
          title="Edit role"
          submitText="Save"
          pending={updateRoleMutation.isPending}
          onClose={() => setEditRole(null)}
          onSubmit={async (event) => {
            event.preventDefault();
            if (!editRole) {
              return;
            }
            try {
              await updateRoleMutation.mutateAsync({
                roleId: editRole.id,
                body: {
                  name: editName,
                  description: editDescription.trim() ? editDescription : null
                }
              });
              setEditRole(null);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        >
          <div className="space-y-3">
            <div>
              <label htmlFor="edit-role-name" className="mb-1 block text-xs font-medium text-slate-600">
                Name
              </label>
              <Input id="edit-role-name" value={editName} onChange={(event) => setEditName(event.target.value)} required />
            </div>
            <div>
              <label htmlFor="edit-role-description" className="mb-1 block text-xs font-medium text-slate-600">
                Description
              </label>
              <Input id="edit-role-description" value={editDescription} onChange={(event) => setEditDescription(event.target.value)} />
            </div>
          </div>
        </FormModal>

        <ConfirmDialog
          open={Boolean(deleteRole)}
          title="Delete role"
          description={`Delete role ${safeText(deleteRole?.name)}?`}
          confirmText="Delete"
          pending={deleteRoleMutation.isPending}
          onClose={() => setDeleteRole(null)}
          onConfirm={async () => {
            if (!deleteRole) {
              return;
            }
            try {
              await deleteRoleMutation.mutateAsync(deleteRole.id);
              if (selectedRoleId === deleteRole.id) {
                setSelectedRoleId(null);
              }
              setDeleteRole(null);
              setErrorMessage(null);
            } catch (error) {
              setErrorMessage(formatApiError(error));
            }
          }}
        />

        <ConfirmDialog
          open={Boolean(detachPermissionId && selectedRole)}
          title="Detach permission"
          description="Detach this permission from selected role?"
          confirmText="Detach"
          pending={detachPermissionMutation.isPending}
          onClose={() => setDetachPermissionId(null)}
          onConfirm={async () => {
            if (!detachPermissionId || !selectedRole) {
              return;
            }
            try {
              await detachPermissionMutation.mutateAsync({ roleId: selectedRole.id, permissionId: detachPermissionId });
              setDetachPermissionId(null);
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
