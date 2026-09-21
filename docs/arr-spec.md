# ARR specification (Milestone 12 — ARR foundation)

Status: **specification and taxonomy only** (2026-09-21).  Authorised scope: distribution
and transmission licensees; UPERC, KERC and GERC first; three financial years plus the
multi-year (MYT) control-period orders; the tariff regulations mapped to every line; a
what-if engine limited to the power purchase mix.  The master prompt's Milestone 12 says
"specify ARR scope before implementing calculation or filing engines"; this is that
specification.  Nothing here changes a tariff fact or the tariff pipeline.

Data: [`packages/arr-taxonomy/`](../packages/arr-taxonomy/README.md) (taxonomy v1,
commission mappings v1 skeletons).  Decision record: ADR-0017.

## 1. What a fact is

An ARR fact answers one question: for this licensee, this line item, this financial year,
as decided in this order, what number did the commission print, in which voice?

| Field | Meaning |
| --- | --- |
| `utility` | The licensee (distribution or transmission); its `licensee_kind` comes from the registry |
| `line_code` | A taxonomy code (`C.OM.EMPLOYEE`, `E.LOSS.DIST_PCT`, …); stable for ever |
| `fiscal_year` | `FY2026-27` |
| `value_type` | The voice: `petitioned`, `approved`, `provisional_true_up`, `final_true_up`, `actual`, `control_period` |
| `as_of_order` | The source document that printed it.  Order N approves FY(n); order N+1 trues it up provisionally; order N+2 finally.  All three are kept; nothing is overwritten |
| `stated_value`, `stated_unit`, `column_label` | Exactly as printed, with the column heading that named the year and voice |
| `canonical_value`, `canonical_unit` | INR crore for money, MU for energy, percent, MW, INR per kWh; the conversion applied is recorded |
| `basis` | Optional: `normative` or `actual`, where the order prints both for one line |
| `category_code` | Only for `by_category` lines (sales, transmission sharing): the tariff category or the user DISCOM |
| `evidence` | Page, table, row, column, cell text, as for every candidate today |
| `reasoning_quote` | A verbatim sentence from the commission's analysis with its own page and line; grounding is mechanical, as for assessments (ADR-0016) |
| `reason_category` | `normative`, `prudence_check`, `audited_accounts`, `carried_forward`, `disallowed`, `deferred`, `not_stated`: proposed by the model, approved by the reviewer, never without the quote |
| `regulation_clause` | The clause of the tariff regulation that governs the line, from the commission mapping |
| `derivation` | For computed lines: the formula, the input facts and the printed comparison (the VAL-07 pattern) |

The identity is `(utility, line_code, fiscal_year, value_type, as_of_order[, category_code])`.
Disallowance is `petitioned − approved`, computed on demand, never stored as a reading.

## 2. The taxonomy

Three levels, stable codes, no commission-specific structure.  Leaves are what orders
print; roll-ups are computed and reconciled against printed totals.  Branches:

- **`E` energy (distribution):** sales by category, open-access drawal, distribution loss,
  energy input at the distribution periphery, intra- and inter-state transmission losses,
  energy requirement at the state periphery, power purchase quantity by source class
  (own, central, state genco, IPPs, renewable by technology, short-term, banking, other),
  surplus sale, and the energy balance.
- **`T` transmission-only:** energy handled, availability, capacity, the approved
  transmission charge (annual total and rate as printed), SLDC fees, and the sharing of
  charges among DISCOMs.
- **`C` costs (shared):** power purchase cost by source class and fixed/variable split,
  transmission and SLDC charges, O&M (employee, R&M, A&G, terminal benefits), depreciation,
  interest on loans, on working capital, on consumer security deposits, other finance
  charges, return (RoE or RoCE, one per commission and period), income tax, contingency
  reserve, bad debts, gain/loss sharing, other expenses (RPO, DSM, smart metering), prior
  period items, carrying cost, and the total.
- **`L` less-items:** non-tariff income, income from other business, open-access income
  (wheeling, CSS, additional surcharge), other.
- **`R` result:** net ARR, revenue at existing and approved tariff, subsidy, revenue gap,
  cumulative gap, regulatory asset opening and closing, gap recovery, average cost of
  supply, average billing rate, average tariff change.
- **`K` capital:** capex, capitalisation, GFA opening and closing, funding split, loan
  roll-forward, equity base, working capital, and the rates (RoE, interest, depreciation).
- **`X` detail tables:** station-wise power purchase, loan-wise schedule, scheme-wise
  capex, category-wise sales.  Their own shapes; they roll up into the leaves.

Every branch has an `OTHER` leaf so an unrecognised printed line lands somewhere visible.
The full list with aliases is `taxonomy.json`; generic aliases live there, commission words
live in the mapping.

## 3. The commission mapping

