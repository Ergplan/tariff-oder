// Unit tests of the ingest validators.  Rows here are obviously synthetic (codes such as
// "TEST-U1", values such as 123.45); none of them is a figure from an order.
import test from "node:test";
import assert from "node:assert/strict";
import { validateRow, numberOnPage, numericTokens, checkEnvelope, SPECS, REVIEW_FIELDS, type Refs } from "../lib/ingest/validate.ts";

const refs: Refs = {
  heads: new Set(["arr", "power_purchase"]),
  parameterDefs: new Set(["distribution_loss_pct"]),
  utilities: new Set(["TEST-U1", "TEST-U2"]),
  states: new Set(["XX", "YY"]),
  commissions: new Set(["TEST-C"]),
};
const url = "https://example.invalid/synthetic-order.pdf";
const parse = { order_url: url, reader: "textlayer", reader_version: "test 0" };
const value = {
  ...parse, utility: "TEST-U1", fiscal_year: "FY2099-00", voice: "approved", head: "arr", label: "Synthetic row",
  value_printed: "123.45", value: 123.45, page: 3, quote: "Synthetic row 123.45",
};
const fact = {
  order_url: url, utility: "TEST-U1", fiscal_year: "FY2099-00", voice: "approved", head: "arr", label: "Synthetic row",
  value: 123.45, page: 3, quote: "Synthetic row 123.45", consensus: "single", readers: ["textlayer"],
  readings: [{ reader: "textlayer", reader_version: "test 0", page: 3, value_printed: "123.45", agrees: true }],
};
const ok = (kind: string, row: unknown) => { const r = validateRow(kind, row, refs); assert.equal(r.ok, true, r.ok ? "" : r.reason); };
const no = (kind: string, row: unknown, re: RegExp) => {
  const r = validateRow(kind, row, refs);
  assert.equal(r.ok, false, `${kind} should be rejected`);
  if (!r.ok) assert.match(r.reason, re);
};

test("well-formed rows of each value kind pass", () => {
  ok("arr_values", value);
  ok("facts", fact);
  ok("parameters", { ...parse, code: "distribution_loss_pct", label: "Synthetic loss", value_printed: "9.9%", value: 9.9, unit: "%", page: 2, quote: "loss 9.9%" });
  ok("states", { code: "XX", name: "Test state", kind: "state" });
  ok("orders", { commission: "TEST-C", title: "Synthetic order", url, utilities: ["TEST-U1"], read_status: "read" });
});

test("unknown fields are refused", () => {
  no("arr_values", { ...value, colour: "red" }, /unknown field colour/);
  no("states", { code: "XX", name: "x", kind: "state", extra: 1 }, /unknown field extra/);
});

test("review fields are refused on every kind, even when null", () => {
  for (const f of REVIEW_FIELDS) {
    no("facts", { ...fact, [f]: "someone" }, /review fields are written by people only/);
    no("facts", { ...fact, [f]: null }, /review fields/);
    no("parameters", { ...parse, code: "distribution_loss_pct", label: "x", value_printed: "1", value: 1, unit: "%", page: 1, quote: "1", [f]: "x" }, /review fields/);
  }
  for (const spec of Object.values(SPECS)) for (const f of REVIEW_FIELDS) assert.ok(!(f in spec), `${f} must never be an accepted field`);
});

test("a value needs a page, a quote and a finite number", () => {
  no("arr_values", { ...value, page: 0 }, /page: must be >= 1/);
  no("arr_values", { ...value, page: 2.5 }, /page: must be an integer/);
  const { page: _p, ...noPage } = value;
  no("arr_values", noPage, /page: required/);
  no("arr_values", { ...value, quote: "   " }, /quote: must not be empty/);
  no("arr_values", { ...value, quote: undefined }, /quote: required/);
  no("arr_values", { ...value, value: Number.NaN }, /value: must be a finite number/);
  no("arr_values", { ...value, value: "123.45" }, /value: must be a finite number/);
  no("facts", { ...fact, value: Infinity }, /value: must be a finite number/);
  no("parameters", { ...parse, code: "distribution_loss_pct", label: "x", value_printed: "1", value: 1, unit: "%", page: 1, quote: "" }, /quote/);
});

