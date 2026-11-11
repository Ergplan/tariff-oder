import { api } from "@/lib/api.ts";

export const dynamic = "force-dynamic";

export function GET() {
  return api(async (sql) => ({
    states: await sql`
      SELECT s.code, s.name, s.kind,
        (SELECT array_agg(cs.commission ORDER BY cs.commission) FROM commission_states cs WHERE cs.state = s.code) AS commissions,
        (SELECT count(*) FROM utilities u WHERE u.state = s.code)::int AS utilities,
        (SELECT count(DISTINCT ou.order_id) FROM order_utilities ou JOIN utilities u ON u.code = ou.utility WHERE u.state = s.code)::int AS orders,
        (SELECT count(DISTINCT ou.order_id) FROM order_utilities ou JOIN utilities u ON u.code = ou.utility JOIN orders o ON o.order_id = ou.order_id
          WHERE u.state = s.code AND o.read_status = 'read')::int AS orders_read,
        (SELECT count(DISTINCT a.utility) FROM v_arr a WHERE a.state = s.code)::int AS utilities_with_arr
      FROM states s ORDER BY s.code`,
  }));
}
