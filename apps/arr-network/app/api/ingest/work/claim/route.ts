import { ingestGuard, dbError } from "@/lib/ingest/http.ts";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const g = await ingestGuard(req, true);
  if (g instanceof Response) return g;
  const b = g.json as { agent?: unknown; kinds?: unknown; limit?: unknown };
  const extra = b && typeof b === "object" ? Object.keys(b).filter((k) => !["agent", "kinds", "limit"].includes(k)) : [];
  if (!b || typeof b !== "object" || typeof b.agent !== "string" || !b.agent.trim() || extra.length) {
    return Response.json({ error: "body must be {agent, kinds: [..], limit?}" }, { status: 400 });
  }
  if (!Array.isArray(b.kinds) || !b.kinds.length || b.kinds.some((k) => typeof k !== "string")) {
    return Response.json({ error: "kinds must be a non-empty list of strings" }, { status: 400 });
  }
  const limit = b.limit === undefined ? 1 : Number(b.limit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) return Response.json({ error: "limit must be an integer 1..100" }, { status: 400 });
  try {
    const items = await g.sql`
      UPDATE work_items w SET state = 'claimed', claimed_by = ${b.agent}, claimed_at = now(), attempts = w.attempts + 1
      WHERE w.work_id IN (
        SELECT work_id FROM work_items
        WHERE state = 'queued' AND kind IN (SELECT jsonb_array_elements_text(${JSON.stringify(b.kinds)}::text::jsonb))
        ORDER BY priority, work_id
        LIMIT ${limit}
        FOR UPDATE SKIP LOCKED)
      RETURNING w.work_id, w.kind, w.target, w.attempts`;
    return Response.json({ items: [...items].sort((x, y) => (x.work_id as number) - (y.work_id as number)) });
  } catch (e) {
    return dbError(e);
  }
}
