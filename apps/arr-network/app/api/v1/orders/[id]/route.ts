import { api } from "@/lib/api.ts";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!/^\d{1,12}$/.test(id)) return Response.json({ error: "not found" }, { status: 404 });
  const oid = Number(id);
  return api(async (sql) => {
    const [order] = await sql`SELECT order_id, commission, title, url, sha256, pages, pages_without_text, arr_year, years_decided, kind,
                                     utility_kind, order_date, found_by, fetched_on, read_status FROM orders WHERE order_id = ${oid}`;
    if (!order) return null;
    const [utilities, parses, tables, facts, paragraphs] = await Promise.all([
      sql`SELECT utility FROM order_utilities WHERE order_id = ${oid} ORDER BY utility`,
      sql`SELECT reader, reader_version, provider, model, is_real, status, pages_parsed, cost_usd, note, created_at FROM parses WHERE order_id = ${oid}`,
      sql`SELECT t.page, t.pages, t.title, t.unit, t.unit_from, t.columns, p.reader, p.reader_version
          FROM parsed_tables t JOIN parses p ON p.parse_id = t.parse_id WHERE t.order_id = ${oid} ORDER BY t.page, t.table_id`,
      sql`SELECT fact_id, utility, fiscal_year, voice, stage, head, label, value_crore, value, unit, page, quote, consensus, readers,
                 is_headline, headline_why, set_aside, reviewed_by, reviewed_at
          FROM facts WHERE order_id = ${oid} ORDER BY page, utility, fiscal_year, voice, fact_id`,
      sql`SELECT page, seq, kind, kind_by, utility, topic, text, summary FROM paragraphs WHERE order_id = ${oid} AND kind <> 'text' ORDER BY page, seq`,
    ]);
    return { order: { ...order, utilities: utilities.map((u) => u.utility) }, parses, tables, facts, key_paragraphs: paragraphs };
  });
}
