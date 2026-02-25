import { apiRequest } from "./core";
import type {
  AdminPermissionRead,
  AdminPermissionUpdate,
  AdminRolePermissionRead,
  AdminRoleRead,
  AdminRoleUpdate,
  AdminUserRoleRead
} from "../types";

export function listAdminRoles() {
  return apiRequest<AdminRoleRead[]>("/admin/roles");
}

export function createAdminRole(body: { name: string; description?: string | null; is_system?: boolean }) {
  return apiRequest<AdminRoleRead>("/admin/roles", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function updateAdminRole(roleId: string, body: AdminRoleUpdate) {
  return apiRequest<AdminRoleRead>(`/admin/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function deleteAdminRole(roleId: string) {
  return apiRequest<null>(`/admin/roles/${roleId}`, { method: "DELETE" });
}

export function listAdminPermissions() {
  return apiRequest<AdminPermissionRead[]>("/admin/permissions");
}

export function createAdminPermission(body: {
  resource: string;
  action: string;
  field?: string | null;
  scope_type?: string | null;
  scope_value?: string | null;
  effect?: "allow" | "deny";
  description?: string | null;
}) {
  return apiRequest<AdminPermissionRead>("/admin/permissions", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function updateAdminPermission(permissionId: string, body: AdminPermissionUpdate) {
  return apiRequest<AdminPermissionRead>(`/admin/permissions/${permissionId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function deleteAdminPermission(permissionId: string) {
  return apiRequest<null>(`/admin/permissions/${permissionId}`, { method: "DELETE" });
}

export function listRolePermissions(roleId: string) {
  return apiRequest<AdminRolePermissionRead[]>(`/admin/roles/${roleId}/permissions`);
}

export function attachPermissionToRole(roleId: string, permissionId: string) {
  return apiRequest<AdminRolePermissionRead>(`/admin/roles/${roleId}/permissions`, {
    method: "POST",
    body: JSON.stringify({ permission_id: permissionId })
  });
}

export function detachPermissionFromRole(roleId: string, permissionId: string) {
  return apiRequest<null>(`/admin/roles/${roleId}/permissions/${permissionId}`, {
    method: "DELETE"
  });
}

export function listUserRoleAssignments() {
  return apiRequest<AdminUserRoleRead[]>("/admin/user-role-assignments");
}

export function assignRoleToUser(userId: string, roleId: string) {
  return apiRequest<AdminUserRoleRead>(`/admin/users/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify({ role_id: roleId })
  });
}

export function unassignRoleFromUser(userId: string, roleId: string) {
  return apiRequest<null>(`/admin/users/${userId}/roles/${roleId}`, {
    method: "DELETE"
  });
}