test("voice, stage, consensus, reader and kind must be in the schema's lists", () => {
  no("arr_values", { ...value, voice: "guessed" }, /voice: must be one of/);
  no("arr_values", { ...value, stage: "Draft" }, /stage: must be one of/);
  no("arr_values", { ...value, reader: "gpt" }, /reader: must be one of/);
  no("facts", { ...fact, consensus: "probably" }, /consensus: must be one of/);
  no("facts", { ...fact, readers: ["textlayer", "oracle"] }, /readers: each must be one of/);
  no("states", { code: "XX", name: "x", kind: "province" }, /kind: must be one of/);
  no("paragraphs", { order_url: url, page: 1, seq: 0, kind: "gossip", text: "x" }, /kind: must be one of/);
});

test("head, parameter code and utility must be known", () => {
  no("arr_values", { ...value, head: "made_up" }, /unknown head code/);
  no("parameters", { ...parse, code: "nope", label: "x", value_printed: "1", value: 1, unit: "%", page: 1, quote: "1" }, /unknown parameter code/);
  no("arr_values", { ...value, utility: "NOBODY" }, /unknown utility code/);
  ok("arr_values", { ...value, utility: "TOTAL" });
  const { utility: _u, ...noUtility } = value;
  ok("arr_values", noUtility);
  no("facts", { ...fact, utility: "NOBODY" }, /unknown utility code/);
  no("orders", { commission: "TEST-C", title: "x", url, utilities: ["NOBODY"] }, /unknown utility code/);
  no("utilities", { code: "N", name: "n", kind: "discom", commission: "TEST-C", state: "ZZ", ownership: "state" }, /unknown state code/);
});

test("consensus must be backed by its readers and readings", () => {
  no("facts", { ...fact, consensus: "agreed_2" }, /needs 2 distinct readers/);
  no("facts", { ...fact, consensus: "agreed_3", readers: ["textlayer", "docling"] }, /needs 3 distinct readers/);
  ok("facts", {
    ...fact, consensus: "agreed_2", readers: ["textlayer", "docling"],
    readings: [...fact.readings, { reader: "docling", reader_version: "test 0", page: 3, value_printed: "123.45", agrees: true }],
  });
  no("facts", { ...fact, consensus: "conflict", readers: ["textlayer", "docling"] }, /conflict needs at least one reading that does not agree/);
  no("facts", { ...fact, readings: [{ ...fact.readings[0], agrees: false }] }, /post it as a conflict/);
  no("facts", { ...fact, readings: [] }, /at least one reading/);
  no("facts", { ...fact, readings: [{ ...fact.readings[0], extra: 1 }] }, /readings\[0\]\.unknown field extra/);
});

test("the number-on-page check reads every numeric token of the printed value", () => {
  assert.deepEqual(numericTokens("(1,234.50)"), ["1,234.50"]);
  assert.deepEqual(numericTokens("12.5 / 7"), ["12.5", "7"]);
  assert.equal(numberOnPage("1,234.50", "Synthetic   row\n 1,234.50  next"), true);
  assert.equal(numberOnPage("(1,234.50)", "row 1,234.50"), true);
  assert.equal(numberOnPage("1,234.50", "row 1,234.5"), false);
  assert.equal(numberOnPage("12.5 / 7", "a 12.5 b 8"), false);
  assert.equal(numberOnPage("nil", "nil"), false);
});

test("the batch envelope: kind, rows, and the 2,000-row limit", () => {
  assert.deepEqual(checkEnvelope({ kind: "states", rows: [] }), { ok: true, kind: "states", rows: [] });
  assert.equal((checkEnvelope({ kind: "nope", rows: [] }) as { status: number }).status, 400);
  assert.equal((checkEnvelope({ kind: "states" }) as { status: number }).status, 400);
  assert.equal((checkEnvelope([]) as { status: number }).status, 400);
  assert.equal((checkEnvelope({ kind: "states", rows: [], x: 1 }) as { status: number }).status, 400);
  assert.equal((checkEnvelope({ kind: "states", rows: new Array(2001).fill({}) }) as { status: number }).status, 413);
});

test("embeddings must have 384 dimensions", () => {
  ok("chunks", { order_url: url, page: 1, text: "synthetic", embedding: new Array(384).fill(0.01) });
  no("chunks", { order_url: url, page: 1, text: "synthetic", embedding: [0.1, 0.2] }, /must have 384 numbers/);
});
