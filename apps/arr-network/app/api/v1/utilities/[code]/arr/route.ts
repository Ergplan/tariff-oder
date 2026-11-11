import { api } from "@/lib/api.ts";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  return api(async (sql) => {
    const [u] = await sql`SELECT code, name, kind, commission, state, ownership FROM utilities WHERE code = ${code}`;
    if (!u) return null;
    const figures = await sql`
      SELECT fact_id, fiscal_year, voice, stage, value_crore, label, consensus, readers, reviewed_by, reviewed_at, page, quote,
             order_id, order_title, order_url, order_arr_year, headline_why
      FROM v_arr WHERE utility = ${code} ORDER BY fiscal_year, voice, order_arr_year NULLS FIRST, fact_id`;
    const latest = await sql`
      SELECT fact_id, fiscal_year, voice, stage, value_crore, consensus, reviewed_by, page, order_id, order_url
      FROM v_arr_latest WHERE utility = ${code} ORDER BY fiscal_year, voice`;
    return {
      utility: u,
      latest,
      all_bottom_lines: figures.map((f) => ({ ...f, pdf: `${f.order_url}#page=${f.page}`, cite: `/cite/${f.fact_id}` })),
    };
  });
}