Per commission, per regulation period, versioned, reviewer-confirmed, exactly like a
reading profile: licensees; the regulations with their control periods and the source id
of the regulation document once uploaded; `return_basis` (RoE or RoCE); `gap_convention`
(before or after subsidy); unit convention; the orders expected with the years and voices
each decides; chapter cues; year-column and voice-column patterns; label aliases;
regulation clauses per line; and the `unplaced` list.

The hand-mapping pass is the first deliverable: from the exported page text of one order
per commission, every printed ARR line is placed or listed as unplaced.  The reviewer
decides each unplaced line (alias, new leaf, or not an ARR line).  Only then does the
mapping's status move from skeleton to confirmed and the pipeline work start.

## 4. Identities (validators)

`ARR-I1` … `ARR-I12` in `taxonomy.json`: total equals the sum of components; net ARR
equals total less the less-items; gap equals ARR less revenue (and subsidy, per
convention); energy input equals sales over one minus loss; power purchase cost and
quantity roll up from stations; the energy balance closes; ACoS; fixed plus variable;
loan roll-forward; the DISCOM's intra-state transmission charge against the TRANSCO
order's sharing table (cross-order); the true-up chain across orders (cross-order); sales
roll up from categories.  Blocking identities block publication of the chapter's facts;
advisory ones are findings.  Tolerances are printed-precision tolerances, in the file.
An identity never corrects a value.

## 5. Sources and registry changes

- `source_documents.order_type`: `tariff_order`, `arr_true_up_order`, `myt_order`,
  `mid_term_review`, `regulation`, `regulation_amendment`, `other`; and `decides`, the
  list of `{fiscal_year, value_type}` the order determines, chosen on the upload form.
- `utilities.licensee_kind`: `distribution` | `transmission` | `generation` (generation is
  registered, not in scope).  Registry additions: UPPTCL, KPTCL, GETCO.
- Regulations are sources of `order_type=regulation`: parsed into clauses with the existing
  clause-outline machinery, linked from mapping entries and facts, **never extracted for
  numbers**.
- The model budget per order rises for ARR orders (Terraform variable, dev first).

## 6. Pipeline

Localisation extends to ARR chapters: each chapter is a region with the branch it serves
and the reviewer checkpoint that exists today.  A chapter agent stage reads a chapter's
grids and text with the same two channels (rules over grid cells and clause lines; the
model over page images), writes candidates in the existing envelope with the ARR payload,
and the validators above run in the validate stage.  Sub-agents per chapter share only the
artefact store (page text, cells, images, BM25 passages); no agent sees the raw PDF alone.
KERC's chapter-5 tables are raster images (Part E hazard 14): grids from OCR word boxes
(`grid_from_ocr_pending`) are a prerequisite for KERC ARR reading and are scheduled before
the KERC chapter stage.

## 7. Review screen

The reviewer never navigates by page.

- **Left rail:** the chapters in document order with progress per chapter, then the
  identities' status per chapter.
- **Chapter grid:** line items down, financial years across, each year split into the
  printed voices (petitioned / approved / true-up); a cell is one fact with its status,
  agreement badge and Approve / Reject / Note, as on the tariff table.
- **Page panel pinned to the chapter:** it follows the table the reviewer is on, with the
  cited table outlined; "next table" and "next unresolved" walk the chapter.  The
  rendered-evidence gate holds: no approval without the page having been shown.
- **Identity failures on the chapter header**, naming the lines involved, never buried on
  a cell.  The reasoning quote shows under the cell with its reason category to confirm.
- The tariff table takes the same rail and pinned panel afterwards.

## 8. What-if engine (power purchase mix only)

A scenario takes one reviewed, published order as its base and lets the user change the
power purchase mix: the MU per source class (or per station where `X.PP.STATION` was
reviewed), keeping total energy input, losses and every other line at their approved
values.  The engine recomputes `C.PP`, `C.TOTAL`, `R.ARR`, `R.GAP`, `R.ACOS` and the
average tariff change needed to close the gap over approved sales.  Rules:

- **Fixed cost is retained by default.**  Reducing a station's or class's energy does not
  remove its fixed (capacity) charge; only the variable cost moves, at the class or station
  variable rate.  Where the order does not print the split, the user must choose
  "all-variable" or "fixed retained at x%" and the choice is stored on the scenario.
- **Rates are the order's own** (`C.PP.x / E.PP.QTY.x`, or the station rate); no market
  price is assumed.  Adding energy beyond a class's approved quantity requires the user to
  name the rate.
- **Every result is a model estimate**, labelled as such, stored as a scenario version with
  its assumptions and base order, kept in its own tables, never a fact, never in the
  explorer's fact views, never citable as a source.
- Losses, O&M, capital and the regulatory asset are not levers in this version.

## 9. Gate for the increment after this one

The specification is accepted when the three hand-mappings exist with their unplaced lists
reviewed; that gate needs the three exported orders in `exchange/` and a reviewer day per
commission.  Pipeline code starts only after that gate.
