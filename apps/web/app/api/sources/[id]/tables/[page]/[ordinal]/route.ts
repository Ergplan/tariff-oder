import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy: the table as the readers read it (raw cell rows) for the review workspace. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string; page: string; ordinal: string }> }) {
  const { id, page, ordinal } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(
    `${API_BASE}/sources/${encodeURIComponent(id)}/tables/${encodeURIComponent(page)}/${encodeURIComponent(ordinal)}/rows`,
    { headers: identity, cache: "no-store" },
  );
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json", "x-request-id": res.headers.get("x-request-id") || "" },
  });
}
