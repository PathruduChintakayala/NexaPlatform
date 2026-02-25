"use client";

import React, { useState } from "react";

import { ApiErrorBanner } from "../../../components/admin/api-error-banner";
import { ConfirmDialog } from "../../../components/admin/confirm-dialog";
import { DataTable } from "../../../components/admin/data-table";
import { RouteGuard } from "../../../components/route-guard";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import type { AdminUserRoleRead } from "../../../lib/types";
import { formatApiError, safeText, useAdminUserRolesData } from "../hooks";

export default function AdminUserRolesPage() {
  const [searchUserId, setSearchUserId] = useState("");
  const [assignUserId, setAssignUserId] = useState("");
  const [assignRoleId, setAssignRoleId] = useState("");
  const [pendingUnassign, setPendingUnassign] = useState<AdminUserRoleRead | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { rolesQuery, assignmentsQuery, userRoles, assignRoleMutation, unassignRoleMutation } = useAdminUserRolesData(searchUserId);

  const assignments = assignmentsQuery.data ?? [];
  const roles = rolesQuery.data ?? [];

  return (
    <RouteGuard requiredRoles={["admin", "system.admin"]}>
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Admin · User Roles</h1>
          <p className="text-sm text-slate-600">Search assignments by user and manage all user-role links.</p>
        </header>

        <ApiErrorBanner message={errorMessage} />

        <article className="rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">Search by user_id</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-[2fr_1fr]">
            <Input value={searchUserId} onChange={(event) => setSearchUserId(event.target.value)} placeholder="user_id" />
            <Button variant="secondary" onClick={() => setSearchUserId("")}>
              Clear
            </Button>
          </div>

          <div className="mt-4">
            <DataTable
              rows={userRoles}
              rowKey={(row) => `${row.user_id}-${row.role_id}`}
              emptyText={searchUserId ? "No roles for this user" : "Enter a user_id to search"}
              columns={[
                { key: "user_id", title: "User ID", render: (row) => safeText(row.user_id) },
                { key: "role_name", title: "Role", render: (row) => safeText(row.role_name) },
                { key: "role_id", title: "Role ID", render: (row) => safeText(row.role_id) },
                {
                  key: "actions",
                  title: "Actions",
                  render: (row) => (
                    <Button variant="danger" onClick={() => setPendingUnassign(row)}>
                      Unassign
                    </Button>
                  )
                }
              ]}
            />
          </div>
        </article>

        <article className="rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">Assign role to user</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <Input value={assignUserId} onChange={(event) => setAssignUserId(event.target.value)} placeholder="user_id" />
            <Select value={assignRoleId} onChange={(event) => setAssignRoleId(event.target.value)}>
              <option value="">Select role</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </Select>
            <Button
              disabled={!assignUserId.trim() || !assignRoleId || assignRoleMutation.isPending}
              onClick={async () => {
                try {
                  await assignRoleMutation.mutateAsync({ userId: assignUserId.trim(), roleId: assignRoleId });
                  setErrorMessage(null);
                } catch (error) {
                  setErrorMessage(formatApiError(error));
                }
              }}
            >
              {assignRoleMutation.isPending ? "Assigning..." : "Assign role"}
            </Button>
          </div>
        </article>

        <article className="rounded-lg border border-slate-200 p-4">
          <h2 className="text-base font-semibold">All assignments</h2>
          <div className="mt-3">
            <DataTable
              rows={assignments}
              rowKey={(row) => `${row.user_id}-${row.role_id}`}
              emptyText={assignmentsQuery.isLoading ? "Loading assignments..." : "No assignments found"}
              columns={[
                { key: "user_id", title: "User ID", render: (row) => safeText(row.user_id) },
                { key: "role_name", title: "Role", render: (row) => safeText(row.role_name) },
                { key: "role_id", title: "Role ID", render: (row) => safeText(row.role_id) },
                {
                  key: "actions",
                  title: "Actions",
                  render: (row) => (
                    <Button variant="danger" onClick={() => setPendingUnassign(row)}>
                      Unassign
                    </Button>
                  )
                }
              ]}
            />
          </div>
        </article>

        <ConfirmDialog
          open={Boolean(pendingUnassign)}
          title="Unassign role"
          description={`Unassign role ${safeText(pendingUnassign?.role_name)} from user ${safeText(pendingUnassign?.user_id)}?`}
          confirmText="Unassign"
          pending={unassignRoleMutation.isPending}
          onClose={() => setPendingUnassign(null)}
          onConfirm={async () => {
            if (!pendingUnassign) {
              return;
            }
            try {
              await unassignRoleMutation.mutateAsync({ userId: pendingUnassign.user_id, roleId: pendingUnassign.role_id });
              setPendingUnassign(null);
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
