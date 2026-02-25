import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import SalesHubPage from "./sales/page";
import ReportsHubPage from "./reports/page";

function fakeTokenWithRoles(roles: string[]) {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ roles }));
  return `${header}.${payload}.sig`;
}

function installLocalStorageStub() {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => {
        store.clear();
      }
    },
    configurable: true
  });
}

describe("Route hubs", () => {
  it("renders sales and reports hubs", () => {
    installLocalStorageStub();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["sales", "finance"]));
    render(React.createElement(SalesHubPage));
    expect(screen.getByText("Sales Hub")).toBeDefined();

    render(React.createElement(ReportsHubPage));
    expect(screen.getByText("Reports Hub")).toBeDefined();
  });
});
