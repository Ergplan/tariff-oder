# ADR-0017 ARR foundation: taxonomy as data, facts versioned by order, what-if kept apart

Status: accepted (2026-09-21), authorising the specification and data only

## Decision

- **The ARR taxonomy and the commission mappings are data**, in `packages/arr-taxonomy/`,
  versioned like reading profiles, reviewer-confirmed before use.  Line codes are stable
  for ever; a wrong item is deprecated, never renamed.
- **A fact is identified by `(utility, line_code, fiscal_year, value_type, as_of_order)`.**
  Petition, approval, provisional and final true-up of one year are separate facts; later
  orders add facts, never overwrite.  Disallowance is computed, never read.
- **Printed unit stays on the fact; canonical units are INR crore and MU.**
- **Arithmetic identities are validators.**  They flag, never correct.
- **ARR facts use the existing candidate envelope** (evidence, two channels, risk tags,
  review decisions, publication), with an ARR payload, so the reviewer boundary and the
  audit trail carry over unchanged.
- **Regulations are sources, parsed into clauses, never extracted for numbers.**
- **The what-if engine changes only the power purchase mix**, retains fixed cost by
  default, uses the order's own rates, and stores results as labelled model estimates in
  their own tables.
- **No agent framework is adopted for this.**  The chapter-agent pattern (plan, one
  sub-agent per chapter, shared artefact store) is built on the existing worker and
  provider adapter; a framework is reconsidered only if run debugging becomes the
  bottleneck.

## Why

The value of the product is an evidence-backed, versioned ARR history across commissions,
not a summary.  Every choice above keeps a number traceable to a page, a voice and an
order, and keeps user scenarios from ever being mistaken for decisions.

## Consequences

- Registry gains `licensee_kind` and the three transmission licensees; sources gain
  `order_type` and `decides`.
- KERC ARR reading waits on grids from OCR word boxes.
- The hand-mapping pass, on exported page text, is the gate before pipeline code.
