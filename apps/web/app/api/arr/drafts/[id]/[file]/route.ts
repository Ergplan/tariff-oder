import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

const FILES: Record<string, string> = {
  "petition.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "formats.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};

/** A draft petition's DOCX or XLSX, streamed through the API with the caller's identity. */
export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string; file: string }> }) {
  const { id, file } = await ctx.params;
  if (!FILES[file]) return new NextResponse("not found", { status: 404 });
  const identity = await identityHeaders();
  const res = await fetch(`${API_BASE}/arr/drafts/${encodeURIComponent(id)}/${file}`, { headers: identity });
  if (!res.ok) {
    return new NextResponse(await res.text(), { status: res.status, headers: { "content-type": "application/json" } });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "content-type": FILES[file],
      "content-disposition": res.headers.get("content-disposition") || `attachment; filename="${file}"`,
      "cache-control": "private, no-store",
    },
  });
}
