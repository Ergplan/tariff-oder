# The ARR petition flow — as built, and the path to filling NPCL's petition

*Written in increment 150 (2026-11-05), at the operator's request: "check the flow of ARR
petition; in the next round we will fill the petition for NPCL — make the application ready".
Kept current with `docs/BUILD_STATE.md`.*

## 1. Two flows in the application

**A. The client case flow** (ADR-0019, `arr/cases.py`, routes `/cases/…`, pages under
`apps/web/app/client/cases/`):

1. An organisation opens a **case** for a licensee: `annual_arr`, `myt`, `true_up` or `apr`, with a
   base year and target years (`POST /cases`).
2. **Readiness** (`GET /cases/{id}`): the base facts the plan needs (from read orders, by voice),
   the regulation parameters it needs, and the documents in the library for the licensee and year.
3. **Assumptions** (`POST /cases/{id}/assumptions`): each parameter entered by a named user with a
   rationale; nothing defaulted.
4. **Formulate → freeze → draft** (`POST /cases/{id}/formulate`, `/freeze`, `/draft`): the
   commission's *formulation plan* computes the target years' lines; a frozen formulation is
   rendered into the commission's *filing template* (formats XLSX + narrative DOCX), each number
   through a traced placeholder, watermarked as a draft.
5. True-up and APR cases add **actuals** (with page and quote), a **variance statement** against the
   approval, and their own draft.

**B. The reference reproduction** (milestone 13, `packages/reference-filings/uperc-npcl-fy2026-27`,
`scripts/reproduce_formats.py`, page `/arr/reference/…`): 280 draft UPERC rules and 112 bindings
reproduce NPCL's filed FY2026-27 petition format by format — 67 of its 74 formats checked, the
other seven text, blank or not filed (increments 54–149).

## 2. The gap this increment found

Flow A does not use flow B's engine (R-RULE-3, "cases do not use the engine yet"):

- `packages/arr-taxonomy/formulation/uperc-plan.v1.json` is a **16-line skeleton** (sales, loss,
  power purchase, O&M, depreciation, interest, RoE, NTI, ARR, revenue, gap, ACoS) — status
  *skeleton*, carry-forward and escalation formulas, none of the 280 rules.
- `packages/filing-templates/uperc/petition.v1.json` has **two sheets** (S-1, S-2).

So a case today drafts a two-sheet summary, not NPCL's 74 formats.  Filling NPCL's petition needs
flow B's engine to *write* the formats, not only check them.

## 3. The petition fill (increment 150)

`tariff_api.arr.petition_fill`, `scripts/petition_fill.py`:

- **Fill mode in the engine.**  Every reproducer (`reproduce`, `reproduce_cells`,
  `reproduce_row_table`, `reproduce_period_table`) now names the cell of each result, gives the
  unrounded figure in the cell's unit, marks *ties* (a figure carried from another format) and the
  cell a tie repeats, and — filling — computes an output whose cell is blank.
- **The fill map** (`fill-map.json`, 4,492 cells): the cells the engine computes that the filed
  format prints (4,406), and the carried cells whose formula in the filing links them to the
  format they repeat (86).  A cell the filing leaves blank stays blank; a cell the petitioner
  computes another way (the ARR's loss as 1 − sales / input; the cash flow's opening line) is the
  petitioner's own — checked, not filled.
