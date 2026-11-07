#!/usr/bin/env python3
"""Write packages/reference-filings/uperc-npcl-fy2026-27/column-labels.json (increment 154): hand labels for
the fill-map columns reference.json's header reader does not label — sheets with one year per sheet, years
in row blocks, or the voice in the title.  Each label's year and voice are decided here, by a person, from
the sheet's printed headers; its `basis` quotes those words, read from the workbook so the quote is exact
(tests/unit/test_column_labels.py checks every quote against the sheet).

    uv run python scripts/npcl_column_labels.py packages/reference-filings/uperc-npcl-fy2026-27
"""

import json
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

folder = Path(sys.argv[1])
wb = openpyxl.load_workbook(folder / "4. Appendix-II MYT Tariff Formats ARR FY 2026-27.xlsx", data_only=True)
names = {n.strip(): n for n in wb.sheetnames}


def words(sheet, *cells):
    ws = wb[names[sheet]]
    out = []
    for ref in cells:
        v = ws[ref].value
        out.append(f"{ref}: " + re.sub(r"\s+", " ", str(v)).strip())
    return "; ".join(out)


def span(a, b):
    return [get_column_letter(i) for i in range(column_index_from_string(a), column_index_from_string(b) + 1)]


A, P, T, R = "actual", "petitioned", "final_true_up", "approved"
TITLE = {
    "ESR_3 Curr Tariff FY24": ("A3", "C5", "C6", "C7"),
    "ESR_3 Curr Tariff FY25": ("C3", "D5", "D6", "D7"),
    "ESR_3 Curr Tariff FY26": ("B3", "B5", "B6", "B7"),
    "ESR_3 Curr Tariff FY27": ("B3", "B5", "B6", "B7"),
    "ESR4_Prop Tariff": ("B3", "B5", "B6", "B7"),
}
L = []  # (sheet, letters, fy, voice, restated, input, basis, rows, note)


def lab(sheet, letters, fy, voice, basis, restated=False, inp=False, rows=None, note=None):
    L.append(
        {
            "sheet": names[sheet],
            "columns": letters,
            "fiscal_year": fy,
            "voice": voice,
            "restated": restated,
            "input": inp,
            "rows": rows,
            "basis": basis,
            "note": note,
        }
    )


# ---- the Commission's figures (restated) and the tariff rates (inputs)
lab(
    "ESR5_BD&Rev",
    span("B", "E"),
    "FY2022-23",
    T,
    words("ESR5_BD&Rev", "B6", "B5", "E5"),
    restated=True,
    note="billing determinants as the Commission trued them up for FY2022-23",
)
RATE_NOTE = (
    "the tariff in force, as the Commission's order sets it: an input, never an average backed out of revenue ÷ units"
)
for s, fy, rate_cols in (
    ("ESR_3 Curr Tariff FY24", "FY2023-24", ("F", "G")),
    ("ESR_3 Curr Tariff FY25", "FY2024-25", ("G", "H")),
    ("ESR_3 Curr Tariff FY27", "FY2026-27", ("G", "H")),
):
    lab(
        s,
        list(rate_cols),
        fy,
        R,
        words(s, *TITLE[s]) + " — " + words(s, *[f"{c}8" for c in rate_cols]),
        restated=True,
        inp=True,
        note=RATE_NOTE,
    )
lab(
    "ESR4_Prop Tariff",
    ["G", "H"],
    "FY2026-27",
    P,
    words("ESR4_Prop Tariff", *TITLE["ESR4_Prop Tariff"]) + " — " + words("ESR4_Prop Tariff", "G8", "H8"),
    inp=True,
    note="the tariff the petitioner proposes: an input, never an average backed out of revenue ÷ units",
)

# ---- the petitioner's own figures, sheet by sheet
for s in ("BS1", "BS2"):
    lab(s, ["C"], "FY2022-23", A, words(s, "A3", "C6"), note="the audited accounts' statements")
    lab(s, ["D"], "FY2023-24", A, words(s, "A3", "D6"), note="the audited accounts' statements")
    lab(s, ["E"], "FY2024-25", A, words(s, "A3", "E6"), note="the audited accounts' statements")
