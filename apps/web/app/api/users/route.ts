import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** Same-origin proxy for user administration; the API enforces the administrator role and audits changes. */
export async function GET() {
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/users`, { headers: identity, cache: "no-store" });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}

export async function PUT(req: NextRequest) {
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/users`, { method: "PUT", headers: { "content-type": "application/json", ...identity }, body: await req.text() });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}
