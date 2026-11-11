import { db, isConnectionError, type Sql } from "../db.ts";
import { checkAuth } from "./auth.ts";
import { MAX_BYTES } from "./validate.ts";

/** Auth, a configured database, and a JSON body (when `body` is true) — or the error response. */
export async function ingestGuard(req: Request, body: boolean): Promise<{ sql: Sql; json: unknown } | Response> {
  const denied = checkAuth(req);
  if (denied) return denied;
  const sql = db();
  if (!sql) return Response.json({ error: "database not connected: DATABASE_URL is not set" }, { status: 503 });
  if (!body) return { sql, json: null };
  const len = Number(req.headers.get("content-length") || 0);
  if (len > MAX_BYTES) return Response.json({ error: "body larger than 8 MB" }, { status: 413 });
  const text = await req.text();
  if (Buffer.byteLength(text, "utf8") > MAX_BYTES) return Response.json({ error: "body larger than 8 MB" }, { status: 413 });
  try {
    return { sql, json: text ? JSON.parse(text) : {} };
  } catch {
    return Response.json({ error: "malformed JSON" }, { status: 400 });
  }
}

export function dbError(e: unknown): Response {
  if (isConnectionError(e)) return Response.json({ error: "database unreachable" }, { status: 503 });
  const err = e as { code?: string; message?: string };
  if (err?.code === "42P01") return Response.json({ error: "schema not applied: POST /api/ingest/migrate" }, { status: 503 });
  console.error(e);
  return Response.json({ error: "internal error" }, { status: 500 });
}
