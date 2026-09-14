import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** The publication transaction.  The API enforces the reviewer role, the version and token checks and the completeness rules. */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const body = await req.text();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/publish`, {
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
