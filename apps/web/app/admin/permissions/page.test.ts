import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { screen } from "@testing-library/react";

import AdminPermissionsPage from "./page";
import { fakeTokenWithRoles, installLocalStorageStub, renderWithQueryClient } from "../test-utils";

const { listAdminPermissions } = vi.hoisted(() => ({
  listAdminPermissions: vi.fn()
}));

vi.mock("../../../lib/api/admin", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api/admin")>();
  return {
    ...actual,
    listAdminPermissions
  };
});

describe("Admin permissions page", () => {
  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["admin"]));
    listAdminPermissions.mockResolvedValue([]);
  });

  it("renders page shell", async () => {
    renderWithQueryClient(React.createElement(AdminPermissionsPage));
    expect(await screen.findByText("Admin · Permissions")).toBeDefined();
  });
});
