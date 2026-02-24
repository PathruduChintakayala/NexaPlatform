"use client";

import type { HealthResponse } from "@nexa/shared";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../lib/api-client";
import { getDevToken } from "../lib/auth-storage";

export function HealthPanel() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/health", undefined, getDevToken())
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-base font-semibold">API Health</h3>
      <p className="mt-1 text-sm text-slate-500">TanStack Query fetch against FastAPI.</p>
      <pre className="mt-3 rounded-md bg-slate-900 p-3 text-xs text-slate-100">
        {health.isLoading ? "Loading..." : JSON.stringify(health.data, null, 2)}
      </pre>
    </div>
  );
}
