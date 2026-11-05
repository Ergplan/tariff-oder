import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * Same-origin proxy for the client application's actions (ADR-0019).  Only these API areas
 * are reachable through it; the API decides every permission with the caller's identity.
 */
const ALLOWED = ["cases", "organisations", "library", "arr"];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }, method: string) {
  const { path } = await ctx.params;
  if (!path.length || !ALLOWED.includes(path[0])) return new NextResponse("not found", { status: 404 });
  const identity = await identityHeaders();
  const url = `${API_BASE}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  // a file upload (a case's petition workbook) is forwarded as the multipart body it is
  const type = req.headers.get("content-type") || "";
  const multipart = type.startsWith("multipart/form-data");
  const body = method === "GET" || method === "DELETE" ? undefined : multipart ? await req.arrayBuffer() : await req.text();
  const res = await fetch(url, { method, headers: { "content-type": multipart ? type : "application/json", ...identity }, body });
  const headers: Record<string, string> = { "content-type": res.headers.get("content-type") || "application/json" };
  const cd = res.headers.get("content-disposition");
  if (cd) headers["content-disposition"] = cd;
  return new NextResponse(res.status === 204 ? null : res.body, { status: res.status, headers });
}

export const GET = (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => forward(req, ctx, "GET");
export const POST = (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => forward(req, ctx, "POST");
export const PUT = (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => forward(req, ctx, "PUT");
export const PATCH = (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => forward(req, ctx, "PATCH");
export const DELETE = (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => forward(req, ctx, "DELETE");
