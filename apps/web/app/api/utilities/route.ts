import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy: add a distribution licensee under a commission (administrator; audited by the API). */
export async function POST(req: NextRequest) {
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/utilities`, { method: "POST", headers: { "content-type": "application/json", ...identity }, body: await req.text() });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}
