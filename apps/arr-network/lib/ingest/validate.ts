// Row validators for the ingest API (docs/arr-network/INGEST.md).  Pure functions: no database,
// so they are unit-tested directly.  The writer (write.ts) supplies the reference sets.

export const VOICES = ["claimed", "approved", "approved_earlier", "actual"] as const;
export const STAGES = ["ARR", "APR", "True-up", "MYT projection"] as const;
export const CONSENSUS = ["single", "agreed_2", "agreed_3", "conflict"] as const;
export const READERS = ["textlayer", "docling", "llamaparse", "llm"] as const;
export const STATE_KINDS = ["state", "union_territory"] as const;
export const UTILITY_KINDS = ["discom", "transco", "genco", "sldc"] as const;
export const ORDER_UTILITY_KINDS = ["discom", "transco", "genco", "sldc", "mixed"] as const;
export const OWNERSHIP = ["state", "private", "municipal", "central"] as const;
export const READ_STATUS = ["listed", "downloaded", "read", "no_tables_found", "no_text_layer", "unreadable"] as const;
export const PARSE_STATUS = ["ok", "partial", "failed", "skipped"] as const;
export const OUTCOMES = PARSE_STATUS;
export const PARAGRAPH_KINDS = ["text", "ruling", "directive", "reasoning", "submission", "heading"] as const;
export const SEVERITY = ["info", "warn", "block"] as const;
export const SECTIONS = ["power_purchase", "re_portfolio", "tariff_schedule", "wheeling", "tod"] as const;
export const SECTION_KINDS = ["table", "text"] as const;
export const WORK_DONE_STATES = ["done", "failed", "parked"] as const;

/** Fields only a person may write.  Their presence anywhere rejects the row. */
export const REVIEW_FIELDS = ["reviewed_by", "reviewed_at", "review_note"];

type T =
  | "text" | "int" | "num" | "bool" | "date" | "timestamp" | "json"
  | "text[]" | "int[]" | "num[]" | "object[]";

interface F { t: T; req?: boolean; enum?: readonly string[]; nonEmpty?: boolean; min?: number; len?: number; nullable?: boolean }

const r = (t: T, extra: Partial<F> = {}): F => ({ t, req: true, nonEmpty: t === "text", ...extra });
const o = (t: T, extra: Partial<F> = {}): F => ({ t, ...extra });

const evidence = {
  page: r("int", { min: 1 }),
  quote: r("text"),
  value: r("num"),
  value_printed: r("text"),
};
// The row label as printed: required, but a table row can print none, so it may be empty.
const printedLabel: F = { t: "text", req: true };
const parseKey = { order_url: r("text"), reader: r("text", { enum: READERS }), reader_version: r("text") };

