import { ingestGuard, dbError } from "@/lib/ingest/http.ts";
import { MIGRATION_VERSIONS } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

const TABLES = [
  "states", "commissions", "utilities", "heads", "parameter_defs", "orders", "order_utilities", "pages", "parses",
  "parsed_tables", "arr_values", "facts", "fact_readings", "parameters", "paragraphs", "chunks", "work_items",
  "agent_runs", "metrics", "findings", "briefs", "gold_figures",
];

export async function GET(req: Request) {
  const g = await ingestGuard(req, false);
  if (g instanceof Response) return g;
  try {
    const [{ exists }] = await g.sql`SELECT to_regclass('public.schema_migrations') IS NOT NULL AS exists`;
    if (!exists) return Response.json({ schema_version: null, applied: [], pending: MIGRATION_VERSIONS, counts: {} });
    const applied = (await g.sql`SELECT version FROM schema_migrations ORDER BY version`).map((r) => r.version as string);
    const counts: Record<string, number> = {};
    const q = TABLES.map((t) => `SELECT '${t}' AS t, count(*)::int AS n FROM ${t}`).join(" UNION ALL ");
    for (const r of await g.sql.unsafe(q)) counts[r.t as string] = r.n as number;
    return Response.json({
      schema_version: applied[applied.length - 1] ?? null,
      applied,
      pending: MIGRATION_VERSIONS.filter((v) => !applied.includes(v)),
      counts,
    });
  } catch (e) {
    return dbError(e);
  }
}
