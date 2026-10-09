import type { AuthStorageState } from "@/lib/types";

const STORAGE_KEY = "caseflow.auth";

export function loadAuthState(): AuthStorageState | null {
  if (typeof window === "undefined") {
    return null;
  }
  const rawValue = window.localStorage.getItem(STORAGE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as AuthStorageState;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function persistAuthState(state: AuthStorageState) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function clearAuthState() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(STORAGE_KEY);
}
