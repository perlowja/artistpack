/**
 * Browser-side session storage for the HMAC session token the backend
 * issues on successful OAuth callback. The token is opaque to the client
 * (we never decode it server-side; we just attach it as a Bearer header).
 *
 * Storage is intentionally **client-only**. The dashboard is built as a
 * CSR + thin RSC shell, so `localStorage` is the right home for it:
 * survives across reloads and tabs, but never leaks to the server.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "artistpack.session";

export interface StoredSession {
  token: string;
  /** Substring of the user display name at the moment of sign-in — purely
   *  cosmetic for the dashboard chrome, not trusted for anything. */
  displayName: string | null;
  /** When the token expires, in epoch milliseconds. Used to avoid issuing
   *  API calls we know will 401. Not authoritative — the backend still
   *  enforces expiry. */
  expiresAt: number;
}

export function saveSession(s: StoredSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // localStorage can be disabled (private mode, etc.). Fail silently
    // — the session just won't survive a reload.
  }
}

export function loadSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.expiresAt !== "number"
    ) {
      return null;
    }
    return {
      token: parsed.token,
      displayName: parsed.displayName ?? null,
      expiresAt: parsed.expiresAt,
    };
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/**
 * `useSession` returns the stored session reactively. SSR-safe: returns
 * `null` until the first effect tick on the client.
 */
export function useSession(): StoredSession | null {
  const [session, setSession] = useState<StoredSession | null>(null);
  useEffect(() => {
    setSession(loadSession());
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setSession(loadSession());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return session;
}

/** Hook variant that also auto-polls the storage layer so other tabs'
 *  sign-in / sign-out events propagate without a manual refresh. */
export function useSessionStable(): StoredSession | null {
  return useSession();
}