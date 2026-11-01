# ADR-0021 The ARR track's outcome is a reconciled filing package, governed by binding requirements

Status: **proposed** (2026-11-01), awaiting the operator's approval.  Builds on ADR-0017 …
0020; on approval, amends ADR-0018 (scope "draft only") and ADR-0019 (private sources on the
roadmap).

## Context

The operator reviewed the consolidated master prompt (`docs/product-master-prompt.md`) and
found it strong on reading orders and preserving evidence, weak on preparing, approving and
maintaining a complete filing.  The named gaps: utility data intake; regulatory
applicability per proceeding and year (one petition can span regulatory regimes); calculation
depth (schedules, not taxonomy lines); true-up treatment; filing completeness; a case-level
approval workflow distinct from evidence review; enterprise isolation and recovery; and
acceptance by reproducing a real filing rather than by passing tests.  The review also noted
that the master prompt let code prevail over the document, so a bug could become the
specification.

## Decision (proposed)

1. **Outcome.**  For the ARR track the product's outcome is *a complete, reconciled,
   regulation-specific petition package prepared from the utility's records, its regulatory
   history and approved assumptions, with every material claim reproducible and
   accountable.*  Reading orders correctly stays the outcome of the tariff-intelligence track
   and a dependency of this one.
2. **Binding requirements.**  `docs/arr-filing-requirements.md` binds the ARR filing
   product; `docs/requirements-matrix.md` tracks each requirement to its commission/years,
   source, implementation, acceptance test and approval.  Specifications and approved ADRs
   are the requirement; **code is the implementation** — a difference is a defect in the code.
3. **Regulations become executable rules** (versioned data with clause, typed inputs,
   formula, rounding, exceptions, worked examples, approver), selected by an approved
   applicability decision per proceeding and year.  The generic plan is for exploration and
   cannot make a case ready for sign-off.
4. **Evidence review ≠ filing approval.**  A case-level workflow (preparer, regulatory and
   finance checkers, approver with delegated authority, four-eyes, sign-offs on content
   hashes, invalidation on change) is added.
5. **Scope S-1:** an approved, submission-ready package and a record of the externally filed
   version; submission stays manual.  Until the operator approves S-1, exports remain
   watermarked drafts.
6. **Private utility data and security move into the first release** (org-owned records and
   sources; isolation tested across every channel; local identity refused when private data
   exists; demo mode for public demonstrations).
7. **Milestone 13 = one commission, one licensee, one historical filing reproduced and
   independently signed off** (UPERC / NPCL, ARR petition FY2026-27) before more geography,
   Q&A, voice or interface work.

## Consequences

- New data packages: `packages/arr-rules/` (rules), filing checklists per commission;
  migrations for proceedings, applicability decisions, utility records, sign-offs, filings.
- The roadmap in the master prompt is reordered; Q&A, voice, the scenario engine and new
  states wait for milestone 13.
- Milestone 13 is blocked until the NPCL petition package, its underlying records and a named
  independent checker are available to the build.
