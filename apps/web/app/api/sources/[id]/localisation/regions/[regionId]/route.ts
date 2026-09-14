import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy for a reviewer's note on one localisation region (PUT). */
export async function PUT(req: NextRequest, ctx: { params: Promise<{ id: string; regionId: string }> }) {
  const { id, regionId } = await ctx.params;
  const identity = await identityHeaders();
  const body = await req.text();
  const res = await fetch(
    `${API_BASE}/sources/${encodeURIComponent(id)}/localisation/regions/${encodeURIComponent(regionId)}`,
    { method: "PUT", headers: { "content-type": "application/json", ...identity }, body },
  );
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json", "x-request-id": res.headers.get("x-request-id") || "" },
  });
}
