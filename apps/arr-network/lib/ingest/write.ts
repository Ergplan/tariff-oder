// Writes one validated batch in one transaction.  Each row runs in its own savepoint, so a row
// the database refuses is rejected with a reason and the rest of the batch is still written.
// No statement here writes reviewed_by, reviewed_at or review_note.
import type { Sql } from "../db.ts";
import { validateRow, numberOnPage, type Refs, type Row } from "./validate.ts";

type Tx = Parameters<Parameters<Sql["begin"]>[0]>[0];
export interface Rejected { index: number; reason: string }
class Reject extends Error {}
const reject = (reason: string): never => { throw new Reject(reason); };

const j = (v: unknown) => (v === undefined ? null : JSON.stringify(v));
const n = <T,>(v: T | undefined): T | null => (v === undefined ? null : v);

async function loadRefs(tx: Tx): Promise<Refs> {
  const [heads, defs, utils, states, comms] = await Promise.all([
    tx`SELECT code FROM heads`, tx`SELECT code FROM parameter_defs`, tx`SELECT code FROM utilities`,
    tx`SELECT code FROM states`, tx`SELECT code FROM commissions`,
  ]);
  const set = (rows: readonly Row[]) => new Set(rows.map((r) => r.code as string));
  return { heads: set(heads), parameterDefs: set(defs), utilities: set(utils), states: set(states), commissions: set(comms) };
}

/** A per-batch cache of order ids and parse ids. */
class Lookup {
  orders = new Map<string, number | null>();
  parses = new Map<string, number | null>();
  constructor(private tx: Tx) {}
  async order(url: string): Promise<number> {
    if (!this.orders.has(url)) {
      const r = await this.tx`SELECT order_id FROM orders WHERE url = ${url}`;
      this.orders.set(url, r.length ? (r[0].order_id as number) : null);
    }
    return this.orders.get(url) ?? reject(`unknown order_url ${url}`);
  }
  async orderOpt(url: unknown): Promise<number | null> {
    return url === undefined || url === null ? null : this.order(url as string);
  }
  async parse(url: string, reader: string, version: string): Promise<{ orderId: number; parseId: number }> {
    const orderId = await this.order(url);
    const key = `${orderId}\u0000${reader}\u0000${version}`;
    if (!this.parses.has(key)) {
      const r = await this.tx`SELECT parse_id FROM parses WHERE order_id = ${orderId} AND reader = ${reader} AND reader_version = ${version}`;
      this.parses.set(key, r.length ? (r[0].parse_id as number) : null);
    }
    const parseId = this.parses.get(key) ?? reject(`no parse for ${reader} ${version} of this order: post the parse first`);
    return { orderId, parseId };
  }
}

async function pageCheck(tx: Tx, orderId: number, page: number, printed: string) {
  const r = await tx`SELECT text FROM pages WHERE order_id = ${orderId} AND page = ${page}`;
  if (r.length && !numberOnPage(printed, r[0].text as string)) reject("number not on page");
}