lab("BS3", ["D"], "FY2022-23", A, words("BS3", "A3"), note="the audited accounts' statements")
lab("BS3", ["E"], "FY2023-24", A, words("BS3", "A3"), note="the audited accounts' statements")
lab("BS3", ["F"], "FY2024-25", A, words("BS3", "A3"), note="the audited accounts' statements")
lab(
    "ARR snapshot",
    ["D"],
    "FY2026-27",
    P,
    words("ARR snapshot", "B79", "B88", "B90"),
    rows=[79, 200],
    note=(
        "below row 79 column D holds the ARR year's claimed energy, ABR and ACoS — "
        "not the upper table's 'Approved in Tariff Order' (D4)"
    ),
)
lab("ESR1_OA", ["J"], "FY2023-24", P, words("ESR1_OA", "C5", "C6", "C7", "J8"))
lab("ESR1_OA", ["R"], "FY2024-25", A, words("ESR1_OA", "K5", "K6", "K7", "R8"))
lab("ESR1_OA", ["Z"], "FY2025-26", P, words("ESR1_OA", "S5", "S6", "S7", "Z8"))
lab("ESR1_OA", ["AH"], "FY2026-27", P, words("ESR1_OA", "AA5", "AA6", "AA7", "AH8"))
for i, fy in enumerate(("FY2017-18", "FY2018-19", "FY2019-20", "FY2020-21", "FY2021-22", "FY2022-23", "FY2023-24")):
    a = get_column_letter(3 + 3 * i)
    lab(
        "ESR2_Sales Forecast",
        span(a, get_column_letter(5 + 3 * i)),
        fy,
        A,
        words("ESR2_Sales Forecast", f"{a}6", f"{a}7"),
        rows=[60, 200],
    )
lab("ESR2_Sales Forecast", span("X", "Z"), "FY2024-25", A, words("ESR2_Sales Forecast", "X6", "X7"), rows=[60, 200])
lab("ESR2_Sales Forecast", span("AA", "AC"), "FY2025-26", P, words("ESR2_Sales Forecast", "AA6", "AA7"), rows=[60, 200])
lab("ESR2_Sales Forecast", span("AD", "AF"), "FY2026-27", P, words("ESR2_Sales Forecast", "AD6", "AD7"), rows=[60, 200])
lab(
    "ESR2_Sales Forecast",
    span("AG", "AI"),
    None,
    P,
    words("ESR2_Sales Forecast", "AG6"),
    note="a growth rate the petitioner computes",
)
lab("ESR4_Prop Tariff", ["F", "N", "O"], "FY2026-27", P, words("ESR4_Prop Tariff", *TITLE["ESR4_Prop Tariff"]))
lab("ESR5_BD&Rev", ["N", "P", "R", "T", "U"], "FY2024-25", P, words("ESR5_BD&Rev", "N6"))
lab(
    "ESR_3 Curr Tariff FY24",
    ["E", "P"],
    "FY2023-24",
    A,
    words("ESR_3 Curr Tariff FY24", *TITLE["ESR_3 Curr Tariff FY24"]),
)
lab(
    "ESR_3 Curr Tariff FY25",
    ["F", "N", "O"],
    "FY2024-25",
    A,
    words("ESR_3 Curr Tariff FY25", *TITLE["ESR_3 Curr Tariff FY25"]),
)
lab(
    "ESR_3 Curr Tariff FY26",
    ["F", "N", "O"],
    "FY2025-26",
    P,
    words("ESR_3 Curr Tariff FY26", *TITLE["ESR_3 Curr Tariff FY26"]),
)
lab(
    "ESR_3 Curr Tariff FY27",
    ["F", "N", "O"],
    "FY2026-27",
    P,
    words("ESR_3 Curr Tariff FY27", *TITLE["ESR_3 Curr Tariff FY27"]),
)
lab("F11_CAP_Asset not in use", ["C", "E", "F"], "FY2024-25", A, words("F11_CAP_Asset not in use", "A5"))
lab("F12_CAP_Cons Contri", ["E"], "FY2024-25", A, words("F12_CAP_Cons Contri", "C5", "C6", "C7"))
lab("F12_CAP_Cons Contri", ["I", "J"], "FY2024-25", P, words("F12_CAP_Cons Contri", "C5", "C6", "G7"))
lab("F12_CAP_Cons Contri", ["N"], "FY2025-26", P, words("F12_CAP_Cons Contri", "K5", "K6", "K7"))
lab("F12_CAP_Cons Contri", ["R"], "FY2026-27", P, words("F12_CAP_Cons Contri", "O5", "O6", "O7"))
lab(
    "F13_CAP_Plan",
    ["E", "F"],
    None,
    "by_row_block",
    words("F13_CAP_Plan", "A11"),
    note="years in row blocks (column A); the petitioner's plan",
)
lab("F16_CAP_CAPEX & CAP. after FY25", ["C"], "FY2025-26", P, words("F16_CAP_CAPEX & CAP. after FY25", "B3", "B4"))
lab("F16_CAP_CAPEX & CAP. after FY25", ["E"], "FY2026-27", P, words("F16_CAP_CAPEX & CAP. after FY25", "D3", "D4"))
lab("F16_CAP_CAPEX & CAP. till 25", ["C"], "FY2023-24", A, words("F16_CAP_CAPEX & CAP. till 25", "B3", "B4"))
lab("F16_CAP_CAPEX & CAP. till 25", ["E"], "FY2024-25", A, words("F16_CAP_CAPEX & CAP. till 25", "D3", "D4"))
for c, fy in zip("CDEFG", ("FY2020-21", "FY2021-22", "FY2022-23", "FY2023-24", "FY2024-25"), strict=True):
    lab(
        "F19_O&M_EE n AG base",
        [c],
        fy,
        "not_printed",
        words("F19_O&M_EE n AG base", f"{c}6"),
        note="the sheet prints the year, not whether the figure is audited or trued-up: for the reviewer",
    )
