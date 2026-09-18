import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy for reviewer assignment; the API enforces roles and writes the audit event. */
export async function PUT(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/assignment`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...identity },
    body: await req.text(),
  });
  const text = await res.text();
  return new NextResponse(text, { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}
