# ADR-0010 Reading profiles as data; localisation as a halting, reviewed stage

Status: accepted (2026-09-14)

## Decision

- **Profiles are JSON data** in `packages/reading-profiles/profiles/<id>.v<n>.json`, validated
  by a pydantic model (`tariff_api.profiles.ReadingProfile`) that *is* the schema;
  `schema.json` is generated from it and a unit test fails on drift.  The three seed profiles
  express every difference among Parts D, E and F without code: schedule representation
  (`tables` / `clause_outline`), the heading kind that marks a category schedule
  (`rate_schedule` / `tariff_schedule` / `rate_clause`), unit placement (cell / header),
  currency convention, ToD adjustment type (percent / absolute paise), effective-rule type,
  schedule scope, conversion factors, inventory expectations (15 UPERC schedules, no LMV-10)
  and locator cues per region role with a note tying each cue to the spec paragraph it came
  from.  A profile change is a data commit linked to the review that motivated it.
- **Profile binding** is detected from the heading inventory (the dominant schedule-heading
  kind names the layout family; a tie or an empty inventory detects nothing) and recorded
  with its rationale, or assigned by an administrator with an audited reason.  Assignment
  drops the localisation and re-runs the stage.
- **Localisation is a pure rule set** (`tariff_api.localisation`, `LOCALISATION_VERSION`)
  over per-page text, class, headings and grid counts.  Span locators open the
  `approved_schedule` region; it runs to the last schedule heading, extends over heading-less
  continuation pages, and closes at a page classified as other material or an image-only
  run.  Page locators classify single pages (adjacent same-role pages merge; a different
  utility on the page keeps them apart).  Contents pages, detected by dot-leader lines, never
  open a region.  Image-only runs are `other`.
- **Ambiguity halts.**  Several `approved_schedule` candidates, none, or a code the profile
  declares absent are blocking findings; the record is `ambiguous`, extraction is not
  allowed, and confirming is refused: a reviewer must *correct* the regions.  The rules
  never pick the last, largest or most numeric table.
- **The checkpoint is a human boundary.**  Even an unambiguous result is `proposed`;
  `extraction_allowed` becomes true only through a reviewer's (or administrator's) decision
  with a rationale, an explicit "pages viewed" statement, optimistic concurrency on the
  record version, and an audit event holding the full before/after region sets.  A re-run
  (new rules, new profile) reopens the checkpoint: the previous decision is visible in the
  audit and in `decision_count`, never silently carried over.

## Consequences

- Milestone 4 extraction reads regions from the localisation record and must refuse to run
  while `extraction_allowed` is false; it must never take a candidate from a region whose
  role is not `approved_schedule` / `approved_summary`.
- The seed profiles are *expectations from the specification*, not verified against the
  real files.  The first run over the three real orders will produce inventory-mismatch
  findings wherever the spec and the file differ; those are findings to resolve, not noise.
- Locator cues are regular expressions over single lines.  A cue that appears only inside a
  vector-drawn table reaches the rules through the OCR artefact text; if OCR misreads the
  caption the region is simply not found and the reviewer places it.
