import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** The draft queries to the petitioner (Markdown), streamed through the API with the caller's identity. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/arr/reference-filings/${encodeURIComponent(id)}/queries`, { headers: identity });
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "content-disposition": res.headers.get("content-disposition") || `attachment; filename="${id}-draft-queries.md"`,
      "cache-control": "private, no-store",
    },
  });
}
