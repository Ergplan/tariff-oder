// UPERC checks for each step of ARR 101.
//
// Source: Uttar Pradesh Electricity Regulatory Commission (Multi Year Tariff for Distribution)
// Regulations, 2025 (No. UPERC/SECY/REGULATION/2025-009, dated 26.03.2025), English text; the copy
// is packages/regulations/uperc/myt-distribution-2025-english.pdf in this repository.
//
// Each check gives the regulation number, the page of that text, a plain summary and a short
// verbatim `quote` from that page.  tests/unit/test_arr101_uperc.py finds every quote on its page,
// so no check rests on words the regulation does not print.  The summaries were written from the
// text by software and have NOT been verified by a reviewer or a lawyer: read the regulation.
//
// `check(s, r)` compares the reader's answers (s) and the working (r) with the norm and returns
// { ok: true | false | null, text }.  null is a note, not a pass or a fail.

const pct = (v) => `${Number(v)}%`;
const f2 = (v) => Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const FILING = {
  "FY 2025-26": ["30.11.2024", "FY 2023-24", "FY 2024-25"],
  "FY 2026-27": ["30.11.2025", "FY 2024-25", "FY 2025-26"],
  "FY 2027-28": ["30.11.2026", "FY 2025-26", "FY 2026-27"],
  "FY 2028-29": ["30.11.2027", "FY 2026-27", "FY 2027-28"],
  "FY 2029-30": ["30.11.2028", "FY 2027-28", "FY 2028-29"],
};
const normYear = (t) => {
  const m = String(t).match(/(20\d\d)\s*[-–]\s*(\d\d)/);
  return m ? `FY ${m[1]}-${m[2]}` : "";
};

export const UPERC_SOURCE = {
  title: "UPERC (Multi Year Tariff for Distribution) Regulations, 2025",
  number: "No. UPERC/SECY/REGULATION/2025-009, dated 26.03.2025",
  applies: "Distribution licensees in Uttar Pradesh, 1 April 2025 to 31 March 2030.",
  status: "Summaries written from the regulation's text by software. Not verified by a reviewer or a lawyer. Read the regulation itself before you rely on any of it.",
};

