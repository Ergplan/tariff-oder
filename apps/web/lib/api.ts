/**
 * Server-side API client.  The web app never talks to the database; every read goes through
 * the FastAPI service with the caller's identity forwarded.
 *
 * Identity forwarding is profile-specific and mirrors the backend adapters:
 *  - local: the `X-Local-User` header is taken from the LOCAL_WEB_USER env var (dev/CI only).
 *  - gcp:   the IAP assertion header of the incoming request is forwarded unchanged; the API
 *           verifies it.  The web app never mints identities.
 */
import { headers } from "next/headers";
import type { ErrorResponse } from "@tariff/contracts";

export const API_BASE = process.env.API_BASE_URL || "http://localhost:8000";
export const PROFILE = process.env.DEPLOYMENT_PROFILE || "local";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ErrorResponse,
  ) {
    super(body.message);
  }
}

export async function identityHeaders(): Promise<Record<string, string>> {
  const h = await headers();
  if (PROFILE === "gcp") {
    const assertion = h.get("x-goog-iap-jwt-assertion");
    return assertion ? { "x-goog-iap-jwt-assertion": assertion } : {};
  }
  const user = process.env.LOCAL_WEB_USER;
  return user ? { "X-Local-User": user } : {};
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const id = await identityHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), ...id },
    cache: "no-store",
  });
  if (!res.ok) {
    let body: ErrorResponse;
    try {
      body = (await res.json()) as ErrorResponse;
    } catch {
      body = {
        error_type: "internal_error",
        message: `API returned ${res.status}`,
        next_step: "Retry; if it persists, report the request id.",
        severity: "error",
        request_id: res.headers.get("x-request-id"),
      };
    }
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

/** Fetch that returns an error envelope instead of throwing, for pages that render errors. */
export async function apiTry<T>(path: string, init?: RequestInit): Promise<{ data?: T; error?: ErrorResponse }> {
  try {
    return { data: await apiFetch<T>(path, init) };
  } catch (e) {
    if (e instanceof ApiError) return { error: e.body };
    return {
      error: {
        error_type: "provider_unavailable",
        message: "The API is not reachable.",
        next_step: "Check that the API service is running and API_BASE_URL is correct.",
        severity: "critical",
        detail: e instanceof Error ? e.message : String(e),
      },
    };
  }
}
