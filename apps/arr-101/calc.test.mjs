// node --test apps/arr-101/calc.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import { SAMPLE, compute } from "./calc.js";

const near = (a, b, tol = 0.005) => assert.ok(Math.abs(a - b) <= tol, `${a} is not ${b}`);

test("the sample utility: 150 consumers of every type", () => {
  const r = compute(SAMPLE);
  assert.equal(r.consumers, 150);
  assert.equal(r.sales, 1218);
  assert.equal(r.shareTotal, 100);
});

test("the sample ARR, worked by hand", () => {
  const r = compute(SAMPLE);
  near(r.atPeriphery, 1218 / 0.92, 1e-9);
  near(r.purchase, 1218 / 0.92 / 0.965, 1e-9);
  near(r.revenue, 81.426 + 21.888, 1e-9); // energy + fixed, category by category
  near(r.om, 9.45 + 3.15 + 5, 1e-9);
  near(r.depreciation, 10.45, 1e-9); // (200 + 218) / 2 × 5%
  near(r.interest, ((80 + 80 + 12.6 - 10.45) / 2) * 0.1, 1e-9);
  near(r.roe, ((60 + 65.4) / 2) * 0.15, 1e-9);
  near(r.arr, r.lines.reduce((a, l) => a + l[1], 0), 1e-9);
  near(r.gap, r.arr - r.revenue, 1e-9);
  near(r.acos, (r.arr * 100) / 1218, 1e-9);
  near(r.arr, 110.19, 0.01); // 63.88 + 17.60 + 10.45 + 8.11 + 9.41 + 0.70 + 0.52 + 1.03 − 1.50
});

test("a negative working capital requirement is nil or netted, as chosen", () => {
  const big = { ...SAMPLE, securityDeposit: 50 };
  assert.equal(compute(big).wcInterest, 0);
  assert.ok(compute({ ...big, negativeWcIsNil: false }).wcInterest < 0);
});

test("blank or bad inputs do not break the arithmetic", () => {
  const r = compute({ ...SAMPLE, distLossPct: "", loanRatePct: "x" });
  assert.ok(Number.isFinite(r.arr));
});
