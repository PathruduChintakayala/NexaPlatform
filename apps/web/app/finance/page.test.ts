import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import FinancePage from "./page";

describe("Finance page", () => {
  it("renders finance reporting title", () => {
    render(React.createElement(FinancePage));
    expect(screen.getByText("Finance Reporting")).toBeDefined();
  });
});
