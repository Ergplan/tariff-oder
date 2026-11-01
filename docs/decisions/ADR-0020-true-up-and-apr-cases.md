# ADR-0020 True-up and APR cases: actuals against the approval

Status: accepted (2026-11-01).  Builds on ADR-0018 (ARR read, formulate, file) and ADR-0019
(the client application).

## Context

A licensee's ARR process is not only the projection of the next year (annual ARR) or a
control period (MYT).  Every year it also files:

- a **true-up** of a past year: its audited actuals against what the Commission approved for
  that year, with the reasons for each difference; the Commission then allows, disallows or
  defers each difference;
- an **annual performance review (APR)** of the running year: actuals so far and estimates for
  the rest, against the approval.

ADR-0018 keeps four kinds of number apart (facts, assumptions, projections, scenarios).  A
true-up adds a kind those four do not cover: the licensee's **actual**, which comes from its
own records (audited accounts, regulatory accounts, a published petition), not from an
order.  It is not a fact (no person reviewed it against a commission's order) and not an
assumption (it is not chosen).

## Decision

1. **Case kinds `true_up` and `apr`** beside `annual_arr` and `myt`.  The year trued up is
   the case's base year and its only target (`final_true_up` / `provisional_true_up`).  No
   formulation plan is needed.
2. **The approved figure** of each line is the current reviewed, published ARR fact of voice
   `approved` for that year (newest order first), with its order and page.  A line with no
   reviewed approval says so; nothing is approved by the application.
3. **The actual** is a new record, `arr_actuals`, one per line per case, entered by a named
   user with its source, of four kinds:
   - `fact` — a current reviewed fact of voice `actual` for the line and year (a true-up
     order that prints the licensee's actuals);
   - `document` — a page of a registered source: the excerpt must be on the page and the
     value must be printed in the excerpt (thousands separators ignored).  Grounding is
     mechanical, as for regulation clauses (ADR-0018);
   - `statement` — a document the application cannot see, named with an optional page and a
     rationale.  Labelled **unchecked** on the screen, in the statement and in the draft;
   - `estimate` — APR only: the rest of a running year, with its rationale.  It is an
     assumption by another name and is labelled an estimate everywhere.
   The value is kept as written (stated value and unit) and converted to the canonical unit
   with the taxonomy's conversions; a unit with no conversion blocks the line.
4. **The statement** is computed, never stored as facts: per line the approved figure, the
   actual, the variance (actual less approved, Decimal, same canonical unit) and a status
   (`complete`, `actual_missing`, `approved_missing`, `unit_mismatch`, `actual_unconverted`);
   the ARR identities run over the actual column (a total that does not add up is a
   blocking finding); an input hash over every approval and actual.  Totals are the figures
   entered, never summed by the application.  **The variance is not an amount the
   Commission has allowed**, and every screen and draft says so.
5. **Freeze and draft.**  A statement freezes only when every approved line has an actual,
   no unit is mismatched or unconvertible and no blocking identity fails; freezing checks
   that the inputs still hash the same.  A draft is rendered only from a frozen statement
   whose inputs still hash the same (a newly published order or a changed actual means
   revise and freeze again).  The draft (DOCX + XLSX, `filing_drafts.case_id`) carries the
   watermark, names every unchecked figure and estimate, leaves the reasons for each variance
   to the licensee as bracketed prompts with no numbers, and traces every number: `fact`
   (approved, order and page), `actual` (its source), `variance` (the two trace ids it is
   computed from).  Revising a case thaws the actuals; frozen statements stay in the audit
   and in each draft's trace.
6. **Privacy.**  Actuals belong to the case and so to the organisation (ADR-0019 rules).  A
   `document` actual can cite only a registered source, and sources are shared by the desk;
   a client's private accounts are therefore cited as a `statement` until sources can be
   owned by an organisation (not built; see consequences).

## Consequences

- The true-up draft uses a built-in layout (`true-up-builtin` v1, status `builtin`), not a
  commission's prescribed true-up formats; commission formats as data, like the petition
  templates of ADR-0018, are later work.
- The application does not judge prudence, controllability or normative ceilings; those are
  the licensee's argument and the Commission's decision.  Normative checks against
  regulation parameters (for example O&M norms) are later work and will cite the clause.
- Organisation-owned sources (a client's private documents, grounded like any other) are
  later work; until then the unchecked label carries the risk honestly.
