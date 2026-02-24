const STORAGE_KEY = "nexa.dev.token";

export function getDevToken(): string {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_DEV_TOKEN ?? "";
  }
  return localStorage.getItem(STORAGE_KEY) ?? process.env.NEXT_PUBLIC_DEV_TOKEN ?? "";
}

export function setDevToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, token);
  }
}
