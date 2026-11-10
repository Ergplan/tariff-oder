// node --test apps/arr-101/formats.test.mjs — the sample's formats agree with the working and with each other
import assert from "node:assert/strict";
import test from "node:test";
import { SAMPLE, compute } from "./calc.js";
import { buildFormats, KINDS } from "./formats-sample.js";

const near = (a, b, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} is not ${b}`);
const r = compute(SAMPLE);
const F = buildFormats(SAMPLE, r);
const g = (code) => F.find((f) => f.code === code).tables;
const row = (t, label) => t.rows.find((x) => x[0] === label);

test("every kind of format, each in a step, every number finite", () => {
  assert.equal(F.length, KINDS);
  assert.equal(new Set(F.map((f) => f.code)).size, KINDS);
  for (const f of F)
    for (const t of f.tables)
      for (const x of t.rows) {
        assert.equal(x.length, t.head.length, f.code);
        x.forEach((v, i) => t.dp[i] != null && assert.ok(Number.isFinite(Number(v)), `${f.code} ${x[0]}`));
      }
});

test("the formats agree with the working", () => {
  near(row(g("ARR")[0], "Aggregate Revenue Requirement")[1], r.arr);
  near(g("ESR3_Curr Tariff")[0].foot.at(-1), r.revenue);
  near(g("ESR4_Prop Tariff")[0].foot.at(-1), r.arr + SAMPLE.gapBroughtForward); // the proposed tariff meets the ARR
  near(g("ESR5_BD&Rev")[0].foot[1], 150);
  near(g("F1_PP_Annual")[0].foot[3], r.powerPurchase);
  near(g("F3_PP_Monthly")[0].foot.at(-2), r.purchase);
  near(g("PPC")[0].foot[5], r.powerPurchase);
  near(row(g("Energy Balance")[0], "Energy purchased")[2], r.purchase);
  near(row(g("F25_IOL")[0], "Interest on loan")[1], r.interest);
  near(row(g("F26_ROE")[0], "Return on equity")[1], r.roe);
  near(row(g("F27_Work Cap")[0], "Interest on working capital")[1], r.wcInterest);
  near(g("F24_Dep")[0].rows[0][6], r.depreciation);
});

test("the formats agree with each other", () => {
  const [assets, liab] = g("BS2");
  near(assets.foot[1], liab.foot[1]); // the balance sheet balances
  near(g("BS3")[0].rows.at(-1)[1], g("BS1")[0].rows.at(-1)[1]); // cash change = profit before tax
  const lt = g("P1A_DL HT-LT")[0];
  near(lt.rows[0][3] + lt.rows[1][3], lt.rows[2][3]); // HT + LT loss = total loss
  const esr2 = g("ESR2_Sales Forecast")[0];
  near(esr2.foot[5], r.sales); // the forecast reproduces the sales
  near(g("F21_O&M_EE (A)")[0].foot[1], r.employee);
  near(g("F23_O&M_A&G")[0].foot[1], r.ag);
  near(g("F28_NTI")[0].foot[1], r.nti);
  near(g("F32_Wheeling-Supply")[0].foot[1], r.arr);
});
