// node --test apps/arr-db/nl2sql.test.mjs   (Node 22+, uses the built-in node:sqlite)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { translate, yearsIn } from "./nl2sql.js";
import { vocabFrom } from "./vocab.js";

const here = new URL(".", import.meta.url);
const db = new DatabaseSync(new URL("data/arr.sqlite", here).pathname, { readOnly: true });
const all = (sql) => db.prepare(sql).all();
const vocab = vocabFrom(all, new Date("2026-11-11T00:00:00Z"));
const ask = (qn) => { const t = translate(qn, vocab); return { ...t, rows: all(t.sql) }; };
const handRead = (pkg, file) => JSON.parse(readFileSync(new URL(`../../packages/order-reproductions/${pkg}/order/${file}`, here))).figures;

test("years are read the ways people write them", () => {
  assert.deepEqual(yearsIn("FY 2026-27"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("for 2024-25 and FY25-26?"), ["FY2024-25"]);
  assert.deepEqual(yearsIn("FY27"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("FY2026-2027"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("in 2026"), []);
});

test("the latest year never runs ahead of the calendar", () => {
  assert.equal(vocab.latestYear, "FY2026-27");
});

test("every example on the page runs and explains itself", () => {
  const html = readFileSync(new URL("app.js", here), "utf8");
  const examples = [...html.matchAll(/^\s+"([^"]+\?|[^"]+)",$/gm)].map((m) => m[1]).filter((s) => / /.test(s));
  assert.ok(examples.length >= 8);
  for (const e of examples) {
    const t = ask(e);
    assert.ok(t.sql.trim().toUpperCase().startsWith("WITH") || t.sql.trim().toUpperCase().startsWith("SELECT"), e);
    assert.ok(t.kind === "meta" || t.explain.length >= 2, `${e}: explained`);
  }
});

test("UPCL's approved net ARR for FY2026-27 is the figure read by hand from UERC Table 4.52", () => {
  const fig = handRead("uerc-upcl-fy2026-27", "figures-arr-fy2026-27.json");
  const key = Object.keys(fig).find((k) => /net/.test(k) && /approved$/.test(k));
  const t = ask("Approved ARR of UPCL for FY 2026-27");
  assert.equal(t.rows.length, 1);
  assert.equal(t.rows[0].arr_crore, Number(fig[key].value));
  assert.equal(t.rows[0].page, fig[key].page);
});

test("the MP state total admitted ARR matches MPERC Table 74 as read by hand", () => {
  const fig = handRead("mperc-discoms-fy2026-27", "figures-arr-fy2026-27.json");
  const t = ask("State total approved ARR of Madhya Pradesh for FY2026-27");
  const total = t.rows.find((r) => r.discom === "TOTAL");
  assert.ok(total, "the state total row is included when asked for");
  assert.equal(total.arr_crore, Number(fig["arr.total.state.admitted"].value));
  for (const [code, part] of [["MPPaKVVCL", "east"], ["MPPKVVCL", "west"], ["MPMKVVCL", "central"]]) {
    assert.equal(t.rows.find((r) => r.discom === code).arr_crore, Number(fig[`arr.total.${part}.admitted`].value), code);
  }
});

test("claimed versus approved pairs the two figures of one order", () => {
  const t = ask("Claimed vs approved ARR for Odisha discoms in FY2026-27");
  assert.equal(t.kind, "compare");
  assert.equal(t.rows.length, 4);
  for (const r of t.rows) {
    assert.ok(Math.abs(r.claimed_crore - r.approved_crore - r.disallowed_crore) < 0.011, r.discom);
    assert.equal(r.claimed_page, r.approved_page);
  }
});

test("ranking leaves out state totals and honours the number asked for", () => {
  const one = ask("Which discom has the highest approved ARR in FY2026-27?");
  assert.equal(one.rows.length, 1);
  assert.notEqual(one.rows[0].discom, "TOTAL");
  const five = ask("Top 5 discoms by approved return on equity in FY2025-26");
  assert.equal(five.rows.length, 5);
  const v = five.rows.map((r) => r.value_crore);
  assert.deepEqual(v, [...v].sort((a, b) => b - a));
});

test("a ranking says how many DISCOMs it ranks", () => {
  const t = ask("Which discom has the highest approved ARR in FY2026-27?");
  const covered = all(t.coverage.covered)[0].n;
  const listed = all(t.coverage.listed)[0].n;
  assert.ok(covered > 0 && covered < listed);
  assert.equal(listed, all("SELECT COUNT(*) AS n FROM discoms")[0].n);
  const up = ask("Total approved ARR of Uttar Pradesh discoms in FY2026-27");
  assert.equal(all(up.coverage.listed)[0].n, 6);
  assert.equal(all(up.coverage.covered)[0].n, up.rows[0].discoms_counted);
});

test("a sum names the DISCOMs it adds up", () => {
  const t = ask("Total approved ARR of Uttar Pradesh discoms in FY2026-27");
  assert.equal(t.kind, "aggregate");
  assert.equal(t.rows.length, 1);
  assert.equal(t.rows[0].discoms_counted, t.rows[0].discoms.split(", ").length);
});

test("a stage without a year is not pinned to the latest year", () => {
  const t = ask("Trued-up ARR of JBVNL");
  assert.ok(!/fiscal_year = 'FY2026-27'/.test(t.sql));
  assert.ok(/stage = 'True-up'/.test(t.sql));
});

test("questions about the database read its catalogue", () => {
  const t = ask("Which commissions could not be reached?");
  assert.equal(t.kind, "meta");
  assert.ok(t.rows.length > 0);
  assert.ok(t.rows.every((r) => r.website_reached === "no"));
});

test("no answer row comes from a bottom line set aside as implausible", () => {
  const aside = all("SELECT value_id FROM arr_headline WHERE set_aside IS NOT NULL").map((r) => r.value_id);
  const shown = new Set(all("SELECT value_id FROM v_arr").map((r) => r.value_id));
  for (const id of aside) assert.ok(!shown.has(id));
});