lab(
    "F19_O&M_EE n AG base",
    ["H"],
    "FY2022-23",
    P,
    words("F19_O&M_EE n AG base", "H6"),
    note="an average the petitioner computes",
)
lab(
    "F19_O&M_EE n AG base",
    ["I"],
    "FY2023-24",
    "not_printed",
    words("F19_O&M_EE n AG base", "I6"),
    note="for the reviewer",
)
lab(
    "F19_O&M_EE n AG base",
    ["J"],
    "FY2024-25",
    "not_printed",
    words("F19_O&M_EE n AG base", "J6"),
    note="for the reviewer",
)
lab("F19_O&M_EE n AG base", ["K"], "FY2025-26", P, words("F19_O&M_EE n AG base", "K6", "K7"))
lab("F19_O&M_EE n AG base", ["L"], "FY2026-27", P, words("F19_O&M_EE n AG base", "L6", "L7"))
lab(
    "F1_PP_Annual",
    ["J", "K", "L", "N", "O", "P"],
    None,
    "by_row_block",
    words("F1_PP_Annual", "A6"),
    note="years in row blocks (column A)",
)
for cols, fy, g in (
    (["B", "C"], "FY2020-21", "B5"),
    (["D", "E"], "FY2021-22", "B5"),
    (["F", "G"], "FY2022-23", "B5"),
    (["H", "I"], "FY2023-24", "H5"),
):
    lab(
        "F20_O&M_EE",
        cols,
        fy,
        "not_printed",
        words("F20_O&M_EE", g, f"{cols[0]}6"),
        note="the sheet prints 'Past years', not audited or trued-up: for the reviewer",
    )
lab("F20_O&M_EE", ["J", "K"], "FY2024-25", A, words("F20_O&M_EE", "J5", "J6"), note="the true-up year's own figures")
lab(
    "F24_Dep",
    ["E", "G", "I", "J"],
    None,
    "by_row_block",
    words("F24_Dep", "A7", "A4"),
    note="years in row blocks (column A)",
)
lab("F30_CSD monthly", span("B", "N"), "FY2024-25", A, words("F30_CSD monthly", "A3"))
lab("F32_Wheeling-Supply", ["F", "H"], "FY2026-27", P, words("F32_Wheeling-Supply", "K5", "L6"))
lab(
    "F33_CSS",
    ["C", "D", "F", "G", "I", "J"],
    "FY2026-27",
    P,
    words("F33_CSS", "A3"),
    note="the ARR year's cross-subsidy surcharge as the petitioner computes it",
)
for s, fy, vo in (
    ("F3_PP_Monthly FY2025", "FY2024-25", A),
    ("F3_PP_Monthly FY2026", "FY2025-26", P),
    ("F3_PP_Monthly FY2027", "FY2026-27", P),
):
    ws = wb[names[s]]
    cols = sorted(
        {get_column_letter(c.column) for row in ws.iter_rows(min_row=17, max_row=43) for c in row},
        key=column_index_from_string,
    )
    lab(s, [c for c in cols if column_index_from_string(c) >= column_index_from_string("V")], fy, vo, words(s, "A1"))
