import { NextRequest, NextResponse } from "next/server";
import { API_BASE, identityHeaders } from "@/lib/api";

/**
 * Same-origin proxy for the browser upload.  Streams the multipart body to the API and
 * forwards the caller's identity; the browser never holds API credentials.
 */
export async function POST(req: NextRequest) {
  const id = await identityHeaders();
  const idem = req.headers.get("idempotency-key");
  const body = await req.arrayBuffer();
  const res = await fetch(`${API_BASE}/sources`, {
    method: "POST",
    headers: {
      "content-type": req.headers.get("content-type") || "application/octet-stream",
      ...(idem ? { "Idempotency-Key": idem } : {}),
      ...id,
    },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json", "x-request-id": res.headers.get("x-request-id") || "" },
  });
}
