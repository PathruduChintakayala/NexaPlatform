import { describe, expect, test } from "vitest";

import { getDevToken, setDevToken } from "./auth-storage";

describe("auth storage", () => {
  test("stores and retrieves dev token", () => {
    const store = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
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

    setDevToken("abc123");
    expect(getDevToken()).toBe("abc123");
  });
});