- **The fill** (`fill`): passes over the bindings until nothing changes (10–11 passes; a binding is
  re-run only when a sheet it reads was written).  Blank map cells are filled; **an entered figure is
  never overwritten** — it is checked and a difference reported with both figures; a carried cell
  copies the figure it repeats as it stands; an output whose inputs are missing stays blank, listed
  with the engine's reason; two bindings computing one cell differently are a conflict, reported.
  Verification-only bindings are left out (order approvals, annexure workbooks, the ledger, the
  pipeline, the end-to-end ARR chain, the comparison with Reg. 30.2's CAGR) — 28 of 112.
- **The output**: the workbook with computed cells shaded green and carried cells blue, a *Fill
  trace* sheet (each figure, its binding, output and pass; each difference; each blocked cell), and a
  JSON report.
- **The inputs template** (`template`): the filed workbook with the fill map blanked — what a
  petitioner enters is what remains.

**The round trip on NPCL's FY2026-27 filing** (`fill-roundtrip.json`, tested):

| run | cells filled | equal to the filing at its printed precision | differ | left blank | conflicts |
|---|---|---|---|---|---|
| the 49 cells whose reproduction already differs kept as filed | 4,443 | **4,443** | 0 | 0 | 0 |
| none kept | 4,492 | 4,427 | 65 | 0 | 0 |

The 65 are the 49 known differences (findings such as A40, A41, A83, A86, A91 and the restated
FY2022-23 columns) and the figures that follow from them through the chain.

## 4. What remains before NPCL's petition can be filled in the application

Smallest first:

1. **Into the case flow — done (increment 151).**  A UPERC / NPCL case has a formats workbook
   (`arr/petition.py`, table `petition_workbooks`, routes `/cases/{id}/petition/…`):
   - `GET …/layout`: the filing the fill follows, its years, the cells a fill writes, and a
     warning when the case's years are not the layout's;
   - `GET …/template`: the inputs template;
   - `POST …/workbooks`: upload an inputs workbook.  It is checked to be an XLSX laid out as
     the filing, and compared with the filed inputs: blank / changed / as filed, fill cells
     already entered, formulas saved without a value;
   - `POST …/workbooks/{id}/fill`: queues the `petition_fill` job (about 90 s);
   - `GET …/workbooks/{id}`, `…/report`, `…/download`: the filled workbook (shaded, a Fill
     trace sheet, a WORKING DRAFT header on every sheet) and its full report.
   It is stored as its own table, not as a `FilingDraft`: a draft there is a DOCX and XLSX
   rendered from a frozen formulation, while a filled workbook is the petitioner's own
   workbook completed.
   **Uploading the filed workbook itself** (formulas with their saved values) runs the engine
   as a pure check: every map cell is already entered, so nothing is written and every figure
   is checked.  On NPCL's filing (run 2026-11-05): 0 written, 4,606 agree, 59 differ (the
   known differences, A40, A41, A83 and the rest, and the ties that repeat them), 0 conflicts,
   one pass.
2. **The client page — done (increment 152).**  The case page's "Formats workbook" panel walks through the layout, the template, the upload, the fill and the results format by format.  Before that increment the plan read: the case shows, format by format, cells filled / checked /
   differing / blocked, and offers the downloads.
3. **The narrative — summary tables done (increment 153).**  `arr/narrative_fill.py` writes the
   nine summary tables bound in increment 93 (five DOCX files) from the filled workbook, as part
   of the fill job.  It works at the printed precision and style.  Changed cells are shaded
   green.  A cell merged over two rows is left as filed (A56).  Rows the binding does not cover
   are the petitioner's own, shaded yellow.  The prose and the other tables are as filed.
   Download: `GET …/workbooks/{id}/narrative` (a ZIP).  Refilled from the filing's own
   workbook it changes exactly 20 cells, all differences increment 93 found.
   **The template now keeps 179 cells as filed:** the Commission's figures quoted from its
   orders (143 cells in approved and trued-up columns) and the cells the petitioner computes
   another way (36).  Before, the draft rules recomputed the order's approved carrying costs.
   The prose remains: its figures are traced (increment 93), not rewritten.

**A decision for the operator — which petition is filled next round.**  The fill map and the
bindings are tied to the FY2026-27 workbook's layout (one column per year and voice).  Filling the
same layout with new figures works as built.  A FY2027-28 petition shifts every year column by one
(FY2026-27 becomes the APR year, FY2027-28 the ARR year), and the bindings would first have to be
moved a year — not yet done.  Until that is decided, the application is being made ready for a
workbook in the FY2026-27 layout.

Everything the fill writes comes from **draft rules, none approved, no clause verified**: a filled
workbook is a working draft for the petitioner and the reviewer, never a filing (R-APP-4).
