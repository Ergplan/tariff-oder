import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy: queue a stage re-run (administrator; the API records the actor and chains the stages after it). */
export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/stages/rerun`, {
    method: "POST",
    headers: { "content-type": "application/json", ...identity },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}
