import { api } from "@/lib/api.ts";

export const dynamic = "force-dynamic";

export function GET(req: Request) {
  const p = new URL(req.url).searchParams;
  const state = p.get("state")?.toUpperCase() || null;
  const kind = p.get("kind") || null;
  return api(async (sql) => ({
    utilities: await sql`
      SELECT u.code, u.name, u.kind, u.commission, u.state, u.ownership, u.aliases,
             c.orders::int, c.orders_read::int, c.years_with_arr::int, c.latest_approved_year
      FROM utilities u JOIN v_coverage c ON c.utility = u.code
      WHERE (${state}::text IS NULL OR u.state = ${state}) AND (${kind}::text IS NULL OR u.kind = ${kind})
      ORDER BY u.state, u.code`,
  }));
}
