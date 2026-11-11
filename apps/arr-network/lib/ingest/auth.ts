import { timingSafeEqual, createHash } from "node:crypto";

/** 503 when INGEST_TOKEN is unset, 401 on a wrong or missing bearer token, null when allowed. */
export function checkAuth(req: Request): Response | null {
  const token = process.env.INGEST_TOKEN;
  if (!token) return Response.json({ error: "ingest is disabled: INGEST_TOKEN is not set on the server" }, { status: 503 });
  const header = req.headers.get("authorization") || "";
  const m = /^Bearer\s+(.+)$/i.exec(header.trim());
  // Compare digests so the comparison takes the same time whatever the lengths.
  const a = createHash("sha256").update(m ? m[1] : "").digest();
  const b = createHash("sha256").update(token).digest();
  if (!m || !timingSafeEqual(a, b)) return Response.json({ error: "bad token" }, { status: 401 });
  return null;
}
