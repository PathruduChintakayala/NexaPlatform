import type { ApiErrorEnvelope } from "../types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  envelope?: ApiErrorEnvelope;
  correlationId: string | null;

  constructor(message: string, status: number, envelope?: ApiErrorEnvelope, correlationId?: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
    this.correlationId = correlationId ?? envelope?.correlation_id ?? null;
  }
}

function createCorrelationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem("auth-token") ?? window.localStorage.getItem("nexa.dev.token");
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  const correlationId = createCorrelationId();
  headers.set("x-correlation-id", correlationId);

  if (!(init?.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (token) {
    headers.set("authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (!response.ok) {
    const responseCorrelationId = response.headers.get("x-correlation-id");
    let envelope: ApiErrorEnvelope | undefined;
    try {
      envelope = (await response.json()) as ApiErrorEnvelope;
    } catch {
      envelope = undefined;
    }
    throw new ApiError(
      envelope?.message ?? `Request failed (${response.status})`,
      response.status,
      envelope,
      responseCorrelationId ?? correlationId
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function toQuery(params: object) {
  const search = new URLSearchParams();
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  });
  const raw = search.toString();
  return raw ? `?${raw}` : "";
}
