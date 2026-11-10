// The ten steps of ARR 101: plain words, the questions to answer (with the sample utility's answers as
// defaults), the live working, and what to watch out for.  The "watch out" notes are lessons from checking
// real petitions and tariff orders format by format; they name no licensee.

const f2 = (v) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f1 = (v) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const f0 = (v) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const table = (head, rows, foot) =>
  `<div class="scroll"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${c}</td>`).join("")}</tr>`)
    .join("")}</tbody>${foot ? `<tfoot><tr>${foot.map((c, i) => `<td class="${i ? "num" : ""}">${c}</td>`).join("")}</tr></tfoot>` : ""}</table></div>`;

const calc = (label, formula, value, unit) =>
  `<div class="calc"><div><b>${label}</b><span>${formula}</span></div><strong>${value} <small>${unit}</small></strong></div>`;

// a question: {q, path, unit, kind?: "text"|"check", help?}
export const STEPS = [
  {
    id: "filing",
    title: "Know what you are filing",
    plain:
      "Every year a distribution licensee tells its Commission how much money it needs to run the business and how much its tariffs will bring in. One petition usually covers three years at once.",
    points: [
      ["True-up", "the year that has closed. You file what actually happened, from audited accounts, against what the Commission had approved."],
      ["Annual Performance Review (APR)", "the year in progress. Part actual, part estimate."],
      ["Aggregate Revenue Requirement (ARR)", "the coming year. A projection. This is the year this guide works through."],
    ],
    questions: [
      { q: "What is the utility called?", path: "utility", kind: "text" },
      { q: "Which year is the ARR for?", path: "arrYear", kind: "text", help: "The true-up year is two years before it, the APR year one year before." },
    ],
    working: (r, s) =>
      `<p>You will file three things for <b>${esc(s.utility)}</b>, ${esc(s.arrYear)}:</p>
       <ol><li><b>The formats</b>: the Commission's spreadsheet of tables (sales, power purchase, assets, the ARR summary and more).</li>
       <li><b>The narrative</b>: the written petition, which restates the formats' figures and explains them.</li>
       <li><b>Supporting documents</b>: audited accounts, power purchase bills, loan statements, the asset register.</li></ol>`,
    watch: [
      "Find your Commission's current tariff regulations and its prescribed formats first. Every norm in this guide is illustrative; yours come from those regulations.",
      "Keep last year's tariff order open. The approved figures you quote must be the order's, copied, never recalculated.",
    ],
  },
  {
    id: "sales",
    title: "Count your consumers and sales",
    plain:
      "Everything starts from who you supply and how much they use. List each consumer category with its number of consumers, connected load and the energy you expect to sell in the year.",
    questions: [],
    grid: {
      cols: [
        ["consumers", "Consumers", 1],
        ["loadKw", "Connected load (kW)", 1],
        ["salesMwh", "Sales (MWh)", 1],
      ],
    },
    working: (r) =>
      `${calc("Total consumers", "sum of all categories", f0(r.consumers), "")}
       ${calc("Total connected load", "sum of all categories", f0(r.loadKw), "kW")}
       ${calc("Total sales", "sum of all categories", f1(r.sales), "MWh")}`,
    watch: [
      "Project sales from your own past years, category by category. Many regulations ask for a compound growth rate over several years; say which years you used.",
      "Use the same sales figure everywhere. In real petitions the sales total often differs between the sales format, the revenue format and the ARR summary.",
      "1 MU (million units) = 1,000 MWh. Large utilities file in MU and Rs crore; state your units on every table.",
    ],
  },
  {
    id: "balance",
    title: "Work out how much energy to buy",
    plain:
      "Some energy is lost in your own wires, and some in the transmission system before it reaches you. So you must buy more than you sell. Work backwards from sales.",
    questions: [
      { q: "What distribution loss do you expect?", path: "distLossPct", unit: "%", help: "Commissions set a loss target (a trajectory). If your actual loss is higher, the extra purchase cost is usually yours to bear." },
      { q: "What is the transmission loss up to your boundary?", path: "txLossPct", unit: "%" },
    ],
    working: (r, s) =>
      `${calc("Energy needed at your boundary", `${f1(r.sales)} ÷ (1 − ${s.distLossPct}%)`, f1(r.atPeriphery), "MWh")}
       ${calc("Energy to purchase", `${f1(r.atPeriphery)} ÷ (1 − ${s.txLossPct}%)`, f1(r.purchase), "MWh")}`,
    watch: [
      "Divide by (1 − loss). Do not multiply sales by (1 + loss): that understates the purchase.",
      "Loss = 1 − sales ÷ input. State it once and make sure the energy balance, the loss format and the ARR summary all show the same figure.",
    ],
  },
  {
    id: "power",
    title: "Cost your power purchase",
    plain:
      "Power purchase is usually the largest cost by far. List each source, how much you will buy from it and at what rate. Add the charges you pay to use the transmission network.",
    questions: [
      { q: "Transmission charges per unit received", path: "txChargeRate", unit: "Rs/kWh" },
    ],
    sources: true,
    working: (r) =>
      `${r.shareTotal !== 100 ? `<p class="warn">The shares add up to ${f1(r.shareTotal)}%, not 100%.</p>` : ""}
       ${table(
         ["Source", "Energy (MWh)", "Rate (Rs/kWh)", "Cost (Rs lakh)"],
         r.sources.map((x) => [esc(x.name), f1(x.mwh), f2(x.rate), f2(x.cost)]),
         ["Energy cost", f1(r.purchase), f2(r.purchase ? (r.energyCost * 100) / r.purchase : 0), f2(r.energyCost)],
       )}
       ${calc("Transmission charges", `${f1(r.atPeriphery)} MWh × rate ÷ 100`, f2(r.txCharges), "Rs lakh")}
       ${calc("Power purchase and transmission", "energy cost + transmission", f2(r.powerPurchase), "Rs lakh")}`,
    watch: [
      "MWh × Rs/kWh ÷ 100 = Rs lakh. Unit slips (lakh against crore, kWh against MU) are the most common error in filed tables.",
      "A real filing separates fixed (capacity) charges from energy charges for each source, and shows the months.",
      "Check your renewable purchase obligation: a minimum share of your energy must come from renewable sources.",
      "The average rate is a result (cost ÷ energy). Never type an average and back the cost out of it.",
    ],
  },
  {
    id: "om",
    title: "Estimate operation and maintenance",
    plain:
      "O&M has three parts: employee cost, administration and general (A&G) expenses, and repairs and maintenance (R&M). Regulations usually fix how each is projected, so you cannot simply claim what you plan to spend.",
    questions: [
      { q: "Employee cost in the base year", path: "employeeBase", unit: "Rs lakh" },
      { q: "A&G expenses in the base year", path: "agBase", unit: "Rs lakh" },
      { q: "Escalation allowed on both", path: "escalationPct", unit: "%", help: "Usually tied to inflation indices (CPI and WPI)." },
      { q: "R&M as a share of opening gross fixed assets", path: "rmPctOfGfa", unit: "%" },
    ],
    working: (r, s) =>
      `${calc("Employee cost", `${f2(s.employeeBase)} × (1 + ${s.escalationPct}%)`, f2(r.employee), "Rs lakh")}
       ${calc("A&G expenses", `${f2(s.agBase)} × (1 + ${s.escalationPct}%)`, f2(r.ag), "Rs lakh")}
       ${calc("R&M", `${f2(s.openingGfa)} × ${s.rmPctOfGfa}%`, f2(r.rm), "Rs lakh")}
       ${calc("Total O&M", "employee + A&G + R&M", f2(r.om), "Rs lakh")}`,
    watch: [
      "Read how your regulations define the base year (often an average of several past years) and which index applies to which head.",
      "Show expenses net of what you capitalised. Employee cost charged to projects belongs in the asset, not in O&M.",
    ],
  },
  {
    id: "capital",
    title: "Assets, depreciation, loan and equity",
    plain:
      "Your network is paid for by loans and by the owners' equity. The ARR recovers the assets' cost over their life (depreciation), the interest on the loans, and a return on the equity.",
    questions: [
      { q: "Gross fixed assets at the start of the year", path: "openingGfa", unit: "Rs lakh" },
      { q: "Assets to be put to use in the year (capitalisation)", path: "capitalisation", unit: "Rs lakh" },
      { q: "Of which paid for by consumers or grants", path: "consumerContribution", unit: "Rs lakh", help: "You earn no depreciation, interest or return on assets consumers paid for." },
      { q: "Depreciation rate", path: "depRatePct", unit: "%", help: "Regulations give a rate per asset class; this is a blended rate." },
      { q: "Share of new assets funded by loan", path: "debtSharePct", unit: "%", help: "Commonly 70 : 30 debt to equity." },
      { q: "Loan outstanding at the start of the year", path: "openingLoan", unit: "Rs lakh" },
      { q: "Interest rate on the loan", path: "loanRatePct", unit: "%" },
      { q: "Equity at the start of the year", path: "openingEquity", unit: "Rs lakh" },
      { q: "Rate of return on equity", path: "roePct", unit: "%" },
    ],
    working: (r, s) =>
      `${calc("Net addition to assets", `${f2(s.capitalisation)} − ${f2(s.consumerContribution)}`, f2(r.netAddition), "Rs lakh")}
       ${calc("Depreciation", `average assets ${f2(r.avgGfa)} × ${s.depRatePct}%`, f2(r.depreciation), "Rs lakh")}
       ${table(
         ["", "Loan", "Equity"],
         [
           ["Opening", f2(s.openingLoan), f2(s.openingEquity)],
           ["Addition", f2(r.loanAddition), f2(r.equityAddition)],
           ["Repayment (= depreciation)", f2(r.depreciation), "—"],
           ["Closing", f2(r.closingLoan), f2(r.closingEquity)],
           ["Average", f2(r.avgLoan), f2(r.avgEquity)],
         ],
       )}
       ${calc("Interest on loan", `${f2(r.avgLoan)} × ${s.loanRatePct}%`, f2(r.interest), "Rs lakh")}
       ${calc("Return on equity", `${f2(r.avgEquity)} × ${s.roePct}%`, f2(r.roe), "Rs lakh")}`,
    watch: [
      "Capital expenditure is not capitalisation. Only assets put to use in the year enter the asset base; work in progress does not.",
      "The loan here is a notional (normative) one: the year's repayment is taken equal to depreciation, whatever your bank schedule says.",
      "Commissions differ on the equity base: some allow return on the opening balance, some on the average, some on half of the year's addition. Check yours.",
      "Stop depreciating an asset at its limit (often 90% of cost). Retired assets come out of assets, loan and equity alike.",
    ],
  },
  {
    id: "wc",
    title: "Working capital and the smaller items",
    plain:
      "You pay for power before consumers pay you, so you need working capital, and the ARR allows interest on a normative amount. A few smaller items complete the cost side, and income other than tariffs is taken off.",
    questions: [
      { q: "Receivables allowed, in months of revenue", path: "receivableMonths", unit: "months" },
      { q: "Consumer security deposits you hold", path: "securityDeposit", unit: "Rs lakh", help: "Deposits already fund part of your working capital, so they are deducted." },
      { q: "Interest rate on working capital", path: "wcRatePct", unit: "%" },
      { q: "If the requirement is negative, treat it as nil", path: "negativeWcIsNil", kind: "check" },
      { q: "Interest you pay consumers on their deposits", path: "sdInterestPct", unit: "%" },
      { q: "Provision for bad debts, as a share of revenue", path: "badDebtPct", unit: "%" },
      { q: "Non-tariff income (meter rent, late fees, interest earned)", path: "nonTariffIncome", unit: "Rs lakh" },
    ],
    working: (r, s) =>
      `${calc("One month of O&M", `${f2(r.om)} ÷ 12`, f2(r.omOneMonth), "Rs lakh")}
       ${calc("Receivables", `revenue ${f2(r.revenue)} × ${s.receivableMonths} ÷ 12`, f2(r.receivables), "Rs lakh")}
       ${calc("Working capital requirement", `O&M month + receivables − deposits ${f2(s.securityDeposit)}`, f2(r.wcRequirementRaw), "Rs lakh")}
       ${r.wcRequirementRaw < 0 ? `<p class="warn">The requirement is negative: ${s.negativeWcIsNil ? "taken as nil" : "the negative interest reduces the ARR"}.</p>` : ""}
       ${calc("Interest on working capital", `${f2(r.wcRequirement)} × ${s.wcRatePct}%`, f2(r.wcInterest), "Rs lakh")}
       ${calc("Interest on security deposits", `${f2(s.securityDeposit)} × ${s.sdInterestPct}%`, f2(r.sdInterest), "Rs lakh")}
       ${calc("Provision for bad debts", `${f2(r.revenue)} × ${s.badDebtPct}%`, f2(r.badDebts), "Rs lakh")}
       ${calc("Non-tariff income", "deducted from the ARR", `(${f2(r.nti)})`, "Rs lakh")}`,
    watch: [
      "The working capital formula differs more between Commissions than any other head: which items count, how many months, what is deducted, which interest rate. Copy yours exactly.",
      "A negative requirement is handled differently too: some Commissions approve nil, others net the negative interest against the ARR.",
      "Working capital and bad debts depend on revenue, and revenue depends on the ARR. Say which revenue you used (existing tariff here).",
    ],
  },
  {
    id: "revenue",
    title: "Revenue at the existing tariff",
    plain:
      "Now the other side: what will today's tariff bring in next year? Apply each category's energy charge to its sales and its fixed charge to its load.",
    questions: [],
    grid: {
      cols: [
        ["energyRate", "Energy charge (Rs/kWh)", 0.1],
        ["fixedRate", "Fixed charge (Rs/kW/month)", 1],
      ],
    },
    working: (r) =>
      table(
        ["Category", "Energy (Rs lakh)", "Fixed (Rs lakh)", "Revenue (Rs lakh)", "Average (Rs/kWh)"],
        r.cats.map((c) => [esc(c.name), f2(c.energyRev), f2(c.fixedRev), f2(c.revenue), f2(c.abr)]),
        ["Total", "", "", f2(r.revenue), f2(r.abr)],
      ),
    watch: [
      "Tariff rates are inputs. Enter the rate from the tariff order; never work a rate out as revenue ÷ units.",
      "Real tariffs have slabs, minimum charges, rebates and surcharges. Compute revenue slab by slab from your billing data.",
      "Keep revenue from open access, wheeling and other business separate from tariff revenue.",
    ],
  },
  {
    id: "arr",
    title: "Put the ARR together and find the gap",
    plain:
      "Add the costs, take off non-tariff income, and you have the Aggregate Revenue Requirement. Compare it with revenue at the existing tariff: the difference is the gap your tariff proposal must close.",
    questions: [
      { q: "Gap (or surplus, as a negative) brought forward from earlier years, with carrying cost", path: "gapBroughtForward", unit: "Rs lakh", help: "From the true-up and APR. A surplus goes in as a negative number." },
    ],
    working: (r, s) =>
      `${table(["ARR for " + esc(s.arrYear), "Rs lakh"], r.lines.map((l) => [l[0], l[1] < 0 ? `(${f2(-l[1])})` : f2(l[1])]), ["Aggregate Revenue Requirement", f2(r.arr)])}
       ${calc("Revenue at existing tariff", "from step 8", f2(r.revenue), "Rs lakh")}
       ${calc(r.gap >= 0 ? "Revenue gap for the year" : "Revenue surplus for the year", "ARR − revenue", f2(r.gap), "Rs lakh")}
       ${calc("Total gap to recover", "year's gap + brought forward", f2(r.totalGap), "Rs lakh")}
       ${calc("Average cost of supply", `ARR ÷ sales ${f1(r.sales)} MWh`, f2(r.acos), "Rs/kWh")}
       ${calc("Average billing rate", "revenue ÷ sales", f2(r.abr), "Rs/kWh")}
       ${calc("Tariff change needed", "total gap ÷ revenue", f1(r.increasePct), "%")}
       <h4>Who pays more or less than cost?</h4>
       ${table(
         ["Category", "Average rate (Rs/kWh)", "As % of average cost"],
         r.cats.map((c) => [esc(c.name), f2(c.abr), `${f0(c.coveragePct)}%`]),
       )}
       <p class="note">Tariff policy asks that each category's average rate move towards a band around the average cost of supply (commonly within 20% either side).</p>`,
    watch: [
      "State the sign convention once: is a positive figure a gap or a surplus? Narratives often print a gap positive where the formats hold it negative.",
      "A gap carried from earlier years earns carrying cost, at the rate and for the period your regulations give. Show the working.",
      "Every row of the summary must be traceable to the format that builds it up, and the totals must add up as printed.",
    ],
  },
  {
    id: "checks",
    title: "Check before you file",
    plain:
      "Most questions a Commission asks back are about figures that do not agree with each other. Run these checks before you sign.",
    questions: [],
    checklist: [
      "Every total equals the sum of its rows, in every table.",
      "The same figure is the same everywhere: formats, ARR summary, narrative tables and the executive summary.",
      "Approved and trued-up figures are copied from the Commission's order, with the order and page noted.",
      "Every actual figure ties to the audited accounts, and differences are explained.",
      "Tariff rates are the order's rates; nothing is backed out of revenue ÷ units.",
      "Units are stated on every table (Rs lakh or crore; MWh or MU) and conversions are right.",
      "Loss, sales and energy purchased agree between the energy balance and the power purchase tables.",
      "Opening balances equal last year's closing balances (assets, loan, equity, deposits, the gap).",
      "Each norm (O&M escalation, depreciation, return on equity, working capital) cites its regulation.",
      "Formulas were recalculated and saved; no cell shows an error or a typed-over total.",
      "Blank cells are meant to be blank, and rounding is applied only where the table prints it.",
      "The petition, affidavit, formats and supporting documents listed by the regulations are all attached.",
    ],
    working: () => "",
    watch: [
      "A petition the Commission can re-add table by table is admitted faster and draws fewer queries.",
      "This guide is a learning example. A real petition must be prepared and signed by the licensee under its own Commission's regulations.",
    ],
  },
];

export function esc(v) {
  return String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
export const fmt = { f0, f1, f2 };
