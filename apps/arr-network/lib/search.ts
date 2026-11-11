// Hybrid search over chunks (full-text rank + vector distance, fused by reciprocal rank) and a
// full-text search over fact labels.  Filters: state, utility, year, paragraph kind.
import type { Sql } from "./db.ts";
import { embedQuery, EMBED_MODEL_NAME } from "./embed.ts";

export interface Filters { state?: string; utility?: string; year?: string; kind?: string }
export interface ChunkHit {
  chunk_id: number; order_id: number; page: number; text: string; kind: string | null; title: string; url: string;
  commission: string; arr_year: string | null; fts_rank: number | null; vec_rank: number | null; score: number;
}
export interface SearchOut {
  chunks: ChunkHit[];
  facts: Record<string, unknown>[];
  mode: "hybrid" | "full_text";
  why: string | null; // why vector search was not used
  chunksTotal: number;
  embedded: number;
}

const RRF_K = 60;
const DEPTH = 50;

export async function search(sql: Sql, q: string, f: Filters, embed = embedQuery): Promise<SearchOut> {
  const state = f.state || null, utility = f.utility || null, year = f.year || null, kind = f.kind || null;
  const [{ total, embedded }] = await sql`
    SELECT count(*)::int AS total, count(*) FILTER (WHERE embedding IS NOT NULL AND embedding_model = ${EMBED_MODEL_NAME})::int AS embedded FROM chunks`;

  let vector: number[] | null = null;
  let why: string | null = null;
  if (!total) why = "no paragraphs have been indexed yet";
  else if (!embedded) why = `no chunk has a ${EMBED_MODEL_NAME} embedding yet`;
  else {
    const e = await embed(q);
    if (e.ok) vector = e.vector;
    else why = e.error;
  }

  const base = sql`
    SELECT c.chunk_id, c.order_id, c.page, c.text, c.tsv, c.embedding, c.embedding_model, p.kind,
           o.title, o.url, o.commission, o.arr_year
    FROM chunks c
    JOIN orders o ON o.order_id = c.order_id
    LEFT JOIN paragraphs p ON p.paragraph_id = c.paragraph_id
    WHERE (${state}::text IS NULL
           OR EXISTS (SELECT 1 FROM order_utilities ou JOIN utilities u ON u.code = ou.utility WHERE ou.order_id = o.order_id AND u.state = ${state})
           OR (NOT EXISTS (SELECT 1 FROM order_utilities ou WHERE ou.order_id = o.order_id)
               AND o.commission IN (SELECT commission FROM commission_states WHERE state = ${state})))
      AND (${utility}::text IS NULL OR p.utility = ${utility}
           OR (p.utility IS NULL AND EXISTS (SELECT 1 FROM order_utilities ou WHERE ou.order_id = o.order_id AND ou.utility = ${utility})))
      AND (${year}::text IS NULL OR o.arr_year = ${year} OR ${year} = ANY (o.years_decided))
      AND (${kind}::text IS NULL OR COALESCE(p.kind, 'text') = ${kind})`;

  const vec = vector ? `[${vector.join(",")}]` : null;
  const chunks = total ? ((await sql`
    WITH base AS (${base}),
    fts AS (
      SELECT chunk_id, row_number() OVER (ORDER BY ts_rank_cd(tsv, query) DESC, chunk_id) AS r
      FROM base, websearch_to_tsquery('english', ${q}) AS query
      WHERE tsv @@ query
      ORDER BY r LIMIT ${DEPTH}
    ),
    vec AS (
      SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> ${vec}::text::vector, chunk_id) AS r
      FROM base
      WHERE ${vec}::text IS NOT NULL AND embedding IS NOT NULL AND embedding_model = ${EMBED_MODEL_NAME}
      ORDER BY r LIMIT ${DEPTH}
    ),
    fused AS (
      SELECT chunk_id, max(fts_r) AS fts_rank, max(vec_r) AS vec_rank,
             sum(1.0 / (${RRF_K} + r)) AS score
      FROM (SELECT chunk_id, r, r AS fts_r, NULL::bigint AS vec_r FROM fts
            UNION ALL SELECT chunk_id, r, NULL, r FROM vec) x
      GROUP BY chunk_id
    )
    SELECT b.chunk_id, b.order_id, b.page, b.text, b.kind, b.title, b.url, b.commission, b.arr_year,
           f.fts_rank, f.vec_rank, f.score::float8 AS score
    FROM fused f JOIN base b USING (chunk_id)
    ORDER BY f.score DESC, b.chunk_id
    LIMIT 30`) as unknown as ChunkHit[]) : [];

  const facts = kind && kind !== "" ? [] : [...(await sql`
    SELECT fact_id, utility, utility_name, state, fiscal_year, voice, stage, head, head_name, label, value_crore, value, unit,
           page, quote, consensus, reviewed_by, order_id, order_title, order_url, is_headline,
           ts_rank_cd(to_tsvector('english', label || ' ' || head_name), query) AS rank
    FROM v_facts, websearch_to_tsquery('english', ${q}) AS query
    WHERE to_tsvector('english', label || ' ' || head_name || ' ' || utility || ' ' || COALESCE(utility_name, '') || ' ' || COALESCE(state_name, '')) @@ query
      AND (${state}::text IS NULL OR state = ${state})
      AND (${utility}::text IS NULL OR utility = ${utility})
      AND (${year}::text IS NULL OR fiscal_year = ${year})
    ORDER BY rank DESC, is_headline DESC, order_arr_year DESC NULLS LAST, fact_id DESC
    LIMIT 40`)];

  return { chunks, facts, mode: vector ? "hybrid" : "full_text", why, chunksTotal: total, embedded };
}
