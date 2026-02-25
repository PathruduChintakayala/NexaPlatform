import React from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import OpsHubPage from "./page";

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

describe("Ops page", () => {
  beforeEach(() => {
    installLocalStorageStub();
    localStorage.clear();
    localStorage.setItem("auth-token", fakeTokenWithRoles(["ops"]));
  });

  it("renders ops section links", () => {
    render(React.createElement(OpsHubPage));

    expect(screen.getByText("Ops Hub")).toBeDefined();
    expect(screen.getByRole("link", { name: "Plans" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Subscriptions" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Invoices" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Payments" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Journal Entries" })).toBeDefined();
  });
});