export const SPECS: Record<string, Record<string, F>> = {
  states: { code: r("text"), name: r("text"), kind: r("text", { enum: STATE_KINDS }) },
  commissions: {
    code: r("text"), name: r("text"), website: o("text"), website_reachable: o("bool"), checked_on: o("date"),
    states: r("text[]"),
  },
  utilities: {
    code: r("text"), name: r("text"), kind: r("text", { enum: UTILITY_KINDS }), commission: r("text"),
    state: r("text"), ownership: r("text", { enum: OWNERSHIP }), aliases: o("text[]"),
  },
  heads: { code: r("text"), name: r("text"), sort: o("int") },
  parameter_defs: { code: r("text"), name: r("text"), unit: r("text"), grp: r("text"), sort: o("int") },
  orders: {
    commission: r("text"), title: r("text"), url: r("text"), sha256: o("text"), bytes: o("int", { min: 0 }),
    pages: o("int", { min: 0 }), pages_without_text: o("int", { min: 0 }), arr_year: o("text"), years_decided: o("text[]"),
    kind: o("text"), utility_kind: o("text", { enum: ORDER_UTILITY_KINDS }), order_date: o("date"), found_by: o("text"),
    fetched_on: o("date"), read_status: o("text", { enum: READ_STATUS }), utilities: r("text[]"),
  },
  pages: { order_url: r("text"), page: r("int", { min: 1 }), text: { t: "text", req: true }, has_text_layer: r("bool") },
  parses: {
    ...parseKey, provider: o("text"), model: o("text"), is_real: r("bool"), status: r("text", { enum: PARSE_STATUS }),
    pages_parsed: o("int", { min: 0 }), cost_usd: o("num", { min: 0 }), note: o("text"),
  },
  parsed_tables: {
    ...parseKey, page: r("int", { min: 1 }), pages: o("int[]"), title: o("text"), unit: o("text"), unit_from: o("text"),
    columns: r("object[]"), cells: o("json"), markdown: o("text"), replace: o("bool"),
  },
  arr_values: {
    ...parseKey, table_page: o("int", { min: 1 }), table_title: o("text"), utility: o("text"), fiscal_year: o("text"),
    voice: o("text", { enum: VOICES }), stage: o("text", { enum: STAGES }), head: r("text"), label: printedLabel,
    group_label: o("text"), ...evidence, unit: o("text"), value_crore: o("num"), column_header: o("text"),
    year_from: o("text"), voice_from: o("text"), is_primary: o("bool"), replace: o("bool"),
  },
  parameters: {
    ...parseKey, utility: o("text"), fiscal_year: o("text"), voice: o("text", { enum: VOICES }), code: r("text"),
    label: r("text"), ...evidence, unit: r("text"), replace: o("bool"),
  },
  facts: {
    order_url: r("text"), utility: r("text"), fiscal_year: r("text"), voice: r("text", { enum: VOICES }),
    stage: o("text", { enum: STAGES }), head: r("text"), label: printedLabel, value_crore: o("num"), value: r("num"),
    unit: o("text"), page: r("int", { min: 1 }), quote: r("text"), consensus: r("text", { enum: CONSENSUS }),
    readers: r("text[]", { enum: READERS }), is_headline: o("bool"), headline_why: o("text"), set_aside: o("text"),
    readings: r("object[]"), replace_order: o("bool"),
  },
  paragraphs: {
    order_url: r("text"), page: r("int", { min: 1 }), seq: r("int", { min: 0 }), kind: o("text", { enum: PARAGRAPH_KINDS }),
    kind_by: o("text"), utility: o("text"), topic: o("text"), text: r("text"), summary: o("text"),
  },
  chunks: {
    order_url: r("text"), page: r("int", { min: 1 }), paragraph_seq: o("int", { min: 0 }), text: r("text"),
    embedding: o("num[]", { len: 384 }), embedding_model: o("text"),
  },
  work_items: { kind: r("text"), target: r("text"), priority: o("int"), created_by: o("text") },
  agent_runs: {
    agent: r("text"), version: r("text"), order_url: o("text"), provider: o("text"), model: o("text"), is_real: r("bool"),
    started_at: r("timestamp"), finished_at: o("timestamp"), outcome: r("text", { enum: OUTCOMES }),
    rows_written: o("int", { min: 0 }), rows_rejected: o("int", { min: 0 }), input_tokens: o("int", { min: 0 }),
    output_tokens: o("int", { min: 0 }), cost_usd: o("num", { min: 0 }), note: o("text"),
  },
  metrics: {
    measured_on: r("date"), name: r("text"), scope: o("text"), numerator: o("num"), denominator: o("num"),
    value: o("num"), detail: o("json"),
  },
  findings: { raised_by: r("text"), severity: r("text", { enum: SEVERITY }), title: r("text"), detail: r("text"), order_url: o("text") },
  briefs: { written_by: r("text"), is_real: r("bool"), body: r("text"), decisions: o("object[]") },
  section_tables: {
    order_url: r("text"), section: r("text", { enum: SECTIONS }), seq: r("int", { min: 1 }),
    kind: o("text", { enum: SECTION_KINDS }), label: o("text"), category: o("text"), title: r("text"),
    fiscal_year: o("text"), page: r("int", { min: 1 }), pages: r("int[]"), columns: r("json"), rows: r("object[]"),
    reader_version: r("text"), is_real: r("bool"), replace_order: o("bool"),
  },
  gold_figures: {
    order_sha256: r("text"), key: r("text"), source: r("text"), page: r("int", { min: 1 }), value: r("num"),
    voice: o("text", { enum: VOICES }), utility: o("text"), what: o("text"),
  },
};

const READING: Record<string, F> = {
  reader: r("text", { enum: READERS }), reader_version: r("text"), page: r("int", { min: 1 }),
  value_printed: r("text"), agrees: r("bool"),
};

export const KINDS = Object.keys(SPECS);

export type Row = Record<string, unknown>;
export type Checked = { ok: true; row: Row } | { ok: false; reason: string };

