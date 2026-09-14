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

/**
 * Service-to-service identity for the API call itself (gcp profile).  Cloud Run's front door
 * requires an invoker token; the metadata server mints one for the web service account with
 * the API URL as audience.  Cached until shortly before expiry.  Never used as the user's
 * identity: the API reads the user from the forwarded headers below.
 */
let s2sToken: { value: string; expiresAt: number } | null = null;

async function serviceToken(): Promise<string | null> {
  if (PROFILE !== "gcp") return null;
  const now = Date.now();
  if (s2sToken && s2sToken.expiresAt > now + 60_000) return s2sToken.value;
  try {
    const res = await fetch(
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(API_BASE)}&format=full`,
      { headers: { "Metadata-Flavor": "Google" }, cache: "no-store", signal: AbortSignal.timeout(3000) },
    );
    if (!res.ok) return null;
    const value = (await res.text()).trim();
    // ID tokens from the metadata server last 60 minutes; refresh after 50.
    s2sToken = { value, expiresAt: now + 50 * 60_000 };
    return value;
  } catch {
    return null;
  }
}

export async function identityHeaders(): Promise<Record<string, string>> {
  const h = await headers();
  if (PROFILE === "gcp") {
    const out: Record<string, string> = {};
    // IAP's assertion identifies the user.  Cloud Run strips Google's reserved x-goog-*
    // identity headers from requests it delivers to the API, so it travels under our own
    // name; the API verifies the signature and audience exactly as before.
    const assertion = h.get("x-goog-iap-jwt-assertion");
    if (assertion) out["X-Forwarded-IAP-Assertion"] = assertion;
    // Without a domain (ADR-0015): the user's Google ID token arrives as the Authorization
    // bearer (gcloud run services proxy); it is forwarded as the user identity, while the
    // call itself carries the web service's own token.
    const auth = h.get("authorization");
    if (auth && auth.toLowerCase().startsWith("bearer ")) out["X-User-Id-Token"] = auth.slice(7).trim();
    const svc = await serviceToken();
    if (svc) out.Authorization = `Bearer ${svc}`;
    return out;
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
    if (res.status === 401 && PROFILE === "gcp") {
      // Diagnostic: which headers the browser/IAP sent us (names only, never values), so an
      // operator can see whether the IAP assertion arrived at the web service at all.
      const names = Array.from((await headers()).keys()).sort();
      console.warn(JSON.stringify({ event: "api_unauthenticated", path, incoming_headers: names }));
    }
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
