"use client";

import React from "react";
import { useMemo } from "react";

import { AccessDeniedPanel } from "./access-denied-panel";

interface RouteGuardProps {
  requiredRoles?: string[];
  children: React.ReactNode;
}

function decodeRolesFromJwt(token: string): string[] {
  const parts = token.split(".");
  if (parts.length < 2) {
    return [];
  }

  try {
    const payloadSegment = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payloadSegment.padEnd(Math.ceil(payloadSegment.length / 4) * 4, "=");
    const payload = JSON.parse(atob(padded)) as { roles?: unknown };
    if (!Array.isArray(payload.roles)) {
      return [];
    }
    return payload.roles.filter((role): role is string => typeof role === "string");
  } catch {
    return [];
  }
}

function getToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("auth-token") ?? localStorage.getItem("nexa.dev.token");
}

export function RouteGuard({ requiredRoles = [], children }: RouteGuardProps) {
  const state = useMemo(() => {
    const token = getToken();
    if (!token) {
      return { allowed: false, status: 401 as const };
    }

    if (requiredRoles.length === 0) {
      return { allowed: true, status: 200 as const };
    }

    const roles = decodeRolesFromJwt(token);
    const normalized = new Set(roles.map((role) => role.toLowerCase()));
    const allowed = requiredRoles.some((role) => normalized.has(role.toLowerCase()));
    return { allowed, status: allowed ? (200 as const) : (403 as const) };
  }, [requiredRoles]);

  if (!state.allowed) {
    return <AccessDeniedPanel statusCode={state.status === 401 ? 401 : 403} />;
  }

  return <>{children}</>;
}
