# ADR-0014 Publication transaction, published facts and the explorer

Status: accepted (2026-09-14)

## Decision

- **Published facts are a separate table with separate routes.**  `published_facts` and
  `published_evidence` are copied from the effective records of finally approved
  candidates at publication time.  The explorer router imports neither the candidate model
  nor the decision or evidence-view models, and a test reads its source to keep it so.  A
  candidate can therefore never appear in any explorer view or, later, in any Section 8
  tool, whatever its status.
- **A release is a transaction over a declared scope with an explicit completeness
  declaration.**  `whole_schedule` or an explicit `subset` (categories and/or charge
  families).  `complete` is refused while any required item is missing: an in-scope
  category with no approved fact, a network family with neither an approved fact nor a
  reviewed disposition, any open candidate (pending, awaiting second review, unresolved),
  or a source-level blocking finding.  `partial` must list every such gap by key with a
  reason and is labelled partial in every response and page that reads it; a partial
  release cannot be used to assert that no other condition applies.  Approved candidates
  that still carry blocking validator findings block publication until corrected or
  rejected.  A release with nothing publishable is refused.
- **Consequences are shown first and must still hold.**  The preview returns what would be
  published, what stands in the way, the prior release, and a token over (scope, source
  version, every in-scope candidate's id, version, status, second-review state).  The
  publish call must present the token and `confirm_consequences`; a decision or version
  change in between fails with `conflict_stale_version`.  `expected_source_version` is
  checked as well.
- **Releases are cumulative per source.**  Release *n* carries every fact publishable at
  that time (earlier facts included), becomes current, and marks release *n−1* superseded.
  Decisions on remaining candidates stay possible while the source is `published`;
  decisions on candidates that a release published are frozen (no further decision, no
  undo).  Republishing after a correction of a published fact is therefore a reprocess
  cycle, never an overwrite: approved history is never rewritten.
- **Citations are derived by backend code.**  Each published evidence row carries the PDF
  page, the printed page label resolved by triage, the primary-reader table ordinal, the
  row and column, the header, row and clause paths and the exact excerpt.  The API turns
  these into `CitationOut` (`table_id` = `p<page>-g<ordinal>`, `cell` = `r<row>c<col>`); the
  drill-down renders the cited page from the immutable bytes with the table outlined.  No
  model output ever becomes a page number.
- **Explorer views.**  Screen 5 (`/explorer/sources/{id}/tariff`): category tree,
  components, values with units and `value_state`, applicability, linked conditions,
  general conditions, citations, completeness banner.  Screen 6a
  (`/explorer/sources/{id}/network`): every network family with its published facts and
  derivation inputs (computed, cap, rule), or `coverage_insufficient` with the reviewed
  disposition when one exists.  A source without a current release returns
  `coverage_insufficient` with an explanation, never an empty success.
- **Cache invalidation.**  Explorer responses are computed from the current release on
  every request and carry the release id; there is no cache to invalidate yet.  When one
  is introduced its key must include the release id, so a new release invalidates by
  construction.
- **Fixture isolation.**  A release inherits the source dataset's fixture flag; the release
  list counts real and fixture releases separately and every fixture fact, banner and row
  is labelled.

## Consequences

- Section 8 tools (Milestone 7) read `published_facts` and `published_evidence` through
  the current release; comparison (Milestone 6) reads two releases and cites both.
- Coverage records (Section 5.2) are the release's checklist snapshot plus its gaps; the
  coverage dashboard (screen 1) can be built from `data_releases` alone.
- Supersede-a-source, reject-a-whole-schedule and delete-a-user confirmations (principle 5)
  follow the same preview-then-confirm shape when built.
- Structured interpretation of condition records and the reader-grid toggle in the review
  workspace remain open.
