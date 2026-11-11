#!/usr/bin/env node
// Dev seed: loads the real machine-read data of apps/arr-db (one reader: the text-layer reader,
// "arrdb-reader 1") into a running ARR Network app through its ingest API, in INGEST.md shapes.
// It is not a fixture: every figure is a reading of a real order, with its page and quote.
// The pipeline (tools/arrnet) later replaces it with multi-reader data through the same API.
//
//   INGEST_URL=http://localhost:3100 INGEST_TOKEN=... node scripts/dev-seed.mjs [--migrate]
//
// Node 22+ (node:sqlite).  Idempotent: orders, parses, tables and facts are upserts, and each
// parse's tables and values are replaced (replace: true) on a re-run.
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..", "..");
const URL_ = (process.env.INGEST_URL || "http://localhost:3100").replace(/\/$/, "");
const TOKEN = process.env.INGEST_TOKEN;
if (!TOKEN) { console.error("set INGEST_TOKEN (the same value the app has)"); process.exit(2); }

const sqlite = new DatabaseSync(join(repo, "apps/arr-db/data/arr.sqlite"), { readOnly: true });
const all = (q, ...p) => sqlite.prepare(q).all(...p);
const registry = JSON.parse(readFileSync(join(repo, "tools/arrdb/registry.json"), "utf8"));
const geo = JSON.parse(readFileSync(join(here, "..", "data", "india-states.json"), "utf8"));
const READER = { reader: "textlayer", reader_version: all("SELECT value FROM build_info WHERE key = 'reader'")[0]?.value || "arrdb-reader 1" };
const CHECKED_ON = all("SELECT value FROM build_info WHERE key = 'built_on'")[0]?.value || null;

// Which states each commission regulates (ISO 3166-2:IN codes as in india-states.json).
const COMMISSION_STATES = {
  UPERC: ["UP"], BERC: ["BR"], HPERC: ["HP"], JSERC: ["JH"], MPERC: ["MP"], OERC: ["OD"], UERC: ["UK"],
  "JERC-GOA-UT": ["GA", "PY", "AN", "CH", "DH", "LD"], DERC: ["DL"], CSERC: ["CG"], KSERC: ["KL"], MERC: ["MH"],
  GERC: ["GJ"], KERC: ["KA"], TNERC: ["TN"], APERC: ["AP"], TGERC: ["TS"], PSERC: ["PB"], HERC: ["HR"], RERC: ["RJ"],
  WBERC: ["WB"], AERC: ["AS"], JKERC: ["JK", "LA"], "JERC-MM": ["MN", "MZ"], TERC: ["TR"], MSERC: ["ML"],
  SSERC: ["SK"], NERC: ["NL"], APSERC: ["AR"],
};
// A utility's state where its commission regulates more than one.
const UTILITY_STATE = { "GOA-ED": "GA", "PED-PY": "PY", MSPDCL: "MN", "PED-MZ": "MZ", JPDCL: "JK", KPDCL: "JK" };
// Display order of the heads (sort), bottom line first.
const HEAD_ORDER = ["arr", "net_arr", "power_purchase", "transmission", "om", "employee", "rm", "ag", "depreciation",
  "interest_loan", "interest_wc", "interest_sd", "finance_charges", "roe", "tax", "bad_debts", "carrying_cost",
  "regulatory_asset", "nti", "revenue", "gap", "other"];

