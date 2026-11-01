# ARR filing requirements — binding specification

**Status: PROPOSED (2026-11-01), awaiting the operator's approval.**  Once approved, this
document **binds** the ARR filing product: where it conflicts with
`docs/product-master-prompt.md`, `docs/arr-spec.md`, `docs/prompts/arr-build-prompt.md` or
ADR-0018 … 0020, this document wins, and the conflict is recorded in ADR-0021.  Code is the
implementation, never the requirement: **a difference between code and an approved
requirement is a defect in the code**, not a change to the requirement.

Origin: the operator's review of the consolidated master prompt (2026-11-01), which scored
it 8/10 as an architecture document and 5/10 as a standalone enterprise ARR filing
specification, and named the gaps this document closes.  Every requirement has an ID; its
commission, years, source, implementation, acceptance test and approval status are tracked
in [`docs/requirements-matrix.md`](requirements-matrix.md).  A requirement is **done** only
when its acceptance test passes on real data and its approver has signed it off.

---

## 0. The outcome (replaces "reading the order is the product" for the ARR track)

> **Prepare a complete, reconciled, regulation-specific petition package from the utility's
> records, its regulatory history and approved assumptions, with every material claim
> reproducible and accountable.**

Historical orders are **context and constraint** (what was approved, trued up, disallowed),
not the source of the filing.  The filing is built from the utility's **current records**:
audited accounts, sales, power purchase, assets, loans, capital expenditure.  Reading orders
correctly remains the product of the *tariff-intelligence* track and a dependency of this one.

**Scope of the output (decision S-1, for the operator to confirm):** the product produces an
**approved, submission-ready package** (every mandatory format, schedule, attachment and
declaration, signed off inside the application) and **records the externally filed version**
(filing date, petition number, the exact bytes filed, the commission's later queries and
deficiency notes).  Submission itself stays manual: the software never files.  Until S-1 is
approved the product's stated scope remains "draft preparation" and every export stays
watermarked as a draft.

## 1. Concepts this specification adds

| Concept | Meaning |
|---|---|
| **Proceeding** | what is being filed: `annual_arr`, `myt` (control period), `true_up`, `apr`, `mid_term_review`, or a combined petition (e.g. true-up of Y−2 + APR of Y−1 + ARR of Y) — one petition, several proceedings |
| **Regulation version** | one published regulation (title, notification date, control period) plus its amendments, each a registered source parsed into clauses |
| **Rule** | one executable calculation requirement derived from a clause (§3) |
| **Applicability decision** | which regulation version and which rules govern *this* licensee, *this* proceeding, *this* financial year — recorded, sourced and approved by a person (§2) |
| **Utility record** | a dataset the utility supplies (trial balance, audited accounts, sales ledger, power-purchase bills, fixed-asset register, loan schedules, capex plan), private to its organisation (§6) |
| **Schedule** | one financial schedule of the petition (§4), computed by rules from facts, records and assumptions |
| **Filing package** | every schedule, format, narrative section, attachment and declaration a commission requires, with its checklist (§7) |
| **Sign-off** | a named person's approval of a defined scope at a defined content hash (§8) |

## 2. Regulatory applicability (R-APP)

- **R-APP-1** For every proceeding and financial year in a case, the case records **one
  applicability decision per regulation role** (distribution tariff, MYT, power purchase, open
  access, …): regulation version, amendments in force, the clause that establishes the
  applicable period, and the person who approved it.
- **R-APP-2** Applicability is decided **per proceeding per year, not per case.**  A single
  petition can span regulatory regimes — for example a true-up of a year governed by the
  previous control period's regulations filed together with the ARR of a year governed by the
  next.  The engine selects rules by the year's decision, never by the case's.
- **R-APP-3** Amendments are versions with effective dates; a rule cites the amended clause
  in force on the relevant date.  Conflicting authorities (an order deviating from a
  regulation, a removal-of-difficulty order, an appellate (APTEL) judgment, a commission
  direction in an earlier order) are recorded as **exceptions** with their source and
  precedence, decided by a person.
- **R-APP-4** The **generic plan and any unapproved mapping are for exploration only.**  A
  case cannot reach `ready_for_signoff` (§8) unless every line of every schedule is computed
  by a rule whose applicability is approved for that year.
- **R-APP-5** Every applicability decision is visible in the package's annex (regulation,
  clause, page) and changes to it invalidate dependent sign-offs (R-SIGN-5).

## 3. Executable, versioned rules (R-RULE)

