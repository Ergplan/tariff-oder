# ADR-0013 Reviewer workflow: decisions, evidence-viewed enforcement, second review, undo

Status: accepted (2026-09-14)

## Decision

- **Decisions are rows, candidates carry state.**  `review_decisions` is append-only: one
  row per decision with the outcome, reviewer, the candidate version decided on, rationale,
  cause tag, the corrected record, the evidence views cited, client- and server-measured
  time, and `before`/`after` snapshots of the candidate's review state.  The candidate row
  holds the current state (`review_status`, `reviewed_record`, `reviewed_by`,
  `first_reviewer`, `second_review`, `decision_count`, `version`).  The extractor's `record`
  is never overwritten: a correction writes `reviewed_record`, and `effective_record` is
  what validators and (in Milestone 5b) publication read.
- **Evidence viewed is proven by the server, not declared by the client.**  The only way
  to obtain an evidence view id is `GET /candidates/{id}/evidence/{n}/image`, which renders
  the cited page (the cited primary-reader table outlined when its bbox is known), writes
  an `evidence_views` row for the identity that received the bytes, and returns the id in a
  response header.  `approve` and `correct` must cite views that belong to the deciding
  reviewer, for that candidate, within `evidence_view_max_age_seconds`, and that include
  the primary evidence (index 0).  A `pages_viewed: true` flag would be a claim; a view row
  is a record of what the API served.  Reject and unresolved need a rationale, not a view.
- **Stale versions never overwrite.**  `expected_version` is mandatory and must equal the
  candidate's current version; otherwise `conflict_stale_version` with the current version
  and status in `extra`.  Every decision and every undo increments the version.
- **Corrections are structured and attributed.**  A correction is a partial record over an
  allow-listed field set, merged onto the effective record and re-validated against the
  candidate schema (a non-decimal value or an unknown field is refused), plus a mandatory
  cause tag (`wrong_table`, `header_misbound`, `unit`, `ocr`, `footnote_missed`,
  `cross_reference`, `other`) and a mandatory evidence selection (indices into the existing
  references or new references).  The changed field names are recorded.  A correction
  re-queues the validation stage over the effective records; review state survives the
  re-run.
- **Second review is a policy, not a reviewer's choice.**  A first-round approval or
  correction moves the candidate to `awaiting_second_review` when the candidate is a
  material condition, a formula component, a correction of a channel disagreement
  (`second_review_material`), or carries `new_profile` — the first order read with a
  profile (`second_review_first_order`, default on).  The second reviewer must differ from
  the first; the second decision is final.  Reject and unresolved are final in round one.
- **Undo restores from the decision's own snapshot.**  Only the reviewer who took the
  latest decision on a candidate may undo it, only while the source is not published; the
  row stays, marked undone, so the correction history is intact.
- **Batch approval is a loop over single decisions.**  `POST /review/batch` refuses any
  candidate that is not pending, batch-routed, high-confidence, risk-free and finding-free,
  and still requires each candidate's own rendered evidence and version; items are decided
  one by one and a refused item never blocks the others.  The second-review policy applies
  unchanged.  There is no auto-approval path.
- **Queue order and checklist are derived, never stored.**  The per-order queue orders open
  candidates by risk (blocking findings, findings, channel disagreement, risk-tag count),
  then coverage impact (categories with no approved fact), then confidence, and says why
  each item sits where it does.  The checklist lists every rate-schedule heading in the
  inventory (a heading with no candidate is a visible gap), every (category, component)
  pair from the extraction, every network family with its disposition, and derives a status
  in which any open or unresolved candidate keeps the item off green.
- **Idempotent decisions.**  `Idempotency-Key` on the decision endpoint replays the original
  result for the same request and rejects a different one under the same key, through the
  same `idempotency_records` mechanism as upload.

## Consequences

- Publication (Milestone 5b) reads `effective_record` of `approved`/`corrected` candidates
  with `second_review` in (`not_required`, `done`), and treats `unresolved` as blocking the
  category unless the reviewer declares a subset.
- Telemetry (Section 7.6) is computed from decision rows without document text: review
  time by risk tag, correction rate by cause tag and utility, outcomes, undo count.
- The evidence image outlines the cited *table*; cell-level bounding boxes are not stored
  by the readers yet, so the caption names the row and column and the excerpt is shown.
  Storing cell bboxes is a reader change to make later, not a review-workflow change.
- Structured interpretation of `condition_records` (interpretation status beyond
  `verbatim_only`) is not part of this increment; conditions reach reviewers as candidate
  fields and as linked condition text.
