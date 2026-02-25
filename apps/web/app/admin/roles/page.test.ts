import React from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import AdminRolesPage from "./page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "../test-utils";

const apiBase = "http://localhost:8000";
let roles = [
  { id: "role-1", name: "admin", description: "System admin", is_system: true, created_at: "2026-02-25" },
  { id: "role-2", name: "ops", description: null, is_system: false, created_at: "2026-02-25" }
];

const permissions = [
  {
    id: "perm-1",
    resource: "crm.contact",
    action: "read",
    field: "*",
    scope_type: null,
    scope_value: null,
    effect: "allow",
    description: null,
    created_at: "2026-02-25"
  }
];

const rolePermissionsByRole: Record<string, Array<{ permission_id: string; resource: string; action: string; field: string | null }>> = {
  "role-1": [{ permission_id: "perm-1", resource: "crm.contact", action: "read", field: "*" }],
  "role-2": []
};

const server = setupServer(
  http.get(`${apiBase}/admin/roles`, () => HttpResponse.json(roles)),
  http.post(`${apiBase}/admin/roles`, async ({ request }) => {
    const body = (await request.json()) as { name: string; description?: string | null };
    const created = {
      id: `role-${roles.length + 1}`,
      name: body.name,
      description: body.description ?? null,
      is_system: false,
      created_at: "2026-02-25"
    };
    roles = [...roles, created];
    rolePermissionsByRole[created.id] = [];
    return HttpResponse.json(created, { status: 201 });
  }),
  http.get(`${apiBase}/admin/permissions`, () => HttpResponse.json(permissions)),
  http.get(`${apiBase}/admin/roles/:roleId/permissions`, ({ params }) => {
    const roleId = String(params.roleId);
    const items = rolePermissionsByRole[roleId] ?? [];
    return HttpResponse.json(
      items.map((item) => ({
        role_id: roleId,
        role_name: roles.find((role) => role.id === roleId)?.name ?? "unknown",
        permission_id: item.permission_id,
        resource: item.resource,
        action: item.action,
        field: item.field,
        scope_type: null,
        scope_value: null,
        effect: "allow",
        created_at: "2026-02-25"
      }))
    );
  })
);

describe("Admin roles page", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());

  beforeEach(() => {
    roles = [
      { id: "role-1", name: "admin", description: "System admin", is_system: true, created_at: "2026-02-25" },
      { id: "role-2", name: "ops", description: null, is_system: false, created_at: "2026-02-25" }
    ];
    rolePermissionsByRole["role-1"] = [{ permission_id: "perm-1", resource: "crm.contact", action: "read", field: "*" }];
    rolePermissionsByRole["role-2"] = [];

    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["admin"]));
  });

  it("renders page shell", async () => {
    renderWithQueryClient(React.createElement(AdminRolesPage));
    expect(await screen.findByText("Admin · Roles")).toBeDefined();
  });

  it("creates role then refreshes list", async () => {
    renderWithQueryClient(React.createElement(AdminRolesPage));

    expect(await screen.findByText("ops")).toBeDefined();

    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "Create role" })[0]);
    await user.type(screen.getByLabelText("Name"), "finance-viewer");
    await user.type(screen.getByLabelText("Description"), "Finance read-only");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getByText("finance-viewer")).toBeDefined();
    });
  });
});