const isObj = (v: unknown): v is Row => typeof v === "object" && v !== null && !Array.isArray(v);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

function checkValue(name: string, f: F, v: unknown): string | null {
  const bad = (what: string) => `${name}: ${what}`;
  switch (f.t) {
    case "text":
      if (typeof v !== "string") return bad("must be a string");
      if (f.nonEmpty && v.trim() === "") return bad("must not be empty");
      if (f.enum && !f.enum.includes(v)) return bad(`must be one of ${f.enum.join(", ")}`);
      return null;
    case "int":
      if (typeof v !== "number" || !Number.isInteger(v)) return bad("must be an integer");
      if (f.min !== undefined && v < f.min) return bad(`must be >= ${f.min}`);
      return null;
    case "num":
      if (typeof v !== "number" || !Number.isFinite(v)) return bad("must be a finite number");
      if (f.min !== undefined && v < f.min) return bad(`must be >= ${f.min}`);
      return null;
    case "bool":
      return typeof v === "boolean" ? null : bad("must be true or false");
    case "date":
      return typeof v === "string" && DATE.test(v) && !Number.isNaN(Date.parse(v + "T00:00:00Z")) ? null : bad("must be a date YYYY-MM-DD");
    case "timestamp":
      return typeof v === "string" && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(v) && !Number.isNaN(Date.parse(v)) ? null : bad("must be an ISO 8601 timestamp");
    case "json":
      return null;
    case "text[]":
      if (!Array.isArray(v) || v.some((x) => typeof x !== "string" || x.trim() === "")) return bad("must be a list of non-empty strings");
      if (f.enum && v.some((x) => !f.enum!.includes(x as string))) return bad(`each must be one of ${f.enum.join(", ")}`);
      return null;
    case "int[]":
      return Array.isArray(v) && v.every((x) => typeof x === "number" && Number.isInteger(x)) ? null : bad("must be a list of integers");
    case "num[]":
      if (!Array.isArray(v) || !v.every((x) => typeof x === "number" && Number.isFinite(x))) return bad("must be a list of finite numbers");
      if (f.len !== undefined && v.length !== f.len) return bad(`must have ${f.len} numbers`);
      return null;
    case "object[]":
      return Array.isArray(v) && v.every(isObj) ? null : bad("must be a list of objects");
  }
}

function checkShape(spec: Record<string, F>, row: unknown, where = ""): string | null {
  if (!isObj(row)) return `${where}row must be an object`;
  for (const k of Object.keys(row)) {
    if (REVIEW_FIELDS.includes(k)) return `${where}${k}: review fields are written by people only, never through the ingest API`;
    if (!(k in spec)) return `${where}unknown field ${k}`;
  }
  for (const [k, f] of Object.entries(spec)) {
    const v = row[k];
    if (v === undefined || v === null) {
      if (f.req) return `${where}${k}: required`;
      continue;
    }
    const err = checkValue(k, f, v);
    if (err) return where + err;
  }
  return null;
}

/** What the database already knows, for reference checks. */
export interface Refs {
  heads: Set<string>;
  parameterDefs: Set<string>;
  utilities: Set<string>;
  states: Set<string>;
  commissions: Set<string>;
}

