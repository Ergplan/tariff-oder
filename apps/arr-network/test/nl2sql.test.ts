// The plain-English translator, ported from apps/arr-db/nl2sql.test.mjs.  Year parsing runs
// always; the rest runs against the database in DATABASE_URL (the dev seed or the pipeline's
// data) and is skipped when it is not set.  Hand-read figures come from
// packages/order-reproductions: people read them from the same orders, page by page.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import postgres from "postgres";
import { translate, yearsIn, currentFy } from "../lib/nl2sql.ts";
import { loadVocab } from "../lib/ask.ts";
import { EXAMPLES } from "../lib/examples.ts";
import { checkSelect } from "../lib/sqlguard.ts";

test("years are read the ways people write them", () => {
  assert.deepEqual(yearsIn("FY 2026-27"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("for 2024-25 and FY25-26?"), ["FY2024-25"]);
  assert.deepEqual(yearsIn("FY27"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("FY2026-2027"), ["FY2026-27"]);
  assert.deepEqual(yearsIn("in 2026"), []);
  assert.equal(currentFy(new Date("2026-11-11T00:00:00Z")), "FY2026-27");
  assert.equal(currentFy(new Date("2027-02-01T00:00:00Z")), "FY2026-27");
});

test("the SQL guard admits one SELECT and refuses everything else", () => {
  assert.equal(checkSelect("SELECT 1;").ok, true);
  assert.equal(checkSelect("WITH a AS (SELECT 1) SELECT * FROM a").ok, true);
  assert.equal(checkSelect("SELECT ';' AS semi, 'drop table x' AS t").ok, true);
  assert.equal(checkSelect("SELECT set_aside FROM v_arr").ok, true);
  for (const bad of ["DELETE FROM facts", "SELECT 1; DROP TABLE facts", "UPDATE facts SET value = 0",
    "SELECT set_config('statement_timeout', '0', true)", "SELECT pg_sleep(10)", "WITH x AS (DELETE FROM facts RETURNING *) SELECT * FROM x",
    "SELECT * INTO t FROM facts", "SELECT 1 /* ; */ ; SELECT 2", "  "]) {
    assert.equal(checkSelect(bad).ok, false, bad);
  }
});

const url = process.env.DATABASE_URL;
const opts = { skip: url ? false : "DATABASE_URL not set" };
const handRead = (pkg: string, file: string) =>
  JSON.parse(readFileSync(new URL(`../../../packages/order-reproductions/${pkg}/order/${file}`, import.meta.url), "utf8")).figures as Record<string, { value: string; page: number }>;

test("against the database", opts, async (t) => {
  const sql = postgres(url!, { prepare: false, max: 2, onnotice: () => {}, types: { numeric: { to: 1700, from: [1700], serialize: String, parse: Number }, bigint: { to: 20, from: [20], serialize: String, parse: Number } } as never });
  const run = async (q: string) => [...(await sql.unsafe(q))] as Record<string, unknown>[];
  try {
    const vocab = await loadVocab(sql as never, new Date("2026-11-11T00:00:00Z"));
    const ask = async (qn: string) => { const tr = translate(qn, vocab); return { ...tr, rows: await run(tr.sql) }; };

    await t.test("the latest year never runs ahead of the calendar", () => assert.equal(vocab.latestYear, "FY2026-27"));

    await t.test("every example runs and explains itself", async () => {
      for (const e of EXAMPLES) {
        const tr = await ask(e);
        assert.ok(/^\s*(WITH|SELECT)/i.test(tr.sql), e);
        assert.ok(tr.kind === "meta" || tr.explain.length >= 2, `${e}: explained`);
      }
    });

    await t.test("UPCL's approved net ARR for FY2026-27 is the figure read by hand from UERC Table 4.52", async () => {
      const fig = handRead("uerc-upcl-fy2026-27", "figures-arr-fy2026-27.json");
      const key = Object.keys(fig).find((k) => /net/.test(k) && /approved$/.test(k))!;
      const tr = await ask("Approved ARR of UPCL for FY 2026-27");
      assert.equal(tr.rows.length, 1);
      assert.equal(tr.rows[0].arr_crore, Number(fig[key].value));
      assert.equal(tr.rows[0].page, fig[key].page);
      assert.ok(tr.rows[0].consensus, "the answer carries its consensus class");
    });

    await t.test("the MP state total admitted ARR matches MPERC Table 74 as read by hand", async () => {
      const fig = handRead("mperc-discoms-fy2026-27", "figures-arr-fy2026-27.json");
      const tr = await ask("State total approved ARR of Madhya Pradesh for FY2026-27");
      const total = tr.rows.find((r) => r.utility === "TOTAL");
      assert.ok(total, "the state total row is included when asked for");
      assert.equal(total.arr_crore, Number(fig["arr.total.state.admitted"].value));
      for (const [code, part] of [["MPPaKVVCL", "east"], ["MPPKVVCL", "west"], ["MPMKVVCL", "central"]]) {
        assert.equal(tr.rows.find((r) => r.utility === code)?.arr_crore, Number(fig[`arr.total.${part}.admitted`].value), code);
      }
    });

    await t.test("claimed versus approved pairs the two figures of one order", async () => {
      const tr = await ask("Claimed vs approved ARR for Odisha discoms in FY2026-27");
      assert.equal(tr.kind, "compare");
      assert.equal(tr.rows.length, 4);
      for (const r of tr.rows) {
        assert.ok(Math.abs((r.claimed_crore as number) - (r.approved_crore as number) - (r.disallowed_crore as number)) < 0.011, String(r.utility));
        assert.equal(r.claimed_page, r.approved_page);
      }
    });

    await t.test("ranking leaves out state totals and honours the number asked for", async () => {
      const one = await ask("Which discom has the highest approved ARR in FY2026-27?");
      assert.equal(one.rows.length, 1);
      assert.notEqual(one.rows[0].utility, "TOTAL");
      const five = await ask("Top 5 discoms by approved return on equity in FY2025-26");
      assert.equal(five.rows.length, 5);
      const v = five.rows.map((r) => r.value_crore as number);
      assert.deepEqual(v, [...v].sort((a, b) => b - a));
    });

    await t.test("a ranking says how many DISCOMs it ranks", async () => {
      const tr = await ask("Which discom has the highest approved ARR in FY2026-27?");
      const covered = (await run(tr.coverage!.covered))[0].n as number;
      const listed = (await run(tr.coverage!.listed))[0].n as number;
      assert.ok(covered > 0 && covered < listed);
      assert.equal(listed, (await run("SELECT COUNT(*) AS n FROM utilities WHERE kind = 'discom'"))[0].n);
      const up = await ask("Total approved ARR of Uttar Pradesh discoms in FY2026-27");
      assert.equal((await run(up.coverage!.listed))[0].n, 6);
      assert.equal((await run(up.coverage!.covered))[0].n, up.rows[0].utilities_counted);
    });

    await t.test("a sum names the utilities it adds up", async () => {
      const tr = await ask("Total approved ARR of Uttar Pradesh discoms in FY2026-27");
      assert.equal(tr.kind, "aggregate");
      assert.equal(tr.rows.length, 1);
      assert.equal(tr.rows[0].utilities_counted, String(tr.rows[0].utilities).split(", ").length);
    });

    await t.test("a trend lists one row per year, in order", async () => {
      const tr = await ask("Trend of approved ARR for NPCL");
      assert.ok(tr.rows.length >= 2);
      const ys = tr.rows.map((r) => r.fiscal_year as string);
      assert.deepEqual(ys, [...ys].sort());
      assert.equal(new Set(ys).size, ys.length);
    });

    await t.test("a stage without a year is not pinned to the latest year", async () => {
      const tr = await ask("Trued-up ARR of JBVNL");
      assert.ok(!/fiscal_year = 'FY2026-27'/.test(tr.sql));
      assert.ok(/stage = 'True-up'/.test(tr.sql));
    });

    await t.test("questions about the database read its catalogue", async () => {
      const tr = await ask("Which commissions could not be reached?");
      assert.equal(tr.kind, "meta");
      assert.ok(tr.rows.length > 0);
      assert.ok(tr.rows.every((r) => r.website_reached === "no"));
    });

    await t.test("no answer row comes from a bottom line set aside as implausible", async () => {
      const aside = new Set((await run("SELECT fact_id FROM facts WHERE is_headline AND set_aside IS NOT NULL")).map((r) => r.fact_id));
      const shown = (await run("SELECT fact_id FROM v_arr")).map((r) => r.fact_id);
      for (const id of shown) assert.ok(!aside.has(id));
    });
  } finally {
    await sql.end();
  }
});