- **R-RULE-1** A rule is data (in `packages/arr-rules/<commission>/<regulation>.vN.json`),
  not code, with these fields: `id`; regulation version; clause reference (source id, page,
  verbatim excerpt — grounded mechanically, as for regulation clauses today); applicability
  (commission, licensee kinds, proceeding kinds, year range); **typed inputs** (each with a
  dimension and unit, and where it comes from: fact, utility record, assumption, another
  rule); the **formula** in a restricted, side-effect-free expression language; **rounding
  policy** (§5); **exceptions**; **worked examples** (from orders or the regulation, with
  expected outputs) that run as tests; **approver** and approval date; status (`draft`,
  `approved`, `superseded`).
- **R-RULE-2** A rule's worked examples must pass before it can be approved; an approved
  rule's examples run in CI for ever.
- **R-RULE-3** Rules are versioned like mappings: a change is a new version; a case records
  the exact rule versions it used; a frozen case recomputes identically for ever.
- **R-RULE-4** No rule may be approved by an automated process (AGENTS.md rule 1).
- **R-RULE-5** The current formulation plans (`carry_forward`, `escalate`,
  `quantity_x_rate`, …) remain as **forecasting heuristics** for exploration and for inputs
  the regulations leave to the petitioner; they are never presented as the commission's
  method unless an approved rule says so.

## 4. Financial schedules (R-SCH)

The taxonomy says what a number *is*; a schedule says how it *must be calculated*.  For the
first supported commission every schedule below is specified as rules (§3) before it is
implemented; for others, "wherever applicable" is decided per commission and recorded.

| ID | Schedule | Minimum content |
|---|---|---|
| R-SCH-1 | Sales and consumers | category- and slab-wise sales (MU), consumers, connected load; historical CAGR; projection method per category with its rationale |
| R-SCH-2 | Energy balance and losses | input at periphery, distribution / transmission losses, inter-state and intra-state losses, loss trajectory per regulation, bulk and surplus sales; must close (ARR-I6) |
| R-SCH-3 | Power purchase | station / source-wise quantity, fixed and variable charges, other charges, rates, merit order where required, RPO compliance, short-term purchases and sales, true-up of power purchase; rolls up to C.PP (ARR-I5, I8) |
| R-SCH-4 | Transmission and SLDC | intra-state transmission per the transmission order's sharing, inter-state charges, SLDC fees |
| R-SCH-5 | O&M | employee, R&M, A&G separately; norms per regulation (base year, indexation by CPI/WPI weights, growth factors), pay-revision and other uncontrollable items, efficiency factors |
| R-SCH-6 | Capital investment and capitalisation | capex plan by scheme; capitalisation by year and asset class with commissioning dates; funding: equity, debt, grants, consumer contributions |
| R-SCH-7 | Gross fixed assets and depreciation | opening GFA, additions, retirements by asset class; rates per class; limits (salvage, cumulative caps) per regulation; assets funded by grants and consumer contributions excluded; pro-rata for mid-year commissioning where the regulation says so |
| R-SCH-8 | Loans and interest | normative loan opening, additions (normative debt share of capitalisation), repayment (per regulation, e.g. equal to depreciation), closing (ARR-I9); weighted average rate; finance charges |
| R-SCH-9 | Return | normative equity (share of capitalisation, cap), rate, tax treatment / grossing-up — or return on capital employed where the commission uses it |
| R-SCH-10 | Interest on working capital | each component as the regulation defines it (e.g. receivables of N months, O&M of N months, maintenance spares %, less security deposits), the interest rate reference per regulation |
| R-SCH-11 | Non-tariff and other income | categories; treatment of income from other businesses per regulation |
| R-SCH-12 | Revenue at existing tariff | category-wise from R-SCH-1 sales × the current schedule's charges (fixed, energy, minimum, ToD), reconciled to billed revenue for actual years |
| R-SCH-13 | Subsidy and gap | state subsidy, revenue gap per the gap convention, carrying cost on gaps per regulation, regulatory assets and their amortisation, accumulated gap across years |
| R-SCH-14 | ARR summary and ACoS | every line traceable to its schedule; ACoS = ARR / sales with dimensional conversion (§5) |
| R-SCH-15 | Tariff proposal | category-wise proposed charges, revenue at proposed tariff, cross-subsidy levels against the regulation's band |

- **R-SCH-16** Cross-schedule reconciliation: every figure that appears in two schedules
  (e.g. depreciation in R-SCH-7 and the ARR summary; capitalisation in R-SCH-6, 7, 8 and 9)
  is one value, computed once and referenced; a reconciliation report lists every such link
  with its value in each place.

## 5. Numerics (R-NUM)

- **R-NUM-1** All money and energy arithmetic uses decimals with explicit precision; no
  binary floating point anywhere in a computed schedule.
