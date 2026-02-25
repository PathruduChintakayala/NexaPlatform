import React from "react";
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import AdminPage from "./page";
import { fakeTokenWithRoles, installLocalStorageStub } from "./test-utils";

describe("Admin page", () => {
  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["admin"]));
  });

  it("renders admin route links", () => {
    render(React.createElement(AdminPage));
    expect(screen.getByText("Admin Console")).toBeDefined();
    expect(screen.getByText("Open roles")).toBeDefined();
    expect(screen.getByText("Open permissions")).toBeDefined();
    expect(screen.getByText("Open user roles")).toBeDefined();
  });
});