const writers: Record<string, (tx: Tx, x: Row, L: Lookup) => Promise<void>> = {
  async states(tx, x) {
    await tx`INSERT INTO states (code, name, kind) VALUES (${x.code as string}, ${x.name as string}, ${x.kind as string})
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind`;
  },
  async commissions(tx, x) {
    await tx`INSERT INTO commissions (code, name, website, website_reachable, checked_on)
      VALUES (${x.code as string}, ${x.name as string}, ${n(x.website as string)}, ${n(x.website_reachable as boolean)}, ${n(x.checked_on as string)})
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, website = EXCLUDED.website,
        website_reachable = EXCLUDED.website_reachable, checked_on = EXCLUDED.checked_on`;
    await tx`DELETE FROM commission_states WHERE commission = ${x.code as string}`;
    await tx`INSERT INTO commission_states (commission, state)
      SELECT ${x.code as string}, s FROM jsonb_array_elements_text(${j(x.states)}::text::jsonb) AS s ON CONFLICT DO NOTHING`;
  },
  async utilities(tx, x) {
    await tx`INSERT INTO utilities (code, name, kind, commission, state, ownership, aliases)
      VALUES (${x.code as string}, ${x.name as string}, ${x.kind as string}, ${x.commission as string}, ${x.state as string},
              ${x.ownership as string}, ${j(x.aliases ?? [])}::text::jsonb)
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind, commission = EXCLUDED.commission,
        state = EXCLUDED.state, ownership = EXCLUDED.ownership, aliases = EXCLUDED.aliases`;
  },
  async heads(tx, x) {
    await tx`INSERT INTO heads (code, name, sort) VALUES (${x.code as string}, ${x.name as string}, ${(x.sort as number) ?? 100})
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, sort = EXCLUDED.sort`;
  },
  async parameter_defs(tx, x) {
    await tx`INSERT INTO parameter_defs (code, name, unit, grp, sort)
      VALUES (${x.code as string}, ${x.name as string}, ${x.unit as string}, ${x.grp as string}, ${(x.sort as number) ?? 100})
      ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, unit = EXCLUDED.unit, grp = EXCLUDED.grp, sort = EXCLUDED.sort`;
  },
  async orders(tx, x, L) {
    const r = await tx`INSERT INTO orders (commission, title, url, sha256, bytes, pages, pages_without_text, arr_year, years_decided,
        kind, utility_kind, order_date, found_by, fetched_on, read_status)
      VALUES (${x.commission as string}, ${x.title as string}, ${x.url as string}, ${n(x.sha256 as string)}, ${n(x.bytes as number)},
        ${n(x.pages as number)}, ${n(x.pages_without_text as number)}, ${n(x.arr_year as string)},
        ARRAY(SELECT jsonb_array_elements_text(${j(x.years_decided ?? [])}::text::jsonb)),
        ${n(x.kind as string)}, ${(x.utility_kind as string) ?? "discom"}, ${n(x.order_date as string)}, ${n(x.found_by as string)},
        ${n(x.fetched_on as string)}, ${(x.read_status as string) ?? "listed"})
      ON CONFLICT (url) DO UPDATE SET commission = EXCLUDED.commission, title = EXCLUDED.title,
        sha256 = COALESCE(EXCLUDED.sha256, orders.sha256), bytes = COALESCE(EXCLUDED.bytes, orders.bytes),
        pages = COALESCE(EXCLUDED.pages, orders.pages), pages_without_text = COALESCE(EXCLUDED.pages_without_text, orders.pages_without_text),
        arr_year = COALESCE(EXCLUDED.arr_year, orders.arr_year), years_decided = EXCLUDED.years_decided,
        kind = COALESCE(EXCLUDED.kind, orders.kind), utility_kind = EXCLUDED.utility_kind,
        order_date = COALESCE(EXCLUDED.order_date, orders.order_date), found_by = COALESCE(EXCLUDED.found_by, orders.found_by),
        fetched_on = COALESCE(EXCLUDED.fetched_on, orders.fetched_on), read_status = EXCLUDED.read_status
      RETURNING order_id`;
    const id = r[0].order_id as number;
    L.orders.set(x.url as string, id);
    await tx`DELETE FROM order_utilities WHERE order_id = ${id}`;
    await tx`INSERT INTO order_utilities (order_id, utility)
      SELECT ${id}, u FROM jsonb_array_elements_text(${j(x.utilities)}::text::jsonb) AS u ON CONFLICT DO NOTHING`;
  },
  async pages(tx, x, L) {
    const id = await L.order(x.order_url as string);
    await tx`INSERT INTO pages (order_id, page, text, has_text_layer) VALUES (${id}, ${x.page as number}, ${x.text as string}, ${x.has_text_layer as boolean})
      ON CONFLICT (order_id, page) DO UPDATE SET text = EXCLUDED.text, has_text_layer = EXCLUDED.has_text_layer`;
  },
  async parses(tx, x, L) {
    const id = await L.order(x.order_url as string);
    const r = await tx`INSERT INTO parses (order_id, reader, reader_version, provider, model, is_real, status, pages_parsed, cost_usd, note)
      VALUES (${id}, ${x.reader as string}, ${x.reader_version as string}, ${n(x.provider as string)}, ${n(x.model as string)},
        ${x.is_real as boolean}, ${x.status as string}, ${n(x.pages_parsed as number)}, ${(x.cost_usd as number) ?? 0}, ${n(x.note as string)})
      ON CONFLICT (order_id, reader, reader_version) DO UPDATE SET provider = EXCLUDED.provider, model = EXCLUDED.model,
        is_real = EXCLUDED.is_real, status = EXCLUDED.status, pages_parsed = EXCLUDED.pages_parsed, cost_usd = EXCLUDED.cost_usd,
        note = EXCLUDED.note
      RETURNING parse_id`;
    L.parses.set(`${id}\u0000${x.reader}\u0000${x.reader_version}`, r[0].parse_id as number);
  },
  async parsed_tables(tx, x, L) {
    const { orderId, parseId } = await L.parse(x.order_url as string, x.reader as string, x.reader_version as string);
    const title = n(x.title as string);
    const vals = [orderId, x.page as number, j(x.pages ?? [x.page]), title, n(x.unit as string), n(x.unit_from as string),
      j(x.columns), j(x.cells), n(x.markdown as string)] as const;
    const upd = await tx`UPDATE parsed_tables SET pages = ARRAY(SELECT jsonb_array_elements_text(${vals[2]}::text::jsonb)::int),
        unit = ${vals[4]}, unit_from = ${vals[5]}, columns = ${vals[6]}::text::jsonb, cells = ${vals[7]}::text::jsonb, markdown = ${vals[8]}
      WHERE parse_id = ${parseId} AND page = ${vals[1]} AND title IS NOT DISTINCT FROM ${title} RETURNING table_id`;
    if (upd.length) return;
    await tx`INSERT INTO parsed_tables (parse_id, order_id, page, pages, title, unit, unit_from, columns, cells, markdown)
      VALUES (${parseId}, ${orderId}, ${vals[1]}, ARRAY(SELECT jsonb_array_elements_text(${vals[2]}::text::jsonb)::int), ${title},
        ${vals[4]}, ${vals[5]}, ${vals[6]}::text::jsonb, ${vals[7]}::text::jsonb, ${vals[8]})`;
  },
  async arr_values(tx, x, L) {
    const { orderId, parseId } = await L.parse(x.order_url as string, x.reader as string, x.reader_version as string);
    let tableId: number | null = null;
    if (x.table_page !== undefined) {
      const t = await tx`SELECT table_id FROM parsed_tables WHERE parse_id = ${parseId} AND page = ${x.table_page as number}
        AND title IS NOT DISTINCT FROM ${n(x.table_title as string)} LIMIT 1`;
      tableId = t.length ? (t[0].table_id as number) : reject("table_page/table_title: no such table in this parse");
    }
    await pageCheck(tx, orderId, x.page as number, x.value_printed as string);
    await tx`INSERT INTO arr_values (parse_id, table_id, order_id, reader, utility, fiscal_year, voice, stage, head, label, group_label,
        value_printed, value, unit, value_crore, page, quote, column_header, year_from, voice_from, is_primary)
      VALUES (${parseId}, ${tableId}, ${orderId}, ${x.reader as string}, ${n(x.utility as string)}, ${n(x.fiscal_year as string)},
        ${n(x.voice as string)}, ${n(x.stage as string)}, ${x.head as string}, ${x.label as string}, ${n(x.group_label as string)},
        ${x.value_printed as string}, ${x.value as number}, ${n(x.unit as string)}, ${n(x.value_crore as number)}, ${x.page as number},
        ${x.quote as string}, ${n(x.column_header as string)}, ${n(x.year_from as string)}, ${n(x.voice_from as string)},
        ${(x.is_primary as boolean) ?? false})`;
  },
  async parameters(tx, x, L) {
    const { orderId, parseId } = await L.parse(x.order_url as string, x.reader as string, x.reader_version as string);
    await pageCheck(tx, orderId, x.page as number, x.value_printed as string);
    await tx`INSERT INTO parameters (parse_id, order_id, reader, utility, fiscal_year, voice, code, label, value_printed, value, unit, page, quote)
      VALUES (${parseId}, ${orderId}, ${x.reader as string}, ${n(x.utility as string)}, ${n(x.fiscal_year as string)}, ${n(x.voice as string)},
        ${x.code as string}, ${x.label as string}, ${x.value_printed as string}, ${x.value as number}, ${x.unit as string},
        ${x.page as number}, ${x.quote as string})`;
  },
  async facts(tx, x, L) {
    const orderId = await L.order(x.order_url as string);
    const readings = x.readings as Row[];
    // every reading must be a stored reading of this order: the fact links to its evidence
    const links: { valueId: number; agrees: boolean }[] = [];
    for (const g of readings) {
      const { parseId } = await L.parse(x.order_url as string, g.reader as string, g.reader_version as string);
      const v = await tx`SELECT value_id FROM arr_values
        WHERE parse_id = ${parseId} AND page = ${g.page as number} AND value_printed = ${g.value_printed as string}
        ORDER BY (label = ${x.label as string}) DESC, (utility IS NOT DISTINCT FROM ${x.utility as string}) DESC,
                 (fiscal_year IS NOT DISTINCT FROM ${x.fiscal_year as string}) DESC, (voice IS NOT DISTINCT FROM ${x.voice as string}) DESC,
                 (head = ${x.head as string}) DESC, value_id
        LIMIT 1`;
      if (!v.length) reject(`readings: no ${g.reader} reading of "${g.value_printed}" on page ${g.page} of this order`);
      links.push({ valueId: v[0].value_id as number, agrees: g.agrees as boolean });
    }
    // the fact's own printed value is checked through its agreeing readings' value_printed
    const printed = readings.find((g) => g.agrees && g.page === x.page)?.value_printed as string | undefined;
    if (printed) await pageCheck(tx, orderId, x.page as number, printed);
    const r = await tx`INSERT INTO facts (order_id, utility, fiscal_year, voice, stage, head, label, value_crore, value, unit, page, quote,
        consensus, readers, is_headline, headline_why, set_aside)
      VALUES (${orderId}, ${x.utility as string}, ${x.fiscal_year as string}, ${x.voice as string}, ${n(x.stage as string)},
        ${x.head as string}, ${x.label as string}, ${n(x.value_crore as number)}, ${x.value as number}, ${n(x.unit as string)},
        ${x.page as number}, ${x.quote as string}, ${x.consensus as string},
        ARRAY(SELECT jsonb_array_elements_text(${j(x.readers)}::text::jsonb)), ${(x.is_headline as boolean) ?? false},
        ${n(x.headline_why as string)}, ${n(x.set_aside as string)})
      ON CONFLICT (order_id, utility, fiscal_year, voice, head, label, page) DO UPDATE SET
        stage = EXCLUDED.stage, value_crore = EXCLUDED.value_crore, value = EXCLUDED.value, unit = EXCLUDED.unit,
        quote = EXCLUDED.quote, consensus = EXCLUDED.consensus, readers = EXCLUDED.readers, is_headline = EXCLUDED.is_headline,
        headline_why = EXCLUDED.headline_why, set_aside = EXCLUDED.set_aside
      RETURNING fact_id`;
    const factId = r[0].fact_id as number;
    await tx`DELETE FROM fact_readings WHERE fact_id = ${factId}`;
    for (const l of links) {
      await tx`INSERT INTO fact_readings (fact_id, value_id, agrees) VALUES (${factId}, ${l.valueId}, ${l.agrees})
        ON CONFLICT (fact_id, value_id) DO UPDATE SET agrees = EXCLUDED.agrees`;
    }
  },
  async paragraphs(tx, x, L) {
    const id = await L.order(x.order_url as string);
    await tx`INSERT INTO paragraphs (order_id, page, seq, kind, kind_by, utility, topic, text, summary)
      VALUES (${id}, ${x.page as number}, ${x.seq as number}, ${(x.kind as string) ?? "text"}, ${n(x.kind_by as string)},
        ${n(x.utility as string)}, ${n(x.topic as string)}, ${x.text as string}, ${n(x.summary as string)})
      ON CONFLICT (order_id, page, seq) DO UPDATE SET kind = EXCLUDED.kind, kind_by = EXCLUDED.kind_by, utility = EXCLUDED.utility,
        topic = EXCLUDED.topic, text = EXCLUDED.text, summary = EXCLUDED.summary`;
  },
  async chunks(tx, x, L) {
    const id = await L.order(x.order_url as string);
    let paragraphId: number | null = null;
    if (x.paragraph_seq !== undefined) {
      const p = await tx`SELECT paragraph_id FROM paragraphs WHERE order_id = ${id} AND page = ${x.page as number} AND seq = ${x.paragraph_seq as number}`;
      paragraphId = p.length ? (p[0].paragraph_id as number) : reject("paragraph_seq: no such paragraph on this page; post the paragraph first");
    }
    const emb = x.embedding ? `[${(x.embedding as number[]).join(",")}]` : null;
    const model = n(x.embedding_model as string);
    const upd = await tx`UPDATE chunks SET text = ${x.text as string}, embedding = ${emb}::text::vector, embedding_model = ${model}
      WHERE order_id = ${id} AND page = ${x.page as number} AND paragraph_id IS NOT DISTINCT FROM ${paragraphId} RETURNING chunk_id`;
    if (upd.length) return;
    await tx`INSERT INTO chunks (order_id, paragraph_id, page, text, embedding, embedding_model)
      VALUES (${id}, ${paragraphId}, ${x.page as number}, ${x.text as string}, ${emb}::text::vector, ${model})`;
  },
  async work_items(tx, x) {
    await tx`INSERT INTO work_items (kind, target, priority, created_by)
      VALUES (${x.kind as string}, ${x.target as string}, ${(x.priority as number) ?? 100}, ${(x.created_by as string) ?? "director"})
      ON CONFLICT (kind, target) DO NOTHING`;
  },
  async agent_runs(tx, x, L) {
    const orderId = await L.orderOpt(x.order_url);
    await tx`INSERT INTO agent_runs (agent, version, order_id, provider, model, is_real, started_at, finished_at, outcome,
        rows_written, rows_rejected, input_tokens, output_tokens, cost_usd, note)
      VALUES (${x.agent as string}, ${x.version as string}, ${orderId}, ${n(x.provider as string)}, ${n(x.model as string)},
        ${x.is_real as boolean}, ${x.started_at as string}, ${n(x.finished_at as string)}, ${x.outcome as string},
        ${(x.rows_written as number) ?? 0}, ${(x.rows_rejected as number) ?? 0}, ${(x.input_tokens as number) ?? 0},
        ${(x.output_tokens as number) ?? 0}, ${(x.cost_usd as number) ?? 0}, ${n(x.note as string)})`;
  },
  async metrics(tx, x) {
    await tx`INSERT INTO metrics (measured_on, name, scope, numerator, denominator, value, detail)
      VALUES (${x.measured_on as string}, ${x.name as string}, ${(x.scope as string) ?? "all"}, ${n(x.numerator as number)},
        ${n(x.denominator as number)}, ${n(x.value as number)}, ${j(x.detail)}::text::jsonb)
      ON CONFLICT (measured_on, name, scope) DO UPDATE SET numerator = EXCLUDED.numerator, denominator = EXCLUDED.denominator,
        value = EXCLUDED.value, detail = EXCLUDED.detail`;
  },
  async findings(tx, x, L) {
    const orderId = await L.orderOpt(x.order_url);
    await tx`INSERT INTO findings (raised_by, severity, title, detail, order_id)
      VALUES (${x.raised_by as string}, ${x.severity as string}, ${x.title as string}, ${x.detail as string}, ${orderId})`;
  },
  async briefs(tx, x) {
    await tx`INSERT INTO briefs (written_by, is_real, body, decisions)
      VALUES (${x.written_by as string}, ${x.is_real as boolean}, ${x.body as string}, ${j(x.decisions ?? [])}::text::jsonb)`;
  },
  async gold_figures(tx, x) {
    await tx`INSERT INTO gold_figures (order_sha256, key, source, page, value, voice, utility, what)
      VALUES (${x.order_sha256 as string}, ${x.key as string}, ${x.source as string}, ${x.page as number}, ${x.value as number},
        ${n(x.voice as string)}, ${n(x.utility as string)}, ${n(x.what as string)})
      ON CONFLICT (order_sha256, source, key) DO UPDATE SET page = EXCLUDED.page, value = EXCLUDED.value, voice = EXCLUDED.voice,
        utility = EXCLUDED.utility, what = EXCLUDED.what`;
  },
};

