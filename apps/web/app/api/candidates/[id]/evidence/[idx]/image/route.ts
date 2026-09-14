import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * Rendered evidence page for one candidate.  The API records the view for the identity it
 * receives and returns its id in `X-Evidence-View-Id`; that header is passed through so the
 * review form can cite it.  Only the bytes that reached the browser count as viewed.
 */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string; idx: string }> }) {
  const { id, idx } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/candidates/${encodeURIComponent(id)}/evidence/${encodeURIComponent(idx)}/image`, {
    headers: identity,
  });
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": "image/png",
      "cache-control": "private, no-store",
      "x-evidence-view-id": res.headers.get("x-evidence-view-id") || "",
      "x-evidence-page": res.headers.get("x-evidence-page") || "",
      "x-evidence-highlighted": res.headers.get("x-evidence-highlighted") || "0",
      "x-evidence-meta": res.headers.get("x-evidence-meta") || "{}",
    },
  });
}
