import type { ClientPlatform } from "./platform";

const OVERRIDE_STORAGE_KEY = "triageassist.apiBaseUrl";

/*
 * The API base URL is empty for the web build, which means "same origin": the
 * Vite dev server proxies /api and the built dashboard is served beside the
 * API. A native WebView has its own origin, so it needs an absolute URL.
 *
 * Resolution order:
 *   1. an override saved on the device (native Server setting)
 *   2. VITE_API_BASE_URL, baked in by `npm run build:web`
 *   3. the platform default
 */
export interface ApiBaseUrlInput {
  platform: ClientPlatform;
  configured?: string;
  override?: string;
}

const NATIVE_LOOPBACK_BASE_URL = "http://localhost:8000";

/**
 * Accept only an absolute http(s) origin. A path, query or fragment is
 * rejected rather than silently dropped: every API path already starts with
 * `/api`, so a base with a path would produce ambiguous URLs.
 */
export function normaliseApiBaseUrl(value: string | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return null;
  }
  if (url.username || url.password || url.search || url.hash) {
    return null;
  }
  if (url.pathname !== "/" && url.pathname !== "") {
    return null;
  }

  return url.origin;
}

export function defaultApiBaseUrl(platform: ClientPlatform): string {
  return platform === "web" ? "" : NATIVE_LOOPBACK_BASE_URL;
}

export function resolveApiBaseUrl(input: ApiBaseUrlInput): string {
  return (
    normaliseApiBaseUrl(input.override) ??
    normaliseApiBaseUrl(input.configured) ??
    defaultApiBaseUrl(input.platform)
  );
}

export function apiUrl(path: string, input: ApiBaseUrlInput): string {
  const base = resolveApiBaseUrl(input);
  return base ? `${base}${path}` : path;
}

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readApiBaseUrlOverride(): string | undefined {
  try {
    return browserStorage()?.getItem(OVERRIDE_STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Returns false and leaves the saved value untouched when the URL is invalid. */
export function saveApiBaseUrlOverride(value: string): boolean {
  const normalised = normaliseApiBaseUrl(value);
  if (normalised === null) {
    return false;
  }
  try {
    browserStorage()?.setItem(OVERRIDE_STORAGE_KEY, normalised);
  } catch {
    return false;
  }
  return true;
}

export function clearApiBaseUrlOverride(): void {
  try {
    browserStorage()?.removeItem(OVERRIDE_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, disabled WebView storage).
  }
}
