import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

export async function PUT(req: NextRequest, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/commissions/${encodeURIComponent(code)}/assignment`, {
    method: "PUT",
    headers: { "content-type": "application/json", ...identity },
    body: await req.text(),
  });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}