export const UPERC = {
  filing: [
    {
      reg: "4.1", page: 9, quote: "The Petitions to be filed in the Control Period under these Regulations will comprise of the following",
      says: "One filing each year, on 30 November, carries all three: the true-up, the APR and the ARR / tariff petition. The regulation tabulates which years go with which filing date.",
      check: (s) => {
        const row = FILING[normYear(s.arrYear)];
        return row
          ? { ok: null, text: `For an ARR of ${normYear(s.arrYear)}, the table gives filing by ${row[0]}, with the true-up of ${row[1]} and the APR of ${row[2]}.` }
          : { ok: false, text: `"${s.arrYear}" is not an ARR year in the regulation's table (FY 2025-26 to FY 2029-30).` };
      },
    },
    {
      reg: "5.1", page: 10, quote: "electronically on e-filing portal of the Commission",
      says: "File in the Commission's prescribed guidelines and formats, on its e-filing portal, authorised by the Board and digitally signed. Hard copies and the fee follow (Reg. 5.2).",
    },
    {
      reg: "5.5", page: 10, quote: "publish a Public Notice in at least two English and two Hindi daily newspapers",
      says: "After the Commission admits the petition, publish a public notice within three working days, and put the petition with its computations on your website in searchable or spreadsheet form.",
    },
    {
      reg: "5.6", page: 11, quote: "within one hundred and twenty days from admittance",
      says: "The Commission issues its order within 120 days of admitting the petition, after considering objections.",
    },
    {
      reg: "6.1", page: 12, quote: "no carrying cost for the period of delay shall be allowed",
      says: "A true-up petition filed late earns no carrying cost on its gap for the period of delay. A surplus is still recovered with carrying cost.",
    },
  ],
  sales: [
    {
      reg: "8.2", page: 12, quote: "category/ sub-category wise number of consumers, connected load, load factor and sales projections",
      says: "The ARR petition must give, by category and sub-category, the number of consumers, connected load, load factor and sales projections.",
      check: () => ({ ok: null, text: "This guide has consumers, load and sales by category. A UPERC filing also needs sub-categories and load factor." }),
    },
    {
      reg: "30.1", page: 38, quote: "to each Tariff slab within such Tariff category / sub-category",
      says: "Forecast sales for each tariff category, sub-category and slab, with the hours of supply.",
    },
    {
      reg: "30.2", page: 38, quote: "Growth Rate (CAGR) of past seven years of sales within each of the slabs",
      says: "Unless the Commission says otherwise, project sales from the compounded annual growth rate of the past seven years, slab by slab, from audited accounts.",
      check: () => ({ ok: null, text: "The sample sales are simply stated. Under UPERC each figure would come from a seven-year CAGR you show." }),
    },
  ],
  balance: [
    {
      reg: "31.2", page: 39, quote: "shall be computed by grossing up the sales with the distribution losses approved by the Commission",
      says: "The purchase requirement at the transmission-distribution interface is sales grossed up by the distribution loss the Commission approved, not the loss you expect.",
      check: (s) => ({ ok: null, text: `You entered ${pct(s.distLossPct)}. Use the loss level approved for the year in the Commission's trajectory.` }),
    },
    {
      reg: "13.3", page: 16, quote: "Transmission Losses and Inter-State Transmission Losses",
      says: "Add distribution losses, intra-State transmission losses and inter-State transmission losses. For true-up, APR and ARR the normative loss trajectory applies.",
      check: (s) => ({ ok: null, text: `This guide uses one transmission loss (${pct(s.txLossPct)}). UPERC asks for intra-State and inter-State losses separately.` }),
    },
    {
      reg: "31.1", page: 39, quote: "shall not be changed/modified, other than under exceptional circumstances",
      says: "The yearly distribution loss trajectory is set for the whole control period and is not changed except in exceptional circumstances.",
    },
  ],
  power: [
    {
      reg: "13.9", page: 17, quote: "in an optimal (least cost and secure) manner",
      says: "Submit a power procurement plan that meets demand at least cost, on merit order despatch principles, with must-run and renewable plants.",
    },
    {
      reg: "8.3", page: 13, quote: "MOD/ SCED principles shall not apply to the purchase of power from renewable energy sources up to the RPO",
      says: "Merit order does not apply to renewable purchases up to the Renewable Purchase Obligation the Commission has set.",
      check: (s) => ({ ok: null, text: `Your renewable share is ${pct(s.sources[1].sharePct)}. Compare it with the RPO percentage in UPERC's RPO regulations (not in this text).` }),
    },
    {
      reg: "29.1", page: 37, quote: "Inter-State Transmission Charges",
      says: "Power purchase, inter-State transmission charges, intra-State transmission charges and SLDC fees are four separate ARR components.",
      check: () => ({ ok: null, text: "This guide rolls transmission into one rate per unit. A UPERC filing shows the three charges separately." }),
    },
  ],
  om: [
    {
      reg: "33.6", page: 42, quote: "Audited Accounts for the last five (5) Financial Years ending March 31, 2025",
      says: "The employee cost base is the average of the last five audited years to 31 March 2025, taken as the middle year and escalated by CPI up to FY 2024-25.",
    },
    {
      reg: "33.6", page: 43, quote: "EMPn= EMPn-1 × (1+ CPI inflation) × (1+ Gn)",
      says: "Each year's employee cost is last year's, escalated by CPI inflation (the average of the three preceding years, for the ARR) and a growth factor Gn the Commission sets.",
      check: (s) => ({ ok: null, text: `You used one escalation of ${pct(s.escalationPct)} for both heads. UPERC uses CPI for employee cost and WPI for A&G, each a three-year average.` }),
    },
    {
      reg: "33.9", page: 44, quote: "A&Gn= A&Gn-1 (1+ WPI inflation) + Provision",
      says: "A&G expenses escalate by WPI inflation, plus a provision for initiatives the Commission has validated.",
    },
    {
      reg: "33.7", page: 43, quote: "For the assets capitalised on or before 31.03.2025 @ 5% of the opening GFA",
      says: "R&M is a norm: 5% of opening gross fixed assets for assets capitalised up to 31.03.2025, and 3% for assets capitalised after.",
      check: (s) =>
        Number(s.rmPctOfGfa) === 5 || Number(s.rmPctOfGfa) === 3
          ? { ok: true, text: `Your ${pct(s.rmPctOfGfa)} is one of UPERC's two norms. Apply 5% to the older assets and 3% to the newer.` }
          : { ok: false, text: `Your ${pct(s.rmPctOfGfa)} is not UPERC's norm. It allows 5% (assets up to 31.03.2025) and 3% (later assets).` },
    },
  ],
  capital: [
    {
      reg: "19.2", page: 28, quote: "70:30 of the amount of capital cost approved by the Commission",
      says: "New assets are funded 70:30 debt to equity, after removing what consumer contributions and grants paid for. Equity above 30% is treated as loan; equity below 30% is taken as it is.",
      check: (s) =>
        Number(s.debtSharePct) === 70
          ? { ok: true, text: "Your 70% loan share matches the 70:30 norm." }
          : Number(s.debtSharePct) > 70
            ? { ok: null, text: `Your loan share is ${pct(s.debtSharePct)}: allowed where actual equity is below 30%, with evidence.` }
            : { ok: false, text: `Your loan share is ${pct(s.debtSharePct)}. Equity above 30% is treated as normative loan, so the share cannot be below 70%.` },
    },
    {
      reg: "20.1", page: 30, quote: "Depreciation shall be allowed up to a maximum of 90% of the allowable capital cost of the asset",
      says: "Straight-line depreciation at the rates in Annexure A (existing assets) and Annexure B (new assets), up to 90% of cost. Land is not depreciated. Nothing on assets funded by consumers or grants.",
      check: (s) => ({ ok: null, text: `You used one blended rate of ${pct(s.depRatePct)}. UPERC requires the Annexure rate for each class of asset.` }),
    },
    {
      reg: "20.3", page: 30, quote: "depreciation shall be computed based on the average of opening and closing value of assets",
      says: "Where assets come into use part-way through a projected year, depreciation is on the average of the opening and closing asset values.",
      check: () => ({ ok: true, text: "This guide depreciates the average of opening and closing assets." }),
    },
    {
      reg: "21.1", page: 31, quote: "at the rate of 15% post-tax per annum",
      says: "Return on equity is 15% a year, post-tax, on the equity base fixed under Regulation 19.",
      check: (s) =>
        Number(s.roePct) === 15
          ? { ok: true, text: "Your 15% matches UPERC's rate." }
          : { ok: false, text: `Your ${pct(s.roePct)} differs: UPERC's rate is 15% post-tax.` },
    },
    {
      reg: "26.1", page: 33, quote: "shall be grossed up with the effective tax rate",
      says: "The return on equity is grossed up by the effective tax rate, and that tax is its own ARR component.",
      check: () => ({ ok: null, text: "This guide leaves tax on return on equity out. A UPERC filing must add it." }),
    },
    {
      reg: "22.3", page: 31, quote: "shall be deemed to be equal to the",
      says: "Each year's loan repayment is deemed equal to the depreciation allowed for that year.",
      check: () => ({ ok: true, text: "This guide takes repayment equal to depreciation." }),
    },
    {
      reg: "22.5", page: 31, quote: "SBI MCLR (1 Year) prevailing during the concerned year plus 100 basis points",
      says: "The interest rate is the weighted average rate of your actual long-term loans at the start of the year. With no actual loan, it is SBI one-year MCLR plus 1%. Interest is on the average normative loan (Reg. 22.7).",
      check: (s) => ({ ok: null, text: `You entered ${pct(s.loanRatePct)}. Support it with your loan portfolio's weighted average rate.` }),
    },
  ],
  wc: [
    {
      reg: "25.1", page: 32, quote: "Operation and maintenance expenses for one month",
      says: "Working capital covers one month of O&M, maintenance spares at 40% of R&M for two months, and one and a half months of expected revenue, less consumer security deposits.",
      check: (s, r) => {
        const spares = (r.rm * 0.4 * 2) / 12;
        const months = Number(s.receivableMonths) === 1.5;
        return {
          ok: months ? null : false,
          text: `${months ? "Your 1.5 months of revenue matches." : `You used ${s.receivableMonths} months of revenue; UPERC allows 1.5.`} This guide leaves maintenance spares out: UPERC would add ${f2(spares)} Rs lakh (40% × R&M ${f2(r.rm)} × 2 ÷ 12).`,
        };
      },
    },
    {
      reg: "25.1", page: 33, quote: "it shall be reduced by the amount of revenue surplus",
      says: "A positive working capital requirement is reduced by any revenue surplus the Commission approved as of 31 March of the previous year. Revenue here is at the tariff approved for the ensuing year, excluding electricity duty.",
    },
    {
      reg: "25.2", page: 33, quote: "200 basis points",
      says: "The interest rate is simple interest at SBI one-year MCLR on the date the petition is filed, plus 2%.",
      check: (s) => ({ ok: null, text: `You entered ${pct(s.wcRatePct)}. Under UPERC it is SBI one-year MCLR on your filing date plus 2%, not a rate you choose.` }),
    },
    {
      reg: "25.3", page: 33, quote: "Interest paid on consumer security deposits",
      says: "Interest paid to consumers on security deposits, as the Electricity Supply Code provides, is allowed.",
    },
    {
      reg: "34.1", page: 45, quote: "up to the extent of 2% of revenue from the sale of electricity",
      says: "Bad debts: up to 2% of revenue or the actual write-off, whichever is less, and never more than the provision in the audited accounts. In an ARR order it is provisionally the amount approved for the true-up year.",
      check: (s) =>
        Number(s.badDebtPct) <= 2
          ? { ok: true, text: `Your ${pct(s.badDebtPct)} is within the 2% ceiling. It must also not exceed your actual write-off.` }
          : { ok: false, text: `Your ${pct(s.badDebtPct)} is above UPERC's ceiling of 2% of revenue.` },
    },
    {
      reg: "35.1", page: 45, quote: "shall be deducted from the ARR in determining the Tariff",
      says: "Non-tariff income is deducted from the ARR. Regulation 35.2 lists what counts, including rent, sale of scrap, income from investments and delayed payment surcharge.",
    },
  ],
  revenue: [
    {
      reg: "8.4", page: 13, quote: "Existing and proposed Tariff as on the date of filing of the Petition",
      says: "Forecast revenue from the energy you will supply and wheel, at both the existing and the proposed tariff as on the filing date.",
      check: () => ({ ok: null, text: "This step works revenue at the existing tariff only. A UPERC filing also shows revenue at the proposed tariff." }),
    },
    {
      reg: "29.2", page: 38, quote: "any combination of fixed/demand charges, energy charges, and any other charges/incentives",
      says: "The retail tariff may combine fixed or demand charges, energy charges and other charges or incentives.",
    },
    {
      reg: "6.3", page: 12, quote: "category/ sub-category wise billed revenue as per the Rate Schedule",
      says: "Your accounting statements must carry billed revenue by category and sub-category as per the Rate Schedule.",
    },
  ],
  arr: [
    {
      reg: "29.1", page: 37, quote: "comprising the following components",
      says: "The ARR has thirteen cost components, (a) to (m), less non-tariff income and income from other business.",
      check: () => ({
        ok: null,
        text: "This guide's ARR leaves out four of them: SLDC fees, banking and finance charges, tax on return on equity, and income from other business.",
      }),
    },
    {
      reg: "8.5", page: 13, quote: "including unrecovered revenue gaps of previous years to the extent proposed to be recovered",
      says: "File the ARR, revenue at the existing tariff, and a category-wise proposed tariff that meets the gap, including earlier years' unrecovered gaps you propose to recover.",
    },
    {
      reg: "27.3", page: 35, quote: "at the interest rates as provided for working capital in these Regulations",
      says: "Carrying cost on an ARR gap is allowed, after prudence check, at the working capital interest rate. A surplus is first set against working capital (Reg. 27.4).",
      check: (s) => ({
        ok: null,
        text: Number(s.gapBroughtForward)
          ? `Your brought-forward figure of ${f2(s.gapBroughtForward)} Rs lakh should carry cost at the working capital rate (${pct(s.wcRatePct)} here).`
          : "You have no brought-forward gap. If you had one, its carrying cost would be at the working capital rate.",
      }),
    },
    {
      reg: "42.2", page: 49, quote: "shall be determined on the basis of the Average Cost of Supply",
      says: "Retail tariffs are set on the basis of the average cost of supply, keeping in view the cost at each voltage level and avoiding tariff shock.",
      check: (s, r) => ({ ok: null, text: `Your average cost of supply is Rs ${f2(r.acos)} per unit, and your tariff change needed is ${Number(r.increasePct).toFixed(1)}%.` }),
    },
  ],
  checks: [
    {
      reg: "5.1", page: 10, quote: "after due authorization by the Board of Directors",
      says: "The petition must be authorised by the Board, or a person the Board authorises, and digitally signed.",
    },
    {
      reg: "6.4", page: 12, quote: "Electricity Distribution (Accounts and Additional Disclosure) Rules",
      says: "Accounting statements must follow the Electricity Distribution (Accounts and Additional Disclosure) Rules, 2024.",
    },
    {
      reg: "6.5", page: 12, quote: "status of compliance to the directives issued by the Commission",
      says: "Attach a statement of compliance with the directives in the previous tariff order and any earlier ones still pending.",
    },
    {
      reg: "5.4", page: 10, quote: "The Commission shall conduct a technical validation before admission of the Petition",
      says: "The Commission validates the petition technically before admitting it. Tables that do not add up delay admission.",
    },
    {
      reg: "27.2", page: 35, quote: "shall not be allowed to be recovered through the ARR",
      says: "Penalties and compensation for failing standards of performance are not recoverable through the ARR. Keep and submit separate details of them.",
    },
  ],
};
