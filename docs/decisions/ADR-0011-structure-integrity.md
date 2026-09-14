# ADR-0011 Structure integrity: normalisation, clause outlines, grid integrity, gated stage

Status: accepted (2026-09-14)

## Decision

- **One normalisation module** (`tariff_api.normalise`, `NORMALISE_VERSION`) with a rule id
  per transformation recorded on every value.  It parses currency prefixes, paise words,
  unit suffixes, `/-`, Indian grouping, stray spaces, signed percentages, parenthesised
  negatives and bracketed secondary figures, and maps `Nil`, `-`, `NA`, blank and bare
  markers to value states — none of them to `0`.  It never converts paise to rupees and never
  guesses a unit: a value with no unit in its own text is returned without one.  `Nil` is
  state `zero` with no numeric value and the flag `nil_word`, so it can be shown as "nothing
  charged" without ever being a number.  Slab labels parse to bounds with inclusivity
  `explicit` / `inferred` / `ambiguous`; adjacent slabs that both claim a boundary or leave a
  gap are `ambiguous` and routed.
- **Clause outlines** (`tariff_api.clause_outline`) for prose-structured schedules: the
  numbered hierarchy is kept as titles keyed by depth so state carries across pages; `PLUS`
  is a connector, `ALTERNATIVELY` increments the alternative index and a sibling clause
  closes the group; roles come from a title vocabulary in which `TIME OF USE DISCOUNT` and
  `TIME OF USE CHARGES` map to different roles with opposite signs; two-column lines bind
  each value to its column header as a metering-type dimension; a `BILLING DEMAND` clause is
  a condition with its amounts as parameters, never a value; power-factor lines keep the
  first percentage as the component and the thresholds as parameters.
- **Grid integrity** (`tariff_api.grid_integrity`): header path per column from all header
  rows with leftward span inheritance; label columns are every mostly non-numeric column;
  row path with merged-cell propagation, including across a page break for a continuation
  whose label was merged; header inheritance for a heading-less continuation with the same
  column count; unit binding in the order cell → header → row-unit column → title →
  footnote with the source recorded, combining currency and denominator from different
  sources (KERC); footnote markers attached to their text; every propagation and every
  failure is a flag on the cell.  A cell is *resolved* only with a header path, a row path
  and a unit.
- **A gated stage** `localised → gridded` builds these representations only from regions a
  reviewer confirmed and only from `approved_schedule` / `approved_summary`; it refuses to
  run otherwise and lists the regions it skipped.  The reviewer's decision queues it; a new
  decision re-runs it and replaces the rows.

## Consequences

- Milestone 4 candidates cite `structure_cells` / `clause_values` rows (page, grid, row,
  column or clause path), never page text.
- Row-label indentation is not available from the readers, so stacked sub-labels are
  reconstructed from empty-cell propagation only (S13, recorded as a limitation).
- Triage rules moved to v2 (small ruled grids are tables); pages triaged under v1 re-triage
  on the next run and their parse artefacts are written beside the old ones.