- **R-NUM-2** Every quantity carries a **dimension and unit**; a formula that combines units
  must convert explicitly, and a dimensionally inconsistent formula is refused at rule
  approval.  Example: ACoS (Rs/kWh) = ARR (Rs crore) × 10⁷ / (sales (MU) × 10⁶) = ARR / sales
  × 10.
- **R-NUM-3** **Rounding policy per rule**: intermediate precision, the step at which
  rounding happens, the mode (half-up as commissions print, unless a regulation says
  otherwise), and the printed precision per format.  Totals are computed from unrounded
  components and then rounded, unless the commission's format sums printed figures — in which
  case the rule says so and the difference is reported.
- **R-NUM-4** Rules form a **dependency graph**; cycles are refused (or resolved by an
  explicit iteration rule, e.g. IoWC depending on receivables depending on ARR, with a
  convergence tolerance); recomputation is topological and deterministic.
- **R-NUM-5** Reconciliation tolerances are per check and recorded on the result (e.g. exact
  to printed precision for totals; ±0.01 crore for derived lines).

## 6. Utility data intake and private data (R-DATA)

- **R-DATA-1** Imports for: trial balance / audited accounts (with schedules), category-wise
  sales and billing, power-purchase bills and settlements, fixed-asset register, loan
  schedules, capex plan and capitalisation, employee cost; from spreadsheet templates per
  commission and from registered documents (with grounding).
- **R-DATA-2** Each import is mapped to the taxonomy and schedules by a recorded mapping,
  validated (types, units, periods, completeness), and **reconciled to the audited totals**
  it claims to break down; a mismatch blocks use.
- **R-DATA-3** Corrections are new versions with a reason and an author; nothing is edited in
  place; every schedule cites the record version it used.
- **R-DATA-4** Utility records and private documents are **owned by an organisation** and
  are never part of the shared corpus, never visible to the desk except an administrator
  under an audited, time-boxed access grant, and never used to train or tune anything.
- **R-DATA-5** This is **first-release scope**, not roadmap: no real utility can prepare a
  filing without it.

## 7. True-up and APR (R-TU)

- **R-TU-1** Per line: approved (reviewed fact, with order and page), actual (utility
  record, reconciled to audited accounts), **normative** (the rule's computation on actual
  drivers, e.g. normative O&M on actual indices, normative interest on actual capitalisation),
  and **claimed** — with the rule that decides which of these is claimable.
- **R-TU-2** Controllable vs uncontrollable classification per regulation; sharing of gains
  and losses on controllable items per regulation.
- **R-TU-3** Prior recoveries and adjustments: amounts already allowed provisionally (APR),
  regulatory surcharges collected, earlier true-up decisions, deferred items — so a year is
  never claimed twice and never lost.
- **R-TU-4** Carrying cost on the true-up gap per regulation, from the right year to the
  right year, at the regulation's rate.
- **R-TU-5** Treatment across years: the chain of decisions on one year (approved → APR →
  final true-up → review/appeal outcome) is one record (ARR-I11), visible in the package.

## 8. Case approval workflow (R-SIGN)

Evidence verification (a reviewer approved that a number was **read** correctly) is not
filing approval.  Filing approval establishes that the **regulatory treatment** is right,
**every required input and schedule** is present, the **claim** is justified, and an
**authorised person** approved the package.

- **R-SIGN-1** Case states extend to: `preparing → in_check → ready_for_signoff → approved →
  filed → (queried → responded) → order_received`; `revise` reopens from any state and keeps
  history.
- **R-SIGN-2** Roles inside an organisation: **preparer**, **regulatory checker**,
  **finance checker**, **approver** (delegated authority, configurable per organisation:
  e.g. claims above a threshold need a second approver); four-eyes: a person cannot check or
  approve what they prepared.
- **R-SIGN-3** Sign-offs are per scope (a schedule, the applicability decisions, the
  narrative, the whole package) and record the person, time, comment and the **content hash**
  of exactly what they signed.
- **R-SIGN-4** `approved` requires: every schedule signed by both checkers, the completeness
  checklist complete (R-PKG), zero unresolved critical validation findings, and the
  approver's sign-off of the package hash.
- **R-SIGN-5** Any change to an input, assumption, rule version, applicability decision or
  narrative **invalidates every sign-off whose scope depends on it** (via the dependency
  graph), and says which and why.
- **R-SIGN-6** After `filed`: the exact filed bytes and the filing reference are stored; the
  commission's queries, deficiency notes and the case's responses are recorded against it;
  the eventual order is linked and read back into facts (closing the loop to the history).

## 9. Filing completeness (R-PKG)

