import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/** The ARR track of a source (ADR-0018): read, chapter edits and decision, publish. */
async function forward(req: NextRequest, ctx: { params: Promise<{ id: string; rest: string[] }> }, method: string) {
  const { id, rest } = await ctx.params;
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/sources/${encodeURIComponent(id)}/arr/${rest.map(encodeURIComponent).join("/")}`, {
    method,
    headers: { "content-type": "application/json", ...identity },
    body: method === "GET" ? undefined : await req.text(),
  });
  return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") || "application/json" } });
}

export const GET = (r: NextRequest, c: { params: Promise<{ id: string; rest: string[] }> }) => forward(r, c, "GET");
export const POST = (r: NextRequest, c: { params: Promise<{ id: string; rest: string[] }> }) => forward(r, c, "POST");
export const PUT = (r: NextRequest, c: { params: Promise<{ id: string; rest: string[] }> }) => forward(r, c, "PUT");
