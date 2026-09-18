import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Streams the order's JSON export (zip) to the browser. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/export.zip`, { headers: identity });
  if (!res.ok) return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": "application/zip",
      "content-disposition": res.headers.get("content-disposition") || "attachment",
      "cache-control": "private, no-store",
    },
  });
}
