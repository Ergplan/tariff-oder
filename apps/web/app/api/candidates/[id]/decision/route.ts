import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * Same-origin proxy for a reviewer decision.  Forwards the caller's identity and the
 * client's Idempotency-Key; the API enforces the reviewer role, the rendered-evidence rule,
 * the version check and the audit event.  The browser never holds API credentials.
 */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const body = await req.text();
  const key = req.headers.get("idempotency-key");
  const res = await fetch(`${API_BASE}/candidates/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(key ? { "Idempotency-Key": key } : {}), ...identity },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json", "x-request-id": res.headers.get("x-request-id") || "" },
  });
}
