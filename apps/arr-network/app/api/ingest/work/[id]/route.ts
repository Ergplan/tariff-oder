import { ingestGuard, dbError } from "@/lib/ingest/http.ts";
import { WORK_DONE_STATES } from "@/lib/ingest/validate.ts";

export const dynamic = "force-dynamic";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const g = await ingestGuard(req, true);
  if (g instanceof Response) return g;
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return Response.json({ error: "work id must be an integer" }, { status: 400 });
  const b = g.json as { state?: unknown; result?: unknown; error?: unknown };
  const extra = b && typeof b === "object" ? Object.keys(b).filter((k) => !["state", "result", "error"].includes(k)) : [];
  if (!b || typeof b !== "object" || extra.length || typeof b.state !== "string" || !(WORK_DONE_STATES as readonly string[]).includes(b.state)) {
    return Response.json({ error: "body must be {state: done|failed|parked, result?, error?}" }, { status: 400 });
  }
  if (b.error !== undefined && b.error !== null && typeof b.error !== "string") return Response.json({ error: "error must be a string" }, { status: 400 });
  try {
    const r = await g.sql`
      UPDATE work_items SET state = ${b.state}, finished_at = now(),
        result = ${b.result === undefined ? null : JSON.stringify(b.result)}::text::jsonb, error = ${(b.error as string) ?? null}
      WHERE work_id = ${Number(id)} AND state = 'claimed'
      RETURNING work_id, kind, target, state, attempts`;
    if (!r.length) {
      const e = await g.sql`SELECT state FROM work_items WHERE work_id = ${Number(id)}`;
      if (!e.length) return Response.json({ error: "no such work item" }, { status: 404 });
      return Response.json({ error: `work item is ${e[0].state}, not claimed` }, { status: 409 });
    }
    return Response.json(r[0]);
  } catch (e) {
    return dbError(e);
  }
}
