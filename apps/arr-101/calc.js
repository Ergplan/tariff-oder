// ARR 101 — the arithmetic of a small utility's Annual Revenue Requirement.
// Money in Rs lakh, energy in MWh, rates in Rs/kWh.  Every figure in SAMPLE is invented for a
// fictional utility; every norm is illustrative — a real filing uses its own Commission's regulations.

export const SAMPLE = {
  utility: "Sample Nagar Electricity Supply (fictional)",
  arrYear: "FY 2026-27",
  categories: [
    { name: "Domestic", consumers: 100, loadKw: 300, salesMwh: 180, energyRate: 5.5, fixedRate: 60 },
    { name: "Commercial", consumers: 25, loadKw: 150, salesMwh: 120, energyRate: 8.0, fixedRate: 150 },
    { name: "Small industry (LT)", consumers: 8, loadKw: 240, salesMwh: 288, energyRate: 7.2, fixedRate: 180 },
    { name: "Agriculture", consumers: 10, loadKw: 75, salesMwh: 60, energyRate: 2.5, fixedRate: 40 },
    { name: "Street light & water works", consumers: 3, loadKw: 60, salesMwh: 36, energyRate: 7.0, fixedRate: 120 },
    { name: "Institutions", consumers: 3, loadKw: 90, salesMwh: 54, energyRate: 7.5, fixedRate: 150 },
    { name: "Large industry (HT)", consumers: 1, loadKw: 250, salesMwh: 480, energyRate: 6.9, fixedRate: 300 },
  ],
  distLossPct: 8,
  txLossPct: 3.5,
  sources: [
    { name: "Long-term thermal", sharePct: 70, rate: 4.4 },
    { name: "Renewable", sharePct: 20, rate: 3.2 },
    { name: "Short-term / exchange", sharePct: 10, rate: 5.5 },
  ],
  txChargeRate: 0.4,
  employeeBase: 9,
  agBase: 3,
  escalationPct: 5,
  rmPctOfGfa: 2.5,
  openingGfa: 200,
  capitalisation: 20,
  consumerContribution: 2,
  depRatePct: 5,
  debtSharePct: 70,
  openingLoan: 80,
  loanRatePct: 10,
  openingEquity: 60,
  roePct: 15,
  receivableMonths: 1.5,
  securityDeposit: 8,
  wcRatePct: 11,
  negativeWcIsNil: true,
  sdInterestPct: 6.5,
  badDebtPct: 1,
  nonTariffIncome: 1.5,
  gapBroughtForward: 0,
};

const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

export function compute(inp) {
  const cats = inp.categories.map((c) => {
    const energyRev = (n(c.salesMwh) * n(c.energyRate)) / 100; // MWh × Rs/kWh ÷ 100 = Rs lakh
    const fixedRev = (n(c.loadKw) * n(c.fixedRate) * 12) / 1e5; // kW × Rs/kW/month × 12 ÷ 1,00,000
    const revenue = energyRev + fixedRev;
    return { ...c, energyRev, fixedRev, revenue, abr: n(c.salesMwh) ? (revenue * 100) / n(c.salesMwh) : 0 };
  });
  const consumers = sum(cats.map((c) => n(c.consumers)));
  const loadKw = sum(cats.map((c) => n(c.loadKw)));
  const sales = sum(cats.map((c) => n(c.salesMwh)));
  const revenue = sum(cats.map((c) => c.revenue));

  // energy balance: work backwards from sales
  const atPeriphery = sales / (1 - n(inp.distLossPct) / 100);
  const purchase = atPeriphery / (1 - n(inp.txLossPct) / 100);

  // power purchase
  const shareTotal = sum(inp.sources.map((s) => n(s.sharePct)));
  const sources = inp.sources.map((s) => {
    const mwh = (purchase * n(s.sharePct)) / 100;
    return { ...s, mwh, cost: (mwh * n(s.rate)) / 100 };
  });
  const energyCost = sum(sources.map((s) => s.cost));
  const txCharges = (atPeriphery * n(inp.txChargeRate)) / 100;
  const powerPurchase = energyCost + txCharges;

  // O&M
  const esc = 1 + n(inp.escalationPct) / 100;
  const employee = n(inp.employeeBase) * esc;
  const ag = n(inp.agBase) * esc;
  const rm = (n(inp.openingGfa) * n(inp.rmPctOfGfa)) / 100;
  const om = employee + ag + rm;

  // assets: additions net of what consumers paid for
  const netAddition = n(inp.capitalisation) - n(inp.consumerContribution);
  const closingGfa = n(inp.openingGfa) + netAddition;
  const avgGfa = (n(inp.openingGfa) + closingGfa) / 2;
  const depreciation = (avgGfa * n(inp.depRatePct)) / 100;

  // normative loan: repayment taken equal to depreciation
  const loanAddition = (netAddition * n(inp.debtSharePct)) / 100;
  const closingLoan = Math.max(0, n(inp.openingLoan) + loanAddition - depreciation);
  const avgLoan = (n(inp.openingLoan) + closingLoan) / 2;
  const interest = (avgLoan * n(inp.loanRatePct)) / 100;

  // equity
  const equityAddition = netAddition - loanAddition;
  const closingEquity = n(inp.openingEquity) + equityAddition;
  const avgEquity = (n(inp.openingEquity) + closingEquity) / 2;
  const roe = (avgEquity * n(inp.roePct)) / 100;

  // working capital
  const omOneMonth = om / 12;
  const receivables = (revenue * n(inp.receivableMonths)) / 12;
  const wcRequirementRaw = omOneMonth + receivables - n(inp.securityDeposit);
  const wcRequirement = inp.negativeWcIsNil ? Math.max(0, wcRequirementRaw) : wcRequirementRaw;
  const wcInterest = (wcRequirement * n(inp.wcRatePct)) / 100;

  const sdInterest = (n(inp.securityDeposit) * n(inp.sdInterestPct)) / 100;
  const badDebts = (revenue * n(inp.badDebtPct)) / 100;
  const nti = n(inp.nonTariffIncome);

  const lines = [
    ["Power purchase and transmission", powerPurchase],
    ["Operation & maintenance", om],
    ["Depreciation", depreciation],
    ["Interest on loan", interest],
    ["Return on equity", roe],
    ["Interest on working capital", wcInterest],
    ["Interest on security deposits", sdInterest],
    ["Provision for bad debts", badDebts],
    ["Less: non-tariff income", -nti],
  ];
  const arr = sum(lines.map((l) => l[1]));
  const gap = arr - revenue;
  const totalGap = gap + n(inp.gapBroughtForward);
  const acos = sales ? (arr * 100) / sales : 0;
  const abr = sales ? (revenue * 100) / sales : 0;
  const increasePct = revenue ? (totalGap / revenue) * 100 : 0;

  return {
    cats: cats.map((c) => ({ ...c, coveragePct: acos ? (c.abr / acos) * 100 : 0 })),
    consumers, loadKw, sales, revenue,
    atPeriphery, purchase, shareTotal, sources, energyCost, txCharges, powerPurchase,
    employee, ag, rm, om,
    netAddition, closingGfa, avgGfa, depreciation,
    loanAddition, closingLoan, avgLoan, interest,
    equityAddition, closingEquity, avgEquity, roe,
    omOneMonth, receivables, wcRequirementRaw, wcRequirement, wcInterest,
    sdInterest, badDebts, nti,
    lines, arr, gap, totalGap, acos, abr, increasePct,
  };
}
