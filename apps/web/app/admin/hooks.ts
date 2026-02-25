"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  assignRoleToUser,
  attachPermissionToRole,
  createAdminPermission,
  createAdminRole,
  deleteAdminPermission,
  deleteAdminRole,
  detachPermissionFromRole,
  listAdminPermissions,
  listAdminRoles,
  listRolePermissions,
  listUserRoleAssignments,
  unassignRoleFromUser,
  updateAdminPermission,
  updateAdminRole
} from "../../lib/api/admin";
import { ApiError } from "../../lib/api/core";
import { queryKeys } from "../../lib/queryKeys";

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const correlationId = error.correlationId ? ` (Correlation ID: ${error.correlationId})` : "";
    return `${error.message}${correlationId}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed";
}

export function safeText(value: unknown): string {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  return "—";
}

export function useAdminRolesData() {
  const queryClient = useQueryClient();

  const rolesQuery = useQuery({
    queryKey: queryKeys.admin.roles(),
    queryFn: listAdminRoles
  });

  const permissionsQuery = useQuery({
    queryKey: queryKeys.admin.permissions(),
    queryFn: listAdminPermissions
  });

  const createRoleMutation = useMutation({
    mutationFn: createAdminRole,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.roles() });
    }
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ roleId, body }: { roleId: string; body: Parameters<typeof updateAdminRole>[1] }) => updateAdminRole(roleId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.roles() });
    }
  });

  const deleteRoleMutation = useMutation({
    mutationFn: deleteAdminRole,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.roles() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.userRoleAssignments() });
    }
  });

  const attachPermissionMutation = useMutation({
    mutationFn: ({ roleId, permissionId }: { roleId: string; permissionId: string }) => attachPermissionToRole(roleId, permissionId),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.rolePermissions(variables.roleId) });
    }
  });

  const detachPermissionMutation = useMutation({
    mutationFn: ({ roleId, permissionId }: { roleId: string; permissionId: string }) => detachPermissionFromRole(roleId, permissionId),
    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.rolePermissions(variables.roleId) });
    }
  });

  return {
    rolesQuery,
    permissionsQuery,
    createRoleMutation,
    updateRoleMutation,
    deleteRoleMutation,
    attachPermissionMutation,
    detachPermissionMutation
  };
}

export function useRolePermissions(roleId: string | null) {
  return useQuery({
    queryKey: queryKeys.admin.rolePermissions(roleId ?? ""),
    queryFn: () => listRolePermissions(roleId ?? ""),
    enabled: Boolean(roleId)
  });
}

export function useAdminPermissionsData() {
  const queryClient = useQueryClient();

  const permissionsQuery = useQuery({
    queryKey: queryKeys.admin.permissions(),
    queryFn: listAdminPermissions
  });

  const createPermissionMutation = useMutation({
    mutationFn: createAdminPermission,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.permissions() });
    }
  });

  const updatePermissionMutation = useMutation({
    mutationFn: ({ permissionId, body }: { permissionId: string; body: Parameters<typeof updateAdminPermission>[1] }) =>
      updateAdminPermission(permissionId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.permissions() });
    }
  });

  const deletePermissionMutation = useMutation({
    mutationFn: deleteAdminPermission,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.permissions() });
      await queryClient.invalidateQueries({ queryKey: ["admin", "rolePermissions"] });
    }
  });

  return {
    permissionsQuery,
    createPermissionMutation,
    updatePermissionMutation,
    deletePermissionMutation
  };
}

export function useAdminUserRolesData(userIdFilter: string) {
  const queryClient = useQueryClient();

  const assignmentsQuery = useQuery({
    queryKey: queryKeys.admin.userRoleAssignments(),
    queryFn: listUserRoleAssignments
  });

  const rolesQuery = useQuery({
    queryKey: queryKeys.admin.roles(),
    queryFn: listAdminRoles
  });

  const assignRoleMutation = useMutation({
    mutationFn: ({ userId, roleId }: { userId: string; roleId: string }) => assignRoleToUser(userId, roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.userRoleAssignments() });
    }
  });

  const unassignRoleMutation = useMutation({
    mutationFn: ({ userId, roleId }: { userId: string; roleId: string }) => unassignRoleFromUser(userId, roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.userRoleAssignments() });
    }
  });

  const userRoles = useMemo(() => {
    const normalized = userIdFilter.trim().toLowerCase();
    if (!normalized) {
      return [];
    }
    return (assignmentsQuery.data ?? []).filter((assignment) => assignment.user_id.toLowerCase().includes(normalized));
  }, [assignmentsQuery.data, userIdFilter]);

  return {
    rolesQuery,
    assignmentsQuery,
    userRoles,
    assignRoleMutation,
    unassignRoleMutation
  };
}
