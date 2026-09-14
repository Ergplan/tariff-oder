import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * Same-origin proxy for the reviewer's localisation decision.  Forwards the caller's identity;
 * the API enforces the reviewer role and records the audit event.  The browser never holds
 * API credentials.
 */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const body = await req.text();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/localisation/decision`, {
    method: "POST",
    headers: { "content-type": "application/json", ...identity },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json", "x-request-id": res.headers.get("x-request-id") || "" },
  });
}