/** Validate one row of a kind.  Returns the row with absent optionals left absent. */
export function validateRow(kind: string, row: unknown, refs: Refs): Checked {
  const spec = SPECS[kind];
  if (!spec) return { ok: false, reason: `unknown kind ${kind}` };
  const shape = checkShape(spec, row);
  if (shape) return { ok: false, reason: shape };
  const x = row as Row;
  const fail = (reason: string): Checked => ({ ok: false, reason });

  if ("head" in spec && x.head !== undefined && !refs.heads.has(x.head as string)) return fail(`head: unknown head code ${x.head}`);
  if (kind === "parameters" && !refs.parameterDefs.has(x.code as string)) return fail(`code: unknown parameter code ${x.code}`);
  if ("utility" in spec && x.utility !== undefined && x.utility !== null && x.utility !== "TOTAL" && !refs.utilities.has(x.utility as string)) {
    return fail(`utility: unknown utility code ${x.utility}`);
  }
  switch (kind) {
    case "commissions":
      for (const s of x.states as string[]) if (!refs.states.has(s)) return fail(`states: unknown state code ${s}`);
      break;
    case "utilities":
      if (!refs.commissions.has(x.commission as string)) return fail(`commission: unknown commission ${x.commission}`);
      if (!refs.states.has(x.state as string)) return fail(`state: unknown state code ${x.state}`);
      break;
    case "orders":
      if (!refs.commissions.has(x.commission as string)) return fail(`commission: unknown commission ${x.commission}`);
      for (const u of x.utilities as string[]) if (!refs.utilities.has(u)) return fail(`utilities: unknown utility code ${u}`);
      break;
    case "section_tables": {
      const cols = x.columns as unknown;
      if (!Array.isArray(cols) || !cols.length || cols.some((c) => typeof c !== "string")) return fail("columns: must be a non-empty list of strings");
      const rows = x.rows as Row[];
      if (!rows.length) return fail("rows: at least one row is required");
      for (let i = 0; i < rows.length; i++) {
        const rw = rows[i];
        const cells = rw.cells as unknown;
        if (!Array.isArray(cells) || cells.some((c) => typeof c !== "string")) return fail(`rows[${i}].cells: must be a list of strings`);
        if (cells.length !== cols.length) return fail(`rows[${i}].cells: ${cells.length} cells for ${cols.length} columns`);
        if (!cells.some((c) => (c as string).trim())) return fail(`rows[${i}].cells: an empty row`);
        if (typeof rw.page !== "number" || !Number.isInteger(rw.page) || rw.page < 1) return fail(`rows[${i}].page: must be an integer >= 1`);
        const extra = Object.keys(rw).filter((k) => k !== "cells" && k !== "page");
        if (extra.length) return fail(`rows[${i}]: unknown field ${extra[0]}`);
      }
      break;
    }
    case "facts": {
      const readings = x.readings as Row[];
      if (!readings.length) return fail("readings: at least one reading is required");
      for (let i = 0; i < readings.length; i++) {
        const e = checkShape(READING, readings[i], `readings[${i}].`);
        if (e) return fail(e);
      }
      const readers = new Set(x.readers as string[]);
      if (!readers.size) return fail("readers: at least one reader is required");
      const need = { single: 1, agreed_2: 2, agreed_3: 3, conflict: 2 }[x.consensus as string] ?? 1;
      if (readers.size < need) return fail(`consensus: ${x.consensus} needs ${need} distinct readers, readers lists ${readers.size}`);
      if (x.consensus === "conflict" && !readings.some((g) => g.agrees === false)) return fail("consensus: a conflict needs at least one reading that does not agree");
      if (x.consensus !== "conflict" && readings.some((g) => g.agrees === false)) return fail(`consensus: ${x.consensus} but a reading does not agree; post it as a conflict`);
      break;
    }
  }
  return { ok: true, row: x };
}

/** The numeric tokens of a printed value: "(1,234.50)" -> ["1,234.50"]. */
export function numericTokens(printed: string): string[] {
  return printed.match(/\d[\d,]*(?:\.\d+)?/g) ?? [];
}

const norm = (s: string) => s.replace(/\s+/g, " ").trim();

/** INGEST.md: with white space normalised, the page text must contain each numeric token. */
export function numberOnPage(printed: string, pageText: string): boolean {
  const text = norm(pageText);
  const tokens = numericTokens(printed);
  if (!tokens.length) return false;
  return tokens.every((t) => text.includes(t));
}

/** Validate the envelope of a batch request.  Returns the rows or an error for a 400 / 413. */
export const MAX_ROWS = 2000;
export const MAX_BYTES = 8 * 1024 * 1024;

export function checkEnvelope(body: unknown): { ok: true; kind: string; rows: unknown[] } | { ok: false; status: 400 | 413; error: string } {
  if (!isObj(body)) return { ok: false, status: 400, error: "the body must be a JSON object {kind, rows}" };
  const extra = Object.keys(body).filter((k) => k !== "kind" && k !== "rows");
  if (extra.length) return { ok: false, status: 400, error: `unknown field ${extra[0]}` };
  if (typeof body.kind !== "string" || !SPECS[body.kind]) return { ok: false, status: 400, error: `kind must be one of ${KINDS.join(", ")}` };
  if (!Array.isArray(body.rows)) return { ok: false, status: 400, error: "rows must be a list" };
  if (body.rows.length > MAX_ROWS) return { ok: false, status: 413, error: `more than ${MAX_ROWS} rows` };
  return { ok: true, kind: body.kind, rows: body.rows };
}
