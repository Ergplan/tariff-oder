import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** A combined order's licensees (increment 35): read them, or set them (administrator). */
async function forward(req: NextRequest, ctx: { params: Promise<{ id: string }> }, method: string) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/licensees`, {
    method,
    headers: { "content-type": "application/json", ...identity },
    body: method === "GET" ? undefined : await req.text(),
  });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}

export const GET = (r: NextRequest, c: { params: Promise<{ id: string }> }) => forward(r, c, "GET");
export const PUT = (r: NextRequest, c: { params: Promise<{ id: string }> }) => forward(r, c, "PUT");
