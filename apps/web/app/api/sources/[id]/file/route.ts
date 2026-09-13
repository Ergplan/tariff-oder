import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Authorized source bytes, streamed through the API (no public or signed URLs). */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/file`, { headers: identity });
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": "application/pdf",
      "content-disposition": res.headers.get("content-disposition") || "inline",
      "cache-control": "private, no-store",
    },
  });
}