lab("F4_PP_MOD", span("D", "L"), "FY2024-25", A, words("F4_PP_MOD", "D6"))
lab("F4_PP_MOD", span("M", "U"), "FY2025-26", P, words("F4_PP_MOD", "M6"))
lab("F4_PP_MOD", span("V", "AD"), "FY2026-27", P, words("F4_PP_MOD", "V6"))
lab("F5_PP_Renew", ["J"], None, "by_row_block", words("F5_PP_Renew", "A6"), note="years in row blocks (column A)")
lab("F6_PP6_RPO", ["D"], "FY2024-25", P, words("F6_PP6_RPO", "D6", "D7"))
lab("F6_PP6_RPO", ["E"], "FY2025-26", P, words("F6_PP6_RPO", "E7"))
lab("F6_PP6_RPO", ["F"], "FY2026-27", P, words("F6_PP6_RPO", "F7"))
lab("F7_PP_Comp Bid", ["B", "C"], "FY2024-25", A, words("F7_PP_Comp Bid", "A3"))
lab(
    "F8_PP_Short Term",
    ["F", "G", "H"],
    None,
    "by_row_block",
    words("F8_PP_Short Term", "A9"),
    note="years in row blocks (column A)",
)
lab("F9_PP_plan", ["C", "D"], "FY2024-25", P, words("F9_PP_plan", "B5", "B6", "B7"))
lab("F9_PP_plan", ["F", "G"], "FY2025-26", P, words("F9_PP_plan", "E5", "E6", "E7"))
lab("F9_PP_plan", ["I", "J"], "FY2026-27", P, words("F9_PP_plan", "H5", "H6", "H7"))
lab("P11_Land", ["N"], None, "not_printed", words("P11_Land", "N5"), note="the sheet prints no year: for the reviewer")
lab("P1_DL", ["D"], None, P, words("P1_DL", "D6"), note="years by row (column C)")
lab(
    "P3_Bad Debts",
    ["C"],
    "FY2023-24",
    "not_printed",
    words("P3_Bad Debts", "C6", "C7"),
    note="'Past year': for the reviewer",
)
lab("P3_Bad Debts", ["D"], "FY2024-25", A, words("P3_Bad Debts", "D6", "D7"))
lab("P3_Bad Debts", ["E"], "FY2025-26", P, words("P3_Bad Debts", "E6", "E7"))
for cols, a in ((["D", "E"], "C"), (["G", "H"], "F"), (["J", "K"], "I"), (["M", "N"], "L")):
    fy = {"C": "FY2023-24", "F": "FY2024-25", "I": "FY2025-26", "L": "FY2026-27"}[a]
    lab(
        "P4_Phy Stat",
        cols,
        fy,
        P,
        words("P4_Phy Stat", f"{a}5", f"{a}6", f"{a}7"),
        note="under the true-up year's 'Trued-Up' heading the voice row reads 'Claimed': the petitioner's"
        if a == "F"
        else None,
    )
lab("P5_Arrear", ["F", "G"], None, "by_row_block", words("P5_Arrear", "A7"), note="years in row blocks (column A)")
lab(
    "P7_Trans Failure",
    span("C", "H"),
    None,
    "not_printed",
    words("P7_Trans Failure", "C6", "F6"),
    note="'Past Year': for the reviewer",
)
lab("P7_Trans Failure", span("I", "K"), "FY2024-25", A, words("P7_Trans Failure", "I5", "I6"))
lab(
    "P8_Elec Accidents",
    ["G"],
    "FY2022-23",
    "not_printed",
    words("P8_Elec Accidents", "C5", "C6"),
    note="'Past year': for the reviewer",
)
lab(
    "P8_Elec Accidents",
    ["L"],
    "FY2023-24",
    "not_printed",
    words("P8_Elec Accidents", "H5", "H6"),
    note="'Past year': for the reviewer",
)
lab("P8_Elec Accidents", ["Q"], "FY2024-25", A, words("P8_Elec Accidents", "M5", "M6"))
for s, fy, vo, ref in (
    ("PPC FY 24", "FY2023-24", A, "B3"),
    ("PPC FY 25", "FY2024-25", A, "B5"),
    ("PPC FY 26", "FY2025-26", P, "A5"),
    ("PPC FY 27", "FY2026-27", P, "A5"),
):
    ws = wb[names[s]]
    cols = sorted(
        {get_column_letter(c.column) for row in ws.iter_rows(min_row=8, max_row=80) for c in row},
        key=column_index_from_string,
    )
    lab(s, cols, fy, vo, words(s, ref))

doc = {
    "package": folder.name,
    "status": (
        "hand labels for the fill-map columns reference.json's header reader does not label (written 2026-11-07 "
        "from the printed headers quoted in `basis`); for the reviewer to confirm.  `restated`: the Commission's "
        "figure quoted from an order — the inputs template keeps it as filed.  `input`: a tariff rate — kept as "
        "filed, never backed out of revenue ÷ units.  `not_printed`: the sheet does not say whether a past year's "
        "figure is audited or trued-up — kept out of the kept set, for the reviewer.  `by_row_block`: the sheet "
        "stacks years in row blocks."
    ),
    "labels": L,
}
(folder / "column-labels.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
print(len(L), "labels;", sum(x["restated"] for x in L), "restated;", sum(x["input"] for x in L), "input")
