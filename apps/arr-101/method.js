// The method of each step as explicit relations: [relation, where it comes from or what the symbols mean].
// These are the relations calc.js computes; the UPERC check below each step says where UPERC's differ.

export const METHOD = {
  filing: [
    ["Petition(y) = True-up(y − 2) + APR(y − 1) + ARR(y)", "three years in one filing; y is the coming year"],
    ["Claim = Formats + Narrative + Evidence", "every figure in the narrative is a figure in the formats"],
  ],
  sales: [
    ["S = Σ S_c", "S_c: energy sold to category c in the year (MWh)"],
    ["g_c = (S_c,t ÷ S_c,t−n)^(1/n) − 1", "compound annual growth over n past years"],
    ["S_c,y = S_c,y−1 × (1 + g_c)", "the forecast, category by category"],
  ],
  balance: [
    ["E_boundary = S ÷ (1 − l_d)", "l_d: distribution loss"],
    ["E_purchase = E_boundary ÷ (1 − l_t)", "l_t: transmission loss"],
    ["l_d = 1 − S ÷ E_boundary", "the same relation, read as a measurement"],
  ],
  power: [
    ["C_energy = Σ E_s × r_s ÷ 100", "E_s: MWh from source s; r_s: Rs/kWh; result in Rs lakh"],
    ["C_tx = E_boundary × t ÷ 100", "t: transmission charge, Rs/kWh"],
    ["r_avg = C_energy × 100 ÷ E_purchase", "an average rate is a result, never an input"],
  ],
  om: [
    ["EMP_y = EMP_y−1 × (1 + i)", "i: allowed escalation"],
    ["A&G_y = A&G_y−1 × (1 + i)", ""],
    ["R&M_y = k × GFA_open", "k: the R&M norm"],
    ["O&M_y = EMP_y + A&G_y + R&M_y", ""],
  ],
  capital: [
    ["GFA_close = GFA_open + CAP − CC", "CAP: capitalisation; CC: paid by consumers or grants"],
    ["DEP = d × (GFA_open + GFA_close) ÷ 2", "d: depreciation rate"],
    ["L_close = L_open + a × (CAP − CC) − DEP", "a: debt share; repayment taken equal to DEP"],
    ["INT = r_L × (L_open + L_close) ÷ 2", ""],
    ["E_close = E_open + (1 − a) × (CAP − CC)", ""],
    ["RoE = r_E × (E_open + E_close) ÷ 2", ""],
  ],
  wc: [
    ["WC = O&M ÷ 12 + m × REV ÷ 12 − SD", "m: months of receivables; SD: security deposits held"],
    ["IWC = r_wc × max(WC, 0)", "or r_wc × WC where a negative requirement is netted"],
    ["ISD = r_sd × SD", "interest paid to consumers"],
    ["BD = b × REV", "b: provision for bad debts"],
  ],
  revenue: [
    ["REV_c = S_c × e_c ÷ 100 + L_c × f_c × 12 ÷ 100000", "e_c: Rs/kWh; L_c: kW; f_c: Rs/kW/month; Rs lakh"],
    ["REV = Σ REV_c", ""],
    ["ABR_c = REV_c × 100 ÷ S_c", "average billing rate of the category, Rs/kWh"],
  ],
  arr: [
    ["ARR = PP + O&M + DEP + INT + RoE + IWC + ISD + BD − NTI", "NTI: non-tariff income"],
    ["GAP = ARR − REV + GAP_brought forward", "positive: a gap; negative: a surplus"],
    ["ACoS = ARR × 100 ÷ S", "average cost of supply, Rs/kWh"],
    ["Δtariff = GAP ÷ REV", "the average change the tariff proposal must deliver"],
  ],
  checks: [
    ["Σ rows = total", "in every table, as printed"],
    ["opening(y) = closing(y − 1)", "assets, loan, equity, deposits, the gap"],
    ["x(format) = x(summary) = x(narrative)", "one figure, the same in every place"],
  ],
};
