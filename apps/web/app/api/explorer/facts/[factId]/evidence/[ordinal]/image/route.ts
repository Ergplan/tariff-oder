import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Citation drill-down: the cited page of a published fact, rendered from the immutable source bytes. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ factId: string; ordinal: string }> }) {
  const { factId, ordinal } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(
    `${API_BASE}/explorer/facts/${encodeURIComponent(factId)}/evidence/${encodeURIComponent(ordinal)}/image`,
    { headers: identity },
  );
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, { status: 200, headers: { "content-type": "image/png", "cache-control": "private, no-store" } });
}
