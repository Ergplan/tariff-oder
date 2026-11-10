// The sample utility's formats: every kind of format in a UPERC petition (64 kinds; a real petition repeats some
// by year, 74 sheets in all), laid out as UPERC's and filled from the sample answers and the working.
//
// Most tables follow from the answers. Where a format needs figures the ten steps do not ask for (past years,
// months, the network, complaints), they come from EXTRA below: invented, fixed, and badged "illustrative".
// This guide works the ARR year only, so each format shows that year; a real filing adds true-up and APR columns.

export const EXTRA = {
  pastYears: ["FY 2018-19", "FY 2019-20", "FY 2020-21", "FY 2021-22", "FY 2022-23", "FY 2023-24", "FY 2024-25", "FY 2025-26"],
  salesGrowthPct: [6, 5, 4, 2, 3, 4, 5], // per category, in the order of the categories
  hoursOfSupply: [23.5, 23.5, 23.5, 18, 23.5, 23.5, 24],
  months: ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"],
  monthDays: [30, 31, 30, 31, 31, 30, 31, 30, 31, 31, 28, 31],
  monthShare: [0.08, 0.095, 0.1, 0.095, 0.09, 0.085, 0.08, 0.075, 0.075, 0.075, 0.075, 0.075],
  loadFactor: 0.55,
  htLossPct: 3,
  thermalPlf: 0.8,
  renewableCuf: 0.2,
  rpoPct: 33,
  employees: 6,
  employeeSplit: [["Salaries and wages", 0.7], ["Allowances", 0.15], ["Terminal benefits", 0.15]],
  agSplit: [["Rent, rates and taxes", 0.2], ["Legal and professional", 0.1], ["Communication", 0.15], ["Office expenses", 0.25], ["Other A&G", 0.3]],
  ntiSplit: [["Meter rent", 0.3], ["Delayed payment surcharge", 0.4], ["Other income", 0.3]],
  projects: [["New connections", 0.4], ["Network strengthening", 0.4], ["Metering", 0.2]],
  openingAccDep: 80,
  openingContribution: 10,
  cwip: 5,
  openingArrears: 6,
  collectionPct: 98.5,
  effectiveTaxPct: 25.17,
  allocWheelingPct: { "Power purchase and transmission": 0, "Operation & maintenance": 65, Depreciation: 90, "Interest on loan": 90, "Return on equity": 90, "Interest on working capital": 10, "Interest on security deposits": 0, "Provision for bad debts": 0, "Less: non-tariff income": 10 },
  network: [["HT lines (km)", 4.5], ["LT lines (km)", 12], ["Distribution transformers (nos)", 6], ["Substations (nos)", 1]],
  complaints: [["Billing", 14, 14], ["Supply interruption", 22, 21], ["Meter", 5, 4], ["Other", 3, 3]],
  land: [["Substation land", "0.2 acre", 3]],
};

const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const share = EXTRA.monthShare.map((x) => x / sum(EXTRA.monthShare));

// a table: head, per-column decimals (null = text), rows, optional total row (sums the numeric columns marked)
const T = (head, dp, rows, total) => ({ head, dp, rows, total });
const totals = (rows, flags) => flags.map((on, i) => (on ? sum(rows.map((r) => Number(r[i]) || 0)) : null));

