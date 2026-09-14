import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Publication preview: the consequences of a release over a scope, with the token the publish call must present. */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const body = await req.text();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/publish/preview`, {
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
