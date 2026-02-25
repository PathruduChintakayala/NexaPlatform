import { afterEach, describe, expect, it, vi } from "vitest";

import { getFinanceArAging } from "./api";

describe("finance report api wrappers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls AR aging endpoint with query params", async () => {
    Object.defineProperty(window, "localStorage", {
      value: { getItem: () => null },
      configurable: true
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ as_of_date: "2026-02-25", total_amount_due: "10.000000", buckets: [], rows: [] })
    });
    vi.stubGlobal("fetch", fetchMock);

    const data = await getFinanceArAging({ tenant_id: "tenant-a", company_code: "C1", as_of_date: "2026-02-25" });

    expect(data.total_amount_due).toBe("10.000000");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/reports/finance/ar-aging?tenant_id=tenant-a&company_code=C1&as_of_date=2026-02-25");
  });
});