/** Before the rows: the replace semantics of INGEST.md "Keys". */
async function replaceFirst(tx: Tx, kind: string, first: Row | undefined, rows: Row[], L: Lookup) {
  if (!first || !rows.length) return;
  if (kind === "facts" && first.replace_order === true) {
    const urls = [...new Set(rows.map((r) => r.order_url as string))];
    for (const u of urls) {
      const id = await L.order(u).catch(() => null);
      if (id !== null) await tx`DELETE FROM facts WHERE order_id = ${id} AND reviewed_by IS NULL`;
    }
  }
  if (["parsed_tables", "arr_values", "parameters"].includes(kind) && first.replace === true) {
    const keys = new Map<string, Row>();
    for (const r of rows) keys.set(`${r.order_url}\u0000${r.reader}\u0000${r.reader_version}`, r);
    for (const r of keys.values()) {
      const p = await L.parse(r.order_url as string, r.reader as string, r.reader_version as string).catch(() => null);
      if (!p) continue;
      // parsed_tables is a parse's first batch: replacing it clears the parse's values too.
      if (kind === "parsed_tables" || kind === "arr_values") await tx`DELETE FROM arr_values WHERE parse_id = ${p.parseId}`;
      if (kind === "parsed_tables" || kind === "parameters") await tx`DELETE FROM parameters WHERE parse_id = ${p.parseId}`;
      if (kind === "parsed_tables") await tx`DELETE FROM parsed_tables WHERE parse_id = ${p.parseId}`;
    }
  }
}