let posted = 0, rejectedTotal = 0;
async function call(path, body) {
  const res = await fetch(URL_ + path, {
    method: "POST",
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status} ${text.slice(0, 500)}`);
  return JSON.parse(text);
}
async function batch(kind, rows, size = 1000) {
  let written = 0;
  const rejected = [];
  for (let i = 0; i < rows.length; i += size) {
    const part = rows.slice(i, i + size);
    const r = await call("/api/ingest/batch", { kind, rows: part });
    written += r.written;
    for (const x of r.rejected) rejected.push({ ...x, index: x.index + i });
  }
  posted += written; rejectedTotal += rejected.length;
  console.log(`${kind.padEnd(14)} written ${String(written).padStart(6)}  rejected ${rejected.length}`);
  for (const x of rejected.slice(0, 5)) console.log(`   row ${x.index}: ${x.reason}`);
  return { written, rejected };
}
const nn = (v) => (v === null || v === undefined || v === "" ? undefined : v);
const strip = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined));

if (process.argv.includes("--migrate")) console.log("migrate:", await call("/api/ingest/migrate"));

// ---- reference
await batch("states", geo.states.map((s) => ({ code: s.code, name: s.name, kind: s.kind })));
await batch("commissions", registry.commissions.map((c) => strip({
  code: c.code, name: c.name, website: nn(c.website), website_reachable: typeof c.website_reachable === "boolean" ? c.website_reachable : undefined,
  checked_on: CHECKED_ON ?? undefined, states: COMMISSION_STATES[c.code] ?? (() => { throw new Error(`no states for ${c.code}`); })(),
})));
await batch("utilities", registry.discoms.map((d) => ({
  code: d.code, name: d.name, kind: "discom", commission: d.commission,
  state: UTILITY_STATE[d.code] ?? COMMISSION_STATES[d.commission][0], ownership: d.ownership, aliases: d.aliases ?? [],
})));
await batch("heads", all("SELECT code, name FROM heads").map((h) => ({
  code: h.code, name: h.name, sort: HEAD_ORDER.includes(h.code) ? (HEAD_ORDER.indexOf(h.code) + 1) * 10 : 900,
})));

// ---- orders
const orderUtils = new Map();
for (const r of all("SELECT order_id, discom FROM order_discoms")) {
  if (!orderUtils.has(r.order_id)) orderUtils.set(r.order_id, new Set());
  orderUtils.get(r.order_id).add(r.discom);
}
const orders = all("SELECT * FROM orders ORDER BY order_id");
const urlOf = new Map(orders.map((o) => [o.order_id, o.url]));
const STATUS = { read: "read", no_tables_found: "no_tables_found", no_text_layer: "no_text_layer", not_downloaded: "listed" };
await batch("orders", orders.map((o) => strip({
  commission: o.commission, title: o.title, url: o.url, sha256: nn(o.sha256), pages: o.pages ?? undefined,
  pages_without_text: o.pages_without_text ?? undefined, arr_year: nn(o.arr_year),
  years_decided: o.years_decided ? o.years_decided.split(",").map((s) => s.trim()).filter(Boolean) : [],
  kind: nn(o.kind), utility_kind: "discom", found_by: nn(o.found_by),
  fetched_on: /^\d{4}-\d{2}-\d{2}$/.test(o.fetched_on || "") ? o.fetched_on : undefined,
  read_status: STATUS[o.read_status] ?? (o.sha256 ? "downloaded" : "listed"),
  utilities: [...(orderUtils.get(o.order_id) ?? [])],
})));

// ---- one text-layer parse per read order
const read = orders.filter((o) => o.read_status === "read");
const tableCount = new Map(all("SELECT order_id, COUNT(*) AS n, COUNT(DISTINCT page) AS p FROM arr_tables GROUP BY order_id").map((r) => [r.order_id, r]));
await batch("parses", read.map((o) => ({
  order_url: o.url, ...READER, is_real: true, status: "ok", cost_usd: 0,
  note: `ARR tables read from the PDF text layer by tools/arrdb (${tableCount.get(o.order_id)?.n ?? 0} tables). Migrated from apps/arr-db/data/arr.sqlite.`,
})));

// ---- tables, values: grouped per order so each parse's rows are replaced together
const tables = all("SELECT * FROM arr_tables ORDER BY order_id, table_id");
const tableOf = new Map(tables.map((t) => [t.table_id, t]));
const ptRows = tables.filter((t) => urlOf.has(t.order_id) && read.some((o) => o.order_id === t.order_id)).map((t, i, arr) => strip({
  order_url: urlOf.get(t.order_id), ...READER, page: t.page,
  pages: String(t.pages).split(",").map((s) => Number(s.trim())).filter(Number.isInteger),
  title: t.title, unit: nn(t.unit), unit_from: nn(t.unit_from), columns: JSON.parse(t.columns_json),
  // replace: true on the first row of the batch clears every parse in that batch (INGEST.md "Keys")
  replace: i === 0 || i % 1000 === 0 ? true : undefined,
}));
// the batch size and the replace flag must line up: one flag per 1,000-row batch
await batch("parsed_tables", ptRows, 1000);

const values = all("SELECT * FROM arr_values ORDER BY order_id, value_id");
const avRows = values.map((v) => {
  const t = tableOf.get(v.table_id);
  return strip({
    order_url: urlOf.get(v.order_id), ...READER, table_page: t.page, table_title: t.title,
    utility: nn(v.discom), fiscal_year: nn(v.fiscal_year), voice: nn(v.voice), stage: nn(v.stage), head: v.head, label: v.label,
    group_label: nn(v.group_label), value_printed: v.value_printed, value: v.value, unit: nn(v.unit),
    value_crore: v.value_crore ?? undefined, page: v.page, quote: v.quote, column_header: nn(v.column_header),
    year_from: nn(v.year_from), voice_from: nn(v.voice_from), is_primary: v.is_primary === 1,
  });
});
// values were cleared with their tables above; no replace flag here (readings are appended)
await batch("arr_values", avRows, 1000);

// ---- facts: one per (order, utility, year, voice, head, label, page), single reader
const headline = new Map(all("SELECT * FROM arr_headline").map((h) => [h.value_id, h]));
const facts = new Map();
const rank = (v) => (headline.has(v.value_id) ? 0 : v.is_primary ? 1 : 2);
let collapsed = 0;
for (const v of values) {
  if (!v.discom || !v.fiscal_year || !v.voice) continue; // a fact needs whose, which year and whose voice
  const key = [v.order_id, v.discom, v.fiscal_year, v.voice, v.head, v.label, v.page].join("\u0000");
  const cur = facts.get(key);
  if (cur) collapsed++;
  if (!cur || rank(v) < rank(cur) || (rank(v) === rank(cur) && v.value_id < cur.value_id)) facts.set(key, v);
}
const factRows = [...facts.values()].map((v) => {
  const h = headline.get(v.value_id);
  return strip({
    order_url: urlOf.get(v.order_id), utility: v.discom, fiscal_year: v.fiscal_year, voice: v.voice, stage: nn(v.stage),
    head: v.head, label: v.label, value_crore: v.value_crore ?? undefined, value: v.value, unit: nn(v.unit), page: v.page,
    quote: v.quote, consensus: "single", readers: ["textlayer"],
    is_headline: h ? true : undefined, headline_why: h ? h.why : undefined, set_aside: h ? nn(h.set_aside) : undefined,
    readings: [{ ...READER, page: v.page, value_printed: v.value_printed, agrees: true }],
  });
});
console.log(`facts: ${factRows.length} (${collapsed} readings share a fact's key with another row of the same page and were not made separate facts)`);
await batch("facts", factRows, 1000);

console.log(`done: ${posted} rows written, ${rejectedTotal} rejected`);
