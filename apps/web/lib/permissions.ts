export function getCurrentRoles(): string[] {
  if (typeof window === "undefined") {
    return [];
  }

  const token = window.localStorage.getItem("auth-token");
  if (!token) {
    return [];
  }

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

export function hasPermission(permission: string, roles: string[]): boolean {
  return roles.includes(permission);
}
