import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";

import AdminUserRolesPage from "./page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "../test-utils";

const { listAdminRoles, listUserRoleAssignments } = vi.hoisted(() => ({
  listAdminRoles: vi.fn(),
  listUserRoleAssignments: vi.fn()
}));

vi.mock("../../../lib/api/admin", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api/admin")>();
  return {
    ...actual,
    listAdminRoles,
    listUserRoleAssignments
  };
});

describe("Admin user roles page", () => {
  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["admin"]));
    listAdminRoles.mockResolvedValue([]);
    listUserRoleAssignments.mockResolvedValue([]);
  });

  it("renders page shell", async () => {
    renderWithQueryClient(React.createElement(AdminUserRolesPage));
    expect(await screen.findByText("Admin · User Roles")).toBeDefined();
  });
});
