import { load, type Sql } from "./db.ts";

export const NOTE = "Machine-read from the orders. A figure is reviewed by a person only where reviewed_by is set; consensus says how many independent readers gave the same value.";

/** Run the queries of a JSON endpoint; 503 when the database is absent or unreachable, 404 on null. */
export async function api(fn: (sql: Sql) => Promise<unknown>): Promise<Response> {
  const res = await load(fn);
  if (!res.ok) return Response.json({ error: "database not connected", reason: res.reason }, { status: 503 });
  if (res.data === null) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json({ note: NOTE, ...(res.data as object) }, { headers: { "cache-control": "public, max-age=60" } });
}