export async function writeBatch(sql: Sql, kind: string, rows: unknown[]): Promise<{ written: number; rejected: Rejected[] }> {
  const rejected: Rejected[] = [];
  let written = 0;
  await sql.begin(async (tx) => {
    const refs = await loadRefs(tx);
    const L = new Lookup(tx);
    const valid: { index: number; row: Row }[] = [];
    for (let i = 0; i < rows.length; i++) {
      const c = validateRow(kind, rows[i], refs);
      if (c.ok) valid.push({ index: i, row: c.row });
      else rejected.push({ index: i, reason: c.reason });
    }
    const first = rows[0] && typeof rows[0] === "object" ? (rows[0] as Row) : undefined;
    await replaceFirst(tx, kind, first, valid.map((v) => v.row), L);
    for (const { index, row } of valid) {
      try {
        await tx.savepoint(async (sp) => { await writers[kind](sp as unknown as Tx, row, L); });
        written++;
      } catch (e) {
        if (e instanceof Reject) rejected.push({ index, reason: e.message });
        else {
          const err = e as { code?: string; message?: string; detail?: string };
          if (!err.code || /^(08|57|53)/.test(err.code)) throw e; // connection or resource trouble: fail the batch
          rejected.push({ index, reason: `database refused the row: ${err.message}${err.detail ? ` (${err.detail})` : ""}` });
        }
      }
    }
  });
  rejected.sort((a, b) => a.index - b.index);
  return { written, rejected };
}