export function buildFormats(s, r) {
  const cats = r.cats;
  const yArr = s.arrYear;
  const F = [];
  const add = (code, step, title, purpose, source, tables, note) => F.push({ code, step, title, purpose, source, tables, note });

  // ---------------------------------------------------------------- filing: the accounts, projected for the ARR year
  const income = r.revenue + r.nti;
  const expenses = [
    ["Power purchase and transmission", r.powerPurchase],
    ["Employee expenses", r.employee],
    ["A&G expenses", r.ag],
    ["R&M expenses", r.rm],
    ["Depreciation", r.depreciation],
    ["Interest on loan", r.interest],
    ["Interest on working capital", r.wcInterest],
    ["Interest on security deposits", r.sdInterest],
    ["Provision for bad debts", r.badDebts],
  ];
  const pbt = income - sum(expenses.map((e) => e[1]));
  add("BS1", "filing", "Profit & Loss Account", "The profit and loss account. A real filing gives three audited years; this is the ARR year, projected.", "answers", [
    T(["Particulars", `${yArr} (Rs lakh)`], [null, 2], [["Revenue from sale of power", r.revenue], ["Non-tariff income", r.nti], ["Total income", income], ...expenses, ["Total expenses", sum(expenses.map((e) => e[1]))], ["Profit before tax", pbt]]),
  ], "Profit before tax equals the return on equity less the year's gap: here it is " + (pbt >= 0 ? "a profit." : "a loss."));
  const nfa = r.closingGfa - (EXTRA.openingAccDep + r.depreciation);
  const liabilities = [["Equity (normative)", r.closingEquity], ["Normative loan", r.closingLoan], ["Consumer security deposits", Number(s.securityDeposit)]];
  const cash = sum(liabilities.map((x) => x[1])) - nfa - EXTRA.cwip - r.receivables;
  add("BS2", "filing", "Balance Sheet", "The balance sheet at the end of the year.", "illustrative", [
    T(["Assets", "Rs lakh"], [null, 2], [["Net fixed assets", nfa], ["Capital works in progress", EXTRA.cwip], ["Receivables", r.receivables], ["Cash and other current assets (balancing)", cash]], [0, 1]),
    T(["Equity and liabilities", "Rs lakh"], [null, 2], liabilities, [0, 1]),
  ], "A normative balance sheet: the cash line is what balances it. Accumulated depreciation and CWIP are illustrative.");
  add("BS3", "filing", "Cash Flow Statement", "Where the year's cash came from and went.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [
      ["Profit before tax", pbt],
      ["Add: depreciation (not a cash cost)", r.depreciation],
      ["Cash from operations", pbt + r.depreciation],
      ["Capital expenditure", -Number(s.capitalisation)],
      ["Consumer contributions received", Number(s.consumerContribution)],
      ["Cash used in investing", -Number(s.capitalisation) + Number(s.consumerContribution)],
      ["Loan drawn", r.loanAddition],
      ["Loan repaid (= depreciation)", -r.depreciation],
      ["Equity added", r.equityAddition],
      ["Cash from financing", r.loanAddition - r.depreciation + r.equityAddition],
      ["Net change in cash", pbt],
    ]),
  ]);

  // ---------------------------------------------------------------- energy balance and losses
  add("Energy Balance", "balance", "Energy Balance", "Sales, losses and energy purchased, on one page.", "answers", [
    T(["Particulars", "Unit", yArr], [null, null, 1], [
      ["Sales to consumers", "MWh", r.sales],
      ["Distribution loss", "%", Number(s.distLossPct)],
      ["Distribution loss", "MWh", r.atPeriphery - r.sales],
      ["Energy at the distribution boundary", "MWh", r.atPeriphery],
      ["Transmission loss", "%", Number(s.txLossPct)],
      ["Transmission loss", "MWh", r.purchase - r.atPeriphery],
      ["Energy purchased", "MWh", r.purchase],
    ]),
  ]);
  add("P1_DL", "balance", "Distribution Loss", "Distribution loss claimed against the trajectory.", "answers", [
    T(["Year", "Claimed (%)", "Trajectory (%)"], [null, 1, 1], [[yArr, Number(s.distLossPct), Number(s.distLossPct)]]),
  ], "The sample claims the trajectory's loss. A real filing lists past years too.");
  const ht = cats.filter((c) => /HT/.test(c.name));
  const htSales = sum(ht.map((c) => Number(c.salesMwh)));
  const htLoss = (r.atPeriphery * EXTRA.htLossPct) / 100;
  const ltIn = r.atPeriphery - htLoss - htSales;
  const ltSales = r.sales - htSales;
  add("P1A_DL HT-LT", "balance", "Distribution Losses in LT and HT system", "Losses separately on the high-voltage and low-voltage networks.", "illustrative", [
    T(["Level", "Energy in (MWh)", "Sales (MWh)", "Loss (MWh)", "Loss (%)"], [null, 1, 1, 1, 1], [
      ["HT", r.atPeriphery, htSales, htLoss, EXTRA.htLossPct],
      ["LT", ltIn, ltSales, ltIn - ltSales, ltIn ? ((ltIn - ltSales) / ltIn) * 100 : 0],
      ["Total", r.atPeriphery, r.sales, r.atPeriphery - r.sales, ((r.atPeriphery - r.sales) / r.atPeriphery) * 100],
    ]),
  ], `HT loss is an illustrative ${EXTRA.htLossPct}%; the LT loss is what remains of the total.`);

  // ---------------------------------------------------------------- sales
  const years = EXTRA.pastYears;
  const n = years.length - 1;
  add("ESR2_Sales Forecast", "sales", "Determination of CAGR of Energy Sales Forecast", "Past sales by category, the growth rate, and the forecast it gives.", "illustrative", [
    T(["Category", ...years.slice(-4), `${yArr} (forecast)`, "CAGR (%)"], [null, 1, 1, 1, 1, 1, 1], cats.map((c, i) => {
      const g = EXTRA.salesGrowthPct[i] / 100;
      const past = years.map((_, k) => Number(c.salesMwh) / (1 + g) ** (years.length - k));
      const cagr = ((past[n] / past[0]) ** (1 / n) - 1) * 100;
      return [c.name, ...past.slice(-4), past[n] * (1 + g), cagr];
    }), [0, 1, 1, 1, 1, 1, 0]),
  ], "Past sales are invented so that each category's seven-year growth gives this year's sales. UPERC Reg. 30.2 uses the seven-year CAGR.");
  add("ESR5_BD&Rev", "sales", "Consumer No., Connected Load, Sales & Revenue Details", "The billing determinants: consumers, load, sales and revenue by category.", "answers", [
    T(["Category", "Consumers", "Connected load (kW)", "Sales (MWh)", "Revenue (Rs lakh)"], [null, 0, 0, 1, 2], cats.map((c) => [c.name, Number(c.consumers), Number(c.loadKw), Number(c.salesMwh), c.revenue]), [0, 1, 1, 1, 1]),
  ]);
  add("ESR7_BD monthly", "sales", "BD monthly", "Sales by category, month by month.", "illustrative", [
    T(["Category", ...EXTRA.months, "Year"], [null, ...EXTRA.months.map(() => 1), 1], cats.map((c) => [c.name, ...share.map((m) => Number(c.salesMwh) * m), Number(c.salesMwh)]), [0, ...EXTRA.months.map(() => 1), 1]),
  ], "Monthly shares are illustrative.");
  add("P2_AVG Supply HRS", "sales", "Avg. No. of Hour Supply Per day", "Average hours of supply a day, by category.", "illustrative", [
    T(["Category", "Hours a day"], [null, 1], cats.map((c, i) => [c.name, EXTRA.hoursOfSupply[i]])),
  ]);
  const peakKw = (r.purchase * 1000) / (8760 * EXTRA.loadFactor);
  add("P9_Peak Demand", "sales", "Peak Demand in MW", "Peak demand from energy and load factor.", "illustrative", [
    T(["Particulars", "Value"], [null, 2], [["Energy purchased (MWh)", r.purchase], ["Load factor", EXTRA.loadFactor], ["Peak demand (kW) = MWh × 1000 ÷ (8760 × LF)", peakKw]]),
  ], `Load factor ${EXTRA.loadFactor} is illustrative. 1 MW = 1,000 kW.`);

  // ---------------------------------------------------------------- revenue
  const tariffRows = (k) => cats.map((c) => {
    const e = Number(c.energyRate) * k;
    const f = Number(c.fixedRate) * k;
    const er = (Number(c.salesMwh) * e) / 100;
    const fr = (Number(c.loadKw) * f * 12) / 1e5;
    return [c.name, Number(c.consumers), Number(c.loadKw), Number(c.salesMwh), e, f, fr, er, fr + er];
  });
  const tariffHead = ["Category", "Consumers", "Load (kW)", "Sales (MWh)", "Energy rate (Rs/kWh)", "Fixed rate (Rs/kW/month)", "Fixed charges (Rs lakh)", "Energy charges (Rs lakh)", "Revenue (Rs lakh)"];
  const tariffDp = [null, 0, 0, 1, 2, 2, 2, 2, 2];
  const tariffTot = [0, 1, 1, 1, 0, 0, 1, 1, 1];
  add("ESR1_OA", "revenue", "Revenue from Open Access Customers", "Revenue from consumers who buy power elsewhere and use your wires.", "none", [
    T(["Consumer", "Energy wheeled (MWh)", "Wheeling charges", "Cross-subsidy surcharge", "Additional surcharge", "Total (Rs lakh)"], [null, 1, 2, 2, 2, 2], [["None in this sample", 0, 0, 0, 0, 0]]),
  ], "The sample utility has no open access consumers.");
  add("ESR3_Curr Tariff", "revenue", "Revenue from Current Tariffs in Ensuing Year", "Next year's revenue if today's tariff stays. A real filing repeats this sheet for each year.", "answers", [T(tariffHead, tariffDp, tariffRows(1), tariffTot)]);
  const k = r.revenue ? 1 + r.totalGap / r.revenue : 1;
  add("ESR4_Prop Tariff", "revenue", "Revenue from Proposed Tariffs", "Revenue at the proposed tariff: here every rate moves by the same factor, so revenue meets the ARR and any gap brought forward.", "answers", [T(tariffHead, tariffDp, tariffRows(k), tariffTot)], `Every rate × ${k.toFixed(4)}. A real proposal sets each category's rate, moving each towards the average cost of supply.`);
  add("ESR4A_Prop Tariff Rate Sch.", "revenue", "Rate Schedule for Proposed Tariff", "Every rate asked for, against today's.", "answers", [
    T(["Category", "Energy now (Rs/kWh)", "Energy proposed", "Fixed now (Rs/kW/month)", "Fixed proposed", "Change (%)"], [null, 2, 2, 2, 2, 1], cats.map((c) => [c.name, Number(c.energyRate), Number(c.energyRate) * k, Number(c.fixedRate), Number(c.fixedRate) * k, (k - 1) * 100])),
  ]);
  add("ESR6_Subsidy", "revenue", "Revenue from Tariff Subsidy", "Subsidy from the State Government.", "none", [T(["Category", "Subsidy (Rs lakh)"], [null, 2], [["None in this sample", 0]])], "No subsidy in this sample.");

  // ---------------------------------------------------------------- power purchase
  const srcs = r.sources;
  add("F1_PP_Annual", "power", "Summary of Power Purchase from Own Stations and Other Sources", "Power purchase for the year, source by source.", "answers", [
    T(["Source", "Energy (MWh)", "Rate (Rs/kWh)", "Cost (Rs lakh)"], [null, 1, 2, 2], [...srcs.map((x) => [x.name, x.mwh, Number(x.rate), x.cost]), ["Transmission charges", 0, Number(s.txChargeRate), r.txCharges]], [0, 1, 0, 1]),
  ], "A real filing splits each source's cost into fixed (capacity) and energy charges.");
  add("F2_PP_Assump", "power", "Assumptions For Power Purchase", "The assumptions behind the projection, stated.", "answers", [
    T(["Assumption", "Value"], [null, null], [
      ...srcs.map((x) => [`${x.name}: share of purchase`, `${x.sharePct}%`]),
      ...srcs.map((x) => [`${x.name}: rate`, `Rs ${Number(x.rate).toFixed(2)}/kWh`]),
      ["Distribution loss", `${s.distLossPct}%`],
      ["Transmission loss", `${s.txLossPct}%`],
      ["Transmission charge", `Rs ${Number(s.txChargeRate).toFixed(2)}/kWh`],
    ]),
  ]);
  add("F3_PP_Monthly", "power", "Power Purchase & Monthly Appropriation of Power Purchase", "Power purchase month by month and source by source. A real filing repeats this sheet for each year.", "illustrative", [
    T(["Month", ...srcs.map((x) => `${x.name} (MWh)`), "Total (MWh)", "Cost (Rs lakh)"], [null, ...srcs.map(() => 1), 1, 2], EXTRA.months.map((m, i) => [m, ...srcs.map((x) => x.mwh * share[i]), r.purchase * share[i], r.energyCost * share[i]]), [0, ...srcs.map(() => 1), 1, 1]),
  ], "Monthly shares are illustrative; the year adds to F1.");
  const mod = [...srcs].sort((a, b) => Number(a.rate) - Number(b.rate));
  let cum = 0;
  add("F4_PP_MOD", "power", "Merit Order Despatch", "Sources ranked by cost; renewables up to the obligation are taken first whatever their cost.", "answers", [
    T(["Rank", "Source", "Rate (Rs/kWh)", "Energy (MWh)", "Cumulative (MWh)"], [null, null, 2, 1, 1], mod.map((x, i) => [String(i + 1), x.name, Number(x.rate), x.mwh, (cum += x.mwh)])),
  ]);
  const re = srcs.find((x) => /renew/i.test(x.name)) || srcs[1];
  add("F5_PP_Renew", "power", "PPA-wise renewable energy procured", "Renewable energy bought, agreement by agreement.", "illustrative", [
    T(["Agreement", "Capacity (kW)", "CUF", "Energy (MWh)", "Tariff (Rs/kWh)", "Cost (Rs lakh)"], [null, 0, 2, 1, 2, 2], [["Solar PPA (sample)", (re.mwh * 1000) / (8760 * EXTRA.renewableCuf), EXTRA.renewableCuf, re.mwh, Number(re.rate), re.cost]]),
  ], `Capacity from energy at an illustrative CUF of ${EXTRA.renewableCuf}.`);
  const rpoReq = (r.purchase * EXTRA.rpoPct) / 100;
  add("F6_PP6_RPO", "power", "Details of Renewable Purchase Obligation", "The renewable obligation: required against met.", "illustrative", [
    T(["Particulars", "Value"], [null, 1], [["Energy purchased (MWh)", r.purchase], ["Obligation (%)", EXTRA.rpoPct], ["Required (MWh)", rpoReq], ["Met: renewable purchased (MWh)", re.mwh], ["Shortfall (MWh)", Math.max(0, rpoReq - re.mwh)]]),
  ], `An illustrative ${EXTRA.rpoPct}% obligation. ${re.mwh < rpoReq ? "The sample falls short: raise the renewable share in step 4." : "The sample meets it."}`);
  const th = srcs[0];
  add("F7_PP_Comp Bid", "power", "Details for power procured via competitive bidding", "Power contracted through competitive bidding.", "illustrative", [
    T(["Contract", "Capacity (kW)", "PLF", "Energy (MWh)", "Levelised tariff (Rs/kWh)"], [null, 0, 2, 1, 2], [[`${th.name} (bid)`, (th.mwh * 1000) / (8760 * EXTRA.thermalPlf), EXTRA.thermalPlf, th.mwh, Number(th.rate)]]),
  ]);
  const st = srcs.find((x) => /short/i.test(x.name)) || srcs[2];
  add("F8_PP_Short Term", "power", "Information on short-term power procurement", "Short-term purchases: quantity, cost, rate.", "answers", [
    T(["Seller", "Energy (MWh)", "Cost (Rs lakh)", "Rate (Rs/kWh)"], [null, 1, 2, 2], [[st.name, st.mwh, st.cost, Number(st.rate)]]),
  ]);
  add("F9_PP_plan", "power", "Power Procurement (in MWs)", "Average power needed each month, by length of contract.", "illustrative", [
    T(["Month", "Long term (kW)", "Short term (kW)", "Total (kW)"], [null, 0, 0, 0], EXTRA.months.map((m, i) => {
      const h = EXTRA.monthDays[i] * 24;
      const lt = ((r.purchase - st.mwh) * share[i] * 1000) / h;
      const sh = (st.mwh * share[i] * 1000) / h;
      return [m, lt, sh, lt + sh];
    })),
  ], "Average kW in the month = monthly MWh × 1000 ÷ hours.");
  add("F10_PP_BST", "power", "Bulk Supply Tariff Details", "Bulk supply bought from another licensee.", "none", [T(["Particulars", "Value"], [null, 2], [["None in this sample", 0]])], "The sample buys no bulk supply.");
  add("PPC", "power", "Power purchase cost sheet", "Every source: energy, losses, charges and cost per unit received. A real filing repeats this sheet for each year.", "answers", [
    T(["Source", "Energy bought (MWh)", "Received after transmission loss (MWh)", "Energy cost (Rs lakh)", "Transmission (Rs lakh)", "Total (Rs lakh)", "Per unit received (Rs/kWh)"], [null, 1, 1, 2, 2, 2, 2], srcs.map((x) => {
      const got = x.mwh * (1 - Number(s.txLossPct) / 100);
      const tx = (got * Number(s.txChargeRate)) / 100;
      return [x.name, x.mwh, got, x.cost, tx, x.cost + tx, got ? ((x.cost + tx) * 100) / got : 0];
    }), [0, 1, 1, 1, 1, 1, 0]),
  ]);

  // ---------------------------------------------------------------- O&M
  const e = Number(s.escalationPct) / 100;
  const idx = ["FY 2022-23", "FY 2023-24", "FY 2024-25", "FY 2025-26"].map((y, i) => [y, 100 * (1 + e) ** i]);
  const idxTable = T(["Year", "Index", "Increase (%)"], [null, 2, 2], idx.map((x, i) => [x[0], x[1], i ? (x[1] / idx[i - 1][1] - 1) * 100 : 0]));
  add("F17_O&M_CPI", "om", "Consumer Price Inflation", "The index that escalates employee cost: the average of three years' increase.", "illustrative", [idxTable], `An index rising ${s.escalationPct}% a year, so the three-year average is ${s.escalationPct}%. UPERC uses CPI (Industrial Workers).`);
  add("F18_O&M_WPI", "om", "Wholesale Price Inflation", "The index that escalates A&G expenses.", "illustrative", [idxTable], "This sample uses one escalation for both; UPERC uses WPI for A&G.");
  const five = ["FY 2020-21", "FY 2021-22", "FY 2022-23", "FY 2023-24", "FY 2024-25"];
  const back = (base) => five.map((_, i) => base / (1 + e) ** (5 - i));
  const empPast = back(Number(s.employeeBase));
  const agPast = back(Number(s.agBase));
  add("F19_O&M_EE n AG base", "om", "Base year determination for Employee and A&G expenses", "The past five years and their average, the starting point of the norm.", "illustrative", [
    T(["Head", ...five, "Average"], [null, 2, 2, 2, 2, 2, 2], [["Employee", ...empPast, sum(empPast) / 5], ["A&G", ...agPast, sum(agPast) / 5]]),
  ], "Past years are invented by escalating backwards. This sample takes the base year as given; UPERC Reg. 33.6 builds it from the five-year average.");
  add("F19A-O&M Normative", "om", "O&M expenses on the norms", "Employee, A&G and R&M worked out on the norms.", "answers", [
    T(["Head", "Base", "Escalation / norm", yArr], [null, 2, null, 2], [
      ["Employee", Number(s.employeeBase), `× (1 + ${s.escalationPct}%)`, r.employee],
      ["A&G", Number(s.agBase), `× (1 + ${s.escalationPct}%)`, r.ag],
      ["R&M", Number(s.openingGfa), `× ${s.rmPctOfGfa}% of opening GFA`, r.rm],
    ], [0, 0, 0, 1]),
  ]);
  add("F20_O&M_EE", "om", "Employee Expenses", "Employees and what they cost.", "illustrative", [
    T(["Particulars", yArr], [null, 2], [["Employees (nos)", EXTRA.employees], ["Employee expenses (Rs lakh)", r.employee], ["Cost per employee (Rs lakh)", r.employee / EXTRA.employees]]),
  ]);
  add("F21_O&M_EE (A)", "om", "Component wise Details of Employee Expenses", "Employee expenses, component by component.", "illustrative", [
    T(["Component", "Rs lakh"], [null, 2], EXTRA.employeeSplit.map(([nm, w]) => [nm, r.employee * w]), [0, 1]),
  ], "The split is illustrative.");
  add("F22_O&M_R&M", "om", "R&M Expenses", "Repairs and maintenance on the norm.", "answers", [
    T(["Particulars", "Value"], [null, 2], [["Opening gross fixed assets (Rs lakh)", Number(s.openingGfa)], ["Norm (% of opening GFA)", Number(s.rmPctOfGfa)], ["R&M (Rs lakh)", r.rm]]),
  ]);
  add("F23_O&M_A&G", "om", "Componentwise Details of Administration & General Expenses", "A&G expenses, component by component.", "illustrative", [
    T(["Component", "Rs lakh"], [null, 2], EXTRA.agSplit.map(([nm, w]) => [nm, r.ag * w]), [0, 1]),
  ], "The split is illustrative.");

  // ---------------------------------------------------------------- capital
  const cap = Number(s.capitalisation);
  const cc = Number(s.consumerContribution);
  add("F11_CAP_Asset not in use", "capital", "Statement of Assets Not in Use", "Assets taken out of use.", "none", [T(["Asset", "Cost", "Written-down value"], [null, 2, 2], [["None in this sample", 0, 0]])]);
  add("F12_CAP_Cons Contri", "capital", "Consumer contributions and grants towards cost of capital assets", "What consumers paid towards assets: it earns no depreciation or return.", "illustrative", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening balance", EXTRA.openingContribution], ["Received in the year", cc], ["Closing balance", EXTRA.openingContribution + cc]]),
  ]);
  const proj = EXTRA.projects.map(([nm, w]) => [nm, cap * w, cc * w, (cap - cc) * w * (Number(s.debtSharePct) / 100), (cap - cc) * w * (1 - Number(s.debtSharePct) / 100)]);
  add("F13_CAP_Plan", "capital", "Investment Plan - Master", "Each scheme, its cost and how it is financed.", "illustrative", [
    T(["Scheme", "Cost (Rs lakh)", "Consumer contribution", "Loan", "Equity"], [null, 2, 2, 2, 2], proj, [0, 1, 1, 1, 1]),
  ], "The split between schemes is illustrative; the financing follows the debt share in step 6.");
  add("F14_CAP_Cap Cost", "capital", "Statement of Capital Cost", "Opening assets, additions, closing assets.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening gross fixed assets", Number(s.openingGfa)], ["Capitalised in the year", cap], ["Less: funded by consumers / grants", -cc], ["Closing gross fixed assets", r.closingGfa]]),
  ]);
  add("F15_CAP_CWIP", "capital", "Statement of Capital Works in Progress", "Spent but not yet in use, so not yet in the asset base.", "illustrative", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening CWIP", EXTRA.cwip], ["Spent in the year", cap], ["Capitalised", -cap], ["Closing CWIP", EXTRA.cwip]]),
  ]);
  add("F16_CAP_CAPEX & CAPITALISATION", "capital", "Capex and Capitalisation Details", "Spending and capitalisation by type of project.", "illustrative", [
    T(["Project type", "Capex (Rs lakh)", "Capitalisation (Rs lakh)"], [null, 2, 2], EXTRA.projects.map(([nm, w]) => [nm, cap * w, cap * w]), [0, 1, 1]),
  ]);
  add("F24_Dep", "capital", "Calculation of Depreciation Rate", "Gross assets and depreciation, by asset class.", "answers", [
    T(["Asset class", "Opening GFA", "Additions", "Closing GFA", "Average", "Rate (%)", "Depreciation", "Accumulated (closing)"], [null, 2, 2, 2, 2, 2, 2, 2], [["All assets (one blended class)", Number(s.openingGfa), r.netAddition, r.closingGfa, r.avgGfa, Number(s.depRatePct), r.depreciation, EXTRA.openingAccDep + r.depreciation]]),
  ], "UPERC requires each asset class at its own Annexure rate; this sample uses one blended class.");
  add("F25_IOL", "capital", "Interest on Normative Loan", "Opening, addition, repayment, average, rate, interest.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening normative loan", Number(s.openingLoan)], ["Addition", r.loanAddition], ["Repayment (= depreciation)", -r.depreciation], ["Closing normative loan", r.closingLoan], ["Average", r.avgLoan], ["Rate (%)", Number(s.loanRatePct)], ["Interest on loan", r.interest]]),
  ]);
  add("F26_ROE", "capital", "Return of Equity", "Opening, addition, average equity and the return.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening equity", Number(s.openingEquity)], ["Addition", r.equityAddition], ["Closing equity", r.closingEquity], ["Average", r.avgEquity], ["Rate (%)", Number(s.roePct)], ["Return on equity", r.roe]]),
  ]);
  const grossed = r.roe / (1 - EXTRA.effectiveTaxPct / 100);
  add("F29_Income Tax", "capital", "Income Tax Provisions", "Tax on the return on equity.", "illustrative", [
    T(["Particulars", "Value"], [null, 2], [["Return on equity (Rs lakh)", r.roe], ["Effective tax rate (%)", EXTRA.effectiveTaxPct], ["Return grossed up (Rs lakh)", grossed], ["Tax on return on equity (Rs lakh)", grossed - r.roe]]),
  ], "Shown for completeness: this sample's ARR leaves tax out (see the UPERC check in step 6). The tax rate is illustrative.");
  add("P4_Phy Stat", "capital", "Details of Physical statistics of the network", "The network in numbers.", "illustrative", [T(["Item", "At year end"], [null, 1], EXTRA.network)]);
  add("P11_Land", "capital", "Details of Land Assets", "Land owned. Land is not depreciated.", "illustrative", [T(["Parcel", "Area", "Value (Rs lakh)"], [null, null, 2], EXTRA.land)]);

  // ---------------------------------------------------------------- working capital and the smaller items
  add("F27_Work Cap", "wc", "Working Capital Requirements", "The working capital requirement and the interest on it.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [["O&M for one month", r.omOneMonth], [`Receivables (${s.receivableMonths} months of revenue)`, r.receivables], ["Less: security deposits", -Number(s.securityDeposit)], ["Requirement", r.wcRequirementRaw], ["Requirement allowed", r.wcRequirement], ["Rate (%)", Number(s.wcRatePct)], ["Interest on working capital", r.wcInterest]]),
  ], "UPERC Reg. 25.1 also counts maintenance spares; this sample does not.");
  add("F28_NTI", "wc", "Details of Non-tariff Income", "Non-tariff income, item by item.", "illustrative", [T(["Item", "Rs lakh"], [null, 2], EXTRA.ntiSplit.map(([nm, w]) => [nm, r.nti * w]), [0, 1])], "The split is illustrative.");
  add("F30_CSD monthly", "wc", "Monthly details of Consumer Security Deposit", "Deposits held, month by month, and the interest.", "illustrative", [
    T(["Month", "Deposit held (Rs lakh)", "Interest (Rs lakh)"], [null, 2, 2], EXTRA.months.map((m) => [m, Number(s.securityDeposit), (Number(s.securityDeposit) * Number(s.sdInterestPct)) / 1200]), [0, 0, 1]),
  ], "Deposits held flat through the year.");
  add("F30A_CSD", "wc", "Consumer Security Deposit", "Deposits held, and the interest paid on them.", "answers", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening", Number(s.securityDeposit)], ["Received less refunded", 0], ["Closing", Number(s.securityDeposit)], ["Rate (%)", Number(s.sdInterestPct)], ["Interest", r.sdInterest]]),
  ]);
  add("F31_Recievables", "wc", "Statement of Receivables", "What consumers owe at the year's end.", "answers", [
    T(["Particulars", "Value"], [null, 2], [["Revenue (Rs lakh)", r.revenue], ["Months of receivables", Number(s.receivableMonths)], ["Receivables (Rs lakh)", r.receivables]]),
  ]);
  add("P3_Bad Debts", "wc", "Bad Debts, Debits, Write-offs and any other items", "Bad debts and the provision.", "answers", [
    T(["Particulars", "Value"], [null, 2], [["Revenue (Rs lakh)", r.revenue], ["Provision (%)", Number(s.badDebtPct)], ["Provision (Rs lakh)", r.badDebts]]),
  ]);
  const collected = (r.revenue * EXTRA.collectionPct) / 100;
  add("P5_Arrear", "wc", "Analysis of Revenue Arrears", "Arrears: opening, billed, collected, closing.", "illustrative", [
    T(["Particulars", "Rs lakh"], [null, 2], [["Opening arrears", EXTRA.openingArrears], ["Billed", r.revenue], ["Collected", -collected], ["Closing arrears", EXTRA.openingArrears + r.revenue - collected]]),
  ], `An illustrative collection efficiency of ${EXTRA.collectionPct}%.`);

  // ---------------------------------------------------------------- the ARR and what follows from it
  add("ARR", "arr", "Annual Revenue Requirement", "The summary of the petition: every cost, revenue and the gap.", "answers", [
    T(["Particulars", `${yArr} (Rs lakh)`], [null, 2], [...r.lines, ["Aggregate Revenue Requirement", r.arr], ["Revenue at existing tariff", r.revenue], ["Gap for the year", r.gap], ["Gap brought forward", Number(s.gapBroughtForward)], ["Total gap", r.totalGap]]),
  ]);
  add("ARR snapshot", "arr", "ARR Snapshot", "The ARR year at a glance.", "answers", [
    T(["Item", "Unit", yArr], [null, null, 2], [["Sales", "MWh", r.sales], ["Energy purchased", "MWh", r.purchase], ["Distribution loss", "%", Number(s.distLossPct)], ["ARR", "Rs lakh", r.arr], ["Revenue at existing tariff", "Rs lakh", r.revenue], ["Average cost of supply", "Rs/kWh", r.acos], ["Average billing rate", "Rs/kWh", r.abr]]),
  ]);
  add("True up-snapshot", "arr", "True-Up Snapshot", "The closed year: approved against actual, head by head.", "none", [T(["Item", "Approved", "Actual"], [null, 2, 2], [["Not in this sample", 0, 0]])], "This guide works the ARR year only. A real filing compares the true-up year's actuals with the order's approval.");
  add("APR Snapshot", "arr", "APR Snapshot", "The current year: approved against the revised estimate.", "none", [T(["Item", "Approved", "Estimate"], [null, 2, 2], [["Not in this sample", 0, 0]])], "This guide works the ARR year only.");
  const alloc = r.lines.map(([nm, v]) => {
    const w = (EXTRA.allocWheelingPct[nm] ?? 0) / 100;
    return [nm, v, w * 100, v * w, v * (1 - w)];
  });
  add("F32_Wheeling-Supply", "arr", "Allocation of Wheeling & Retail Supply", "The ARR split between the wires business and the supply business.", "illustrative", [
    T(["ARR item", "Total (Rs lakh)", "Wheeling (%)", "Wheeling (Rs lakh)", "Supply (Rs lakh)"], [null, 2, 0, 2, 2], alloc, [0, 1, 0, 1, 1]),
  ], "The allocation percentages are illustrative; the Commission's matrix applies.");
  const wheelingArr = sum(alloc.map((a) => a[3]));
  const hv = ht[0] || cats[cats.length - 1];
  const Tt = hv.abr;
  const C = r.purchase ? (r.energyCost * 100) / r.purchase : 0;
  const L = (Number(s.txLossPct) + EXTRA.htLossPct) / 100;
  const D = r.sales ? (wheelingArr * 100) / r.sales : 0;
  const S = Tt - (C / (1 - L) + D);
  const capCss = 0.2 * r.acos;
  add("F33_CSS", "arr", "Details of Cross Subsidy Surcharge", "The surcharge an open access consumer pays: S = T − [C ÷ (1 − L) + D + R].", "illustrative", [
    T(["Term", "Rs/kWh"], [null, 2], [
      [`T: tariff of ${hv.name}`, Tt],
      ["C: power purchase cost per unit", C],
      ["L: losses up to HT (fraction)", L],
      ["D: wheeling charge per unit", D],
      ["R: regulatory assets per unit", 0],
      ["S computed", S],
      ["Cap: 20% of average cost of supply", capCss],
      ["Cross-subsidy surcharge", Math.max(0, Math.min(S, capCss))],
    ]),
  ], "Losses and the wheeling share are illustrative. UPERC Reg. 37 caps the surcharge at 20% of the average cost of supply.");

  // ---------------------------------------------------------------- performance
  add("P6_Cons Complaints", "checks", "Consumer Complaint", "Complaints received and resolved.", "illustrative", [
    T(["Type", "Received", "Resolved"], [null, 0, 0], EXTRA.complaints, [0, 1, 1]),
  ]);
  add("P7_Trans Failure", "checks", "Failure of Transformers", "Transformer failures as a share of those installed.", "illustrative", [
    T(["Particulars", "Value"], [null, 0], [["Transformers installed", 6], ["Failed in the year", 0], ["Failure rate (%)", 0]]),
  ]);
  add("P8_Elec Accidents", "checks", "Electrical Accidents", "Accidents, fatal and non-fatal.", "illustrative", [
    T(["Type", "Human", "Animal"], [null, 0, 0], [["Fatal", 0, 0], ["Non-fatal", 0, 0]]),
  ]);
  add("P10_Pending Cases", "checks", "Details of Pending Cases as on date of filing", "Court and regulatory cases pending.", "none", [T(["Case", "Forum", "Status"], [null, null, null], [["None in this sample", "", ""]])]);

  // totals rows
  for (const f of F)
    for (const t of f.tables)
      if (t.total) t.foot = ["Total", ...totals(t.rows, t.total).slice(1)];
  return F;
}

export const KINDS = 64; // kinds of format in a UPERC petition: one each above
