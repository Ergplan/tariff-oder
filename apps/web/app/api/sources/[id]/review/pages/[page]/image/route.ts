import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * One rendered page for a block of candidates (tariff-table screen).  The API issues an
 * evidence view per candidate on that page for the identity it receives and returns the
 * map in `X-Evidence-View-Ids`; the header is passed through so the table can cite them.
 * Only the bytes that reached the browser count as viewed.
 */
export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string; page: string }> }) {
  const { id, page } = await ctx.params;
  const identity = await identityHeaders();
  const candidates = req.nextUrl.searchParams.get("candidates") || "";
  const res = await fetch(
    `${API_BASE}/sources/${encodeURIComponent(id)}/review/pages/${encodeURIComponent(page)}/image?candidates=${encodeURIComponent(candidates)}`,
    { headers: identity },
  );
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": "image/png",
      "cache-control": "private, no-store",
      "x-evidence-view-ids": res.headers.get("x-evidence-view-ids") || "{}",
      "x-evidence-skipped": res.headers.get("x-evidence-skipped") || "[]",
      "x-evidence-page": res.headers.get("x-evidence-page") || page,
    },
  });
}
