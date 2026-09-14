import type { ErrorResponse } from "@tariff/contracts";

/**
 * Turn any failed same-origin call into an ErrorResponse the form can show.  A non-JSON
 * body (an HTML sign-in page from IAP after the session expired, a gateway error) becomes
 * a plain message with the status, never a silent failure.
 */
export async function readError(res: Response): Promise<ErrorResponse> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as Partial<ErrorResponse>;
    if (j && typeof j.message === "string") return j as ErrorResponse;
  } catch {
    // not JSON
  }
  const signIn = res.status === 401 || res.status === 403 || /accounts\.google\.com|sign in/i.test(text);
  return {
    error_type: signIn ? "unauthenticated" : "internal_error",
    message: signIn ? `The request was not accepted (${res.status}); your sign-in session may have expired.` : `The server answered ${res.status}.`,
    next_step: signIn ? "Reload the page, sign in again if asked, then retry." : "Retry; if it persists, report the request id.",
    detail: text.slice(0, 200) || null,
    severity: "error",
    request_id: res.headers.get("x-request-id"),
  };
}

export function networkError(what: string): ErrorResponse {
  return {
    error_type: "provider_unavailable",
    message: `${what} could not reach the server.`,
    next_step: "Check your connection and retry; nothing was recorded.",
    severity: "error",
    request_id: null,
  };
}