- **R-PKG-1** A **filing checklist per commission and proceeding**, as versioned data:
  every mandatory format (by its commission number), schedule, narrative section,
  attachment (audited accounts, auditor's certificates, board resolution, affidavit,
  fee proof, index), declaration, and cross-reference; with its source (the regulation or
  the commission's practice direction).
- **R-PKG-2** The package view shows each item: present, computed, attached, signed, or
  missing — and the package cannot be approved with a mandatory item missing.
- **R-PKG-3** Narrative ↔ spreadsheet reconciliation: every number in the narrative is a
  reference to a schedule cell, never typed; a report proves narrative and formats agree.
- **R-PKG-4** Cross-references (format A refers to format B line X) are checked
  mechanically.

## 10. Enterprise operation and security (R-SEC)

- **R-SEC-1** Tenant isolation is enforced and **tested** across document bytes, object
  keys, search indexes, exports, jobs and their artefacts, caches, logs and telemetry — not
  only API lookups.  An isolation test suite attempts cross-tenant access through every
  channel.
- **R-SEC-2** Production identity: OIDC / IAP with MFA; the local identity profile
  (`LOCAL_WEB_USER`, header identity) is refused at startup when any organisation-private
  data exists or when the profile is `gcp`; a **demo mode** flag forces a banner, a
  fixture-only dataset and refuses private uploads.  The current public VM demonstration
  runs in this mode or is withdrawn.
- **R-SEC-3** Recovery targets (proposed; operator to approve): RPO ≤ 15 minutes (PITR),
  RTO ≤ 4 hours; a **restore drill** at least quarterly, its result recorded.
- **R-SEC-4** Operational monitoring: job failures, queue age, error rates, cost per order,
  storage growth, with alerts to a named on-call; audit export per organisation.
- **R-SEC-5** Encryption at rest and in transit; secrets only via the secrets adapter;
  retention and deletion per organisation on request, audited.

## 11. Acceptance (R-ACC) — what "done" means

Tests passing is necessary, never sufficient.  For the **first supported commission** the
release gate is:

- **R-ACC-1** One **historical filing reproduced end to end**: an actual, filed petition
  (the first target: **UPERC / NPCL, ARR petition FY2026-27**) regenerated from its
  underlying records (R-DATA) and regulations (R-RULE), and compared line by line with the
  filed petition: every line within the agreed tolerance (R-NUM-5), every difference
  explained in a reconciliation report.
- **R-ACC-2** **Independently signed off** by a named person who did not build it.
- **R-ACC-3** Every mandatory format and attachment of the checklist accounted for (100 %).
- **R-ACC-4** Every material output (any line on the ARR summary, and any figure ≥ an agreed
  threshold) traceable to its inputs and the applicable rule, in the package annex.
- **R-ACC-5** Narrative and spreadsheet totals reconciled within tolerance; zero unresolved
  critical validation findings.
- **R-ACC-6** Tenant-isolation suite and a backup-restore drill passed on the release
  environment.
- **R-ACC-7** Reading quality measured as **recall and completeness**, not only precision
  and identities: per order, required schedules found / required (schedule recall);
  lines read / lines in a human-keyed reference (line recall); correct year and licensee
  attribution (attribution accuracy) — because a table can reconcile perfectly and belong to
  the wrong year or licensee, or a whole schedule can be missing.

## 12. Order of work (proposed milestone 13)

**One commission, one licensee, one complete historical filing, reproduced and
independently signed off** — before more states, Q&A, voice or interface work.

1. Obtain the NPCL FY2026-27 petition package and its underlying records.  **Located
   (2026-11-01):** NPCL publishes both the FY2026-27 and the FY2025-26 petitions in full,
   with their records, on its website; the documents are listed in
   `packages/reference-filings/` and downloaded and hashed with
   `scripts/fetch_reference_filing.py` on the VM.  Being public, they are real shared
   sources; a client's unpublished records remain organisation-private (R-DATA-4).
2. Key the petition's formats as the **reference** (human-keyed, reviewed) — the target the
   reproduction is measured against.
3. Register the applicable UPERC regulations (all versions and amendments in force for the
   years covered) and record the applicability decisions (R-APP).
4. Write and approve the rules for each schedule (R-RULE, R-SCH), worked examples first.
5. Build intake for the records the schedules need (R-DATA), reconcile to audited accounts.
6. Compute, reconcile (R-NUM, R-SCH-16), assemble the package against the checklist (R-PKG).
7. Run the sign-off workflow (R-SIGN) and the acceptance gate (R-ACC) with an independent
   checker.
8. In parallel and first-release scope: R-SEC-1 isolation suite, R-SEC-2 demo-mode guard.

## 13. Out of scope

Electronic submission to a commission portal; legal advice or advocacy text beyond the
petition's factual narrative; predicting a commission's decision; bill computation.
