# Data dictionary (through Milestone 4b)

Migration owner: `services/api/migrations/versions/0001_foundation.py`.  All timestamps are
`timestamptz`; ids are UUIDv4 unless noted.  Enums are PostgreSQL enum types.

## `datasets`
| Column | Type | Meaning |
| --- | --- | --- |
| kind | `dataset_kind` (`real`, `fixture`) | Unique per kind (`uq_datasets_kind`): exactly one real and one fixture dataset |
| name | text | `real` / `fixture` |

Isolation rule (working agreement 12): `utilities.dataset_id` and `source_documents.dataset_id`
are foreign keys; every list endpoint carries `dataset_kind`; the UI labels fixture records.
A real utility linked to a fixture source will be rejected by the order-registration
service in Milestone 3 (link does not exist yet).

## `users`
`email` (unique), `display_name`, `role` (`user_role`: analyst | reviewer | administrator),
`active`.  Under the `gcp` profile IAP authenticates and this table authorises; under
`local` the allow-list carries the role.  Role changes are audit events.

## `jurisdictions`, `commissions`, `utilities`
Stable identities with `code`, `name`, `aliases` (JSONB list).  `utilities` additionally:
`licensed_area`, `active_reading_profile`, `active_reading_profile_version` (null until a
profile version is published in Milestone 3), `dataset_id`.  A state is not a schedule;
nothing here implies coverage.

## `source_documents`
| Column | Meaning |
| --- | --- |
| sha256 (unique), size_bytes, original_filename, content_type | Immutable identity of the bytes |
| provenance_url, acquired_at, uploaded_by | Provenance |
| object_key | `<sha256>.pdf` in the logical `sources` bucket |
| state, state_reason | `source_state` enum; transitions in `models.SOURCE_TRANSITIONS`; each transition is an audit event |
| page_count, pdf_version, producer, creator, is_encrypted, is_tagged, fonts_total, fonts_not_embedded | Document-level inventory; null until the inventory stage ran (never guessed) |
| pages_with_text, pages_without_text, inventory_tool, inventory_tool_version, inventoried_at | Text-layer summary and tool provenance |
| golden_id, manifest_check | Set when the hash matches `tests/golden/manifest.json`; `manifest_check` records expected vs observed per field |
| superseded_by_id | Supersession link (set by later milestones' supersede action) |
| version | Optimistic-concurrency counter; incremented on every transition |

## `source_pages`
One row per PDF page (`page_index` 1-based, unique per source).

Inventory (Milestone 1): `width_pt`, `height_pt`, `rotation`, `text_chars` (non-whitespace
characters from the text layer), `has_text_layer`, `image_count`, `drawing_count`,
`label_declared` (the PDF's own page-label dictionary entry, if any).

Triage (Milestone 2a, `docs/reading-reliability.md` D1/D2/D5/D8):
| Column | Meaning |
| --- | --- |
| page_class | Section 6.3 class from a deterministic rule; `unknown` when no rule matched (never green) |
| quality_flags | JSONB list: `no_text_layer`, `ocr_needed`, `rotated`, `overlapping_graphics`, `glyph_mapping_damaged`, `text_not_wordlike`, `suspected_column_interleaving`, `low_text_quality`, `label_conflict`, `label_off_rule` |
| text_quality | JSONB `{glyph_coverage, dictionary_hit_rate, reading_order_sanity, score, token_count}`; null when there is no text layer |
| ocr_recommended | The page should be rasterised and OCR'd (executed in Milestone 2b) |
| triage_rationale | Why the class was chosen, in words |
| label_observed | The label read from the page footer/header |
| printed_label | The **resolved** label a citation should show |
| label_source | Where `printed_label` came from: `observed` \| `rule` \| `declared` \| `none` |
| triage_version, triaged_at | Rules version and time; a version bump re-triages every page |
| page_role | Section 6.5; `unknown` until Milestone 3 |

Parse (Milestone 2b, ADR-0009): `ocr_used`, `ocr_engine` (`tesseract@5.3.4`), `ocr_confidence`
(mean word confidence), `ocr_word_count`, `ocr_text_chars`, `ocr_agreement` (token Jaccard with
the text layer when both exist; null otherwise), `parse_version`, `parsed_at`.  Extra
`quality_flags`: `ocr_low_confidence`, `ocr_no_text`, `ocr_layer_disagreement`,
`grid_from_ocr_pending`, `reader_disagreement`, `structure_disagreement`, `primary_missing`,
`secondary_missing`, `empty_grid`.

## `table_grids`
One row per reader per table on a page (`uq_table_grid`): `reader`, `reader_version`,
`ordinal`, `strategy` (`lines` | `text`), `bbox`, `row_count`, `col_count`, `header_rows`,
`is_empty`, `is_primary`, `agreement_class` (`high_agreement` | `minority_cell_disagreement` |
`structure_disagreement` | `primary_missing` | `secondary_missing`), `agreement_score`,
`paired_ordinal`, `disagreeing_cells`, `risk_tags`, `object_key` (artefact holding the full
grid and the agreement record).  A re-run at the same parse version replaces the rows for a
page; artefacts stay immutable.

## `document_headings`
Heading inventory (`uq_document_heading` per page/line/kind/rules version): `ordinal`
(document-wide), `kind` (`rate_schedule` | `tariff_schedule` | `rate_clause` | `annexure` |
`chapter` | `table_caption`), `code_raw`, `code_canonical`, `text`, `text_source`
(`text_layer` | `ocr`), `rules_version`.

## `source_documents` — parse columns
`parse_version`, `parsed_at`, `heading_inventory` (JSONB: `counts`, `unique_codes`,
`repeated_codes` per kind), `table_summary` (JSONB: `tool_version`, `grid_pages`,
`primary_grids`, `agreement_classes`, `pages_needing_review`, `ocr_pages`,
`ocr_low_confidence_pages`, `grid_from_ocr_pending_pages`).

## `source_documents` — reading profile and localisation columns (Milestone 3a)

| Column | Meaning |
| --- | --- |
| reading_profile_id, reading_profile_version | The profile the source is read with (`packages/reading-profiles/profiles`) |
| reading_profile_source | `detected` (from the heading inventory) or `assigned` (administrator) |
| reading_profile_rationale | Why: the detection explanation or the assignment reason and actor |
| localisation_version, localised_at | Rules version and time of the last localisation run |

## `localisation_records` (one per source)

| Column | Meaning |
| --- | --- |
| status | `proposed` (rules ran, reviewer needed), `ambiguous` (rules halted), `confirmed`, `corrected` |
| rules_version, profile_ref | What produced the current regions (`<id>@<version>`) |
| findings | Rule findings: `code`, `severity` (`blocking` / `warning` / `info`), `message`, `pages` |
| extraction_allowed | True only after a reviewer decision; the gate Milestone 4 reads |
| decided_by, decided_at, decision_rationale, decision_count | The human decision; a re-run resets the first three and keeps the count |
| artefact_key | The immutable rules output (`<sha>/localise/rules@<v>+profile@<ref>/document.json`) |
| version | Optimistic concurrency for decisions |

## `localisation_regions`

| Column | Meaning |
| --- | --- |
| role | `approved_schedule`, `approved_summary`, `existing_tariff`, `proposed_tariff`, `amendment_diff`, `formula_parameters`, `network_charges`, `loss_trajectory`, `green_tariff`, `illustrative`, `derived_not_tariff`, `other` |
| sub_role | For `network_charges`: `wheeling_charge`, `oa_loss`, `cross_subsidy_surcharge`, `additional_surcharge`, `banking_rule`, `green_tariff`, `transmission_reference` |
| page_start, page_end | PDF indices, inclusive |
| cue_text, cue_page, cue_kind | The line that justified the classification, where it was found, and how (`locator`, `page_class`, `reviewer`) |
| utility, period | When exactly one profile utility / one or more `FY` periods appear on the cue page |
| origin | `detected` by the rules or placed by a `reviewer` |
| grid_count | Primary table grids inside the span (from the parse stage) |
| reviewer_note, excluded, annotated_by, annotated_at | A reviewer's comment on the region (`PUT /sources/{id}/localisation/regions/{region_id}`, reviewer role, versioned against the localisation record, audited as `localisation.annotate`). `excluded` makes the structure and extraction stages skip the span; the note is shown on the family in the review checklist. Allowed while the source is `localised` or `gridded`; frozen once candidates exist. Carried across a localise re-run when the rules find the same span again. |

## `category_summaries`

Generated reviewer context for one schedule category — labelled generated, never a fact, never
published, never an input to a validator.

| Column | Meaning |
| --- | --- |
| category_code, heading_text, page_indices | The category, its schedule heading and the pages from that heading to the next |
| text | The summary. Fixture mode: a template that reads the candidates back grouped by rate block. Real provider: prose from the same inputs under `SUMMARY_SYSTEM_PROMPT` (only printed numbers, every rate with component, unit and who it applies to, applicability and conditions quoted, ≤160 words) |
| grounded, unsupported_numbers | Deterministic check: every number in the text must be a candidate value or appear in the category's page text; failures are stored and shown, not hidden |
| provider, model, prompt_version, is_fixture, input_tokens, output_tokens, cost_usd | The call that wrote it, counted in the order's provider budget |

`Candidate.assessment` (schema 2): the model's feedback on one value — `verdict`,
`confidence`, `sub_category`, `meaning`, `quote`, `grounded`, `issue`, provider, model,
`is_fixture`, `prompt_version`, `sub_categories_seen`.  Grounding is mechanical (the quote
must be on the pages); doubt raises `model_low_confidence` / `model_contradicted` /
`assessment_ungrounded` risk tags and individual review; nothing in it changes a value
(ADR-0016).

`Applicability.rate_block` on a retail candidate: the lettered block above the table the cell
sits in ("(b) Public Institutions … supply at Single Point on 11 kV & above voltage levels:"),
read from the page text; part of the candidate key, so the same row label under (a) and (b) are
two facts.

## `source_documents` — structure columns (Milestone 3b)

| Column | Meaning |
| --- | --- |
| structure_version | `grid@<v>+clauses@<v>+normalise@<v>` that produced the rows |
| gridded_at | Time of the last structure run |
| structure_summary | Counts: cells, resolved/unresolved by flag, unit sources, continuations, clause values/cross-references/conditions/categories/option groups, per-region reports |

## `structure_cells`

| Column | Meaning |
| --- | --- |
| region_role, page_index, grid_ordinal, row, col | Where the cell is: the citation a candidate carries |
| raw | The cell text as read |
| header_path, row_path | Column header hierarchy and row label hierarchy, both required for a resolved cell |
| normalised | The full normalisation record (value, state, rules, flags) |
| value_state | `value`, `zero`, `not_applicable`, `unknown`, `cross_reference`, `formula`, `footnote_only` |
| currency, per_unit, frequency, unit_source | The binding and where it came from (`cell`, `header`, `row_unit_column`, `title`, `footnote`) |
| flags | `header_inherited`, `header_span_inherited`, `merged_cell_propagated`, `footnote_attached`, `footnote_unresolved`, `unit_unresolved`, `currency_unresolved`, `unresolved_header`, `unresolved_row`, `slab_inclusivity_ambiguous`, `nil_word`, … |
| footnotes | Attached footnote texts |
| slab | Parsed slab bounds of the row label, when it is one |
| resolved | Header path + row path + unit all present |

## `clause_values`

| Column | Meaning |
| --- | --- |
| category_code, clause_path | `RGP`, `["1. RATE: RGP", "1.2. ENERGY CHARGES", "(a) First 50 units …"]` |
| role | `fixed`, `demand`, `energy`, `tou_surcharge`, `rebate`, `minimum`, `power_factor`, `penalty`, `option`, `condition`, `other` |
| kind | `value`, `cross_reference`, `condition` |
| connector, alternative | `PLUS` joins to the previous block; alternative index within the category's option group |
| normalised, dimension, slab, time_window, sign, parameters | Value record; metering-type column; parsed slab; `11:00-17:00`; ±1; further amounts on a rule line |

## `extraction_runs` (Milestone 4a)

One row per call per channel per region: `channel`, `provider`, `model`, `prompt_version`,
`schema_version`, `is_fixture`, `input_hash`, `input_tokens`, `output_tokens`, `cost_usd`,
`status`, `error`, `candidates_returned`.  The structure channel is always the rules
(`provider=rules`, `is_fixture=false`, cost 0, one row per region); the image channel is one
row per page chunk for a real model, one row for the fixture.  Fixture, rules and real runs
are never summed together (`fixture_runs`, `rules_runs`, `real_runs`).

## `candidates`

| Column | Meaning |
| --- | --- |
| candidate_key | Identity of the fact (family, category, component, applicability, period, utility) used for channel comparison and duplicate detection |
| family, category_code, component_type | Section 5.1 family; source category code; component (`energy`, `fixed`, `demand`, `minimum`, `tod_adjustment`, `rebate`, `surcharge`, `subsidy`, `green_premium`, `charge`, `loss`, `cross_reference`) |
| value, value_state, currency, per_unit, frequency, decision_status, period, utility | Denormalised from the record for queries |
| record | The full `Candidate` (schema v1): original text, applicability, conditions, evidence, missing/ambiguous, `derivation` (printed inputs and rule behind a network value) |
| image_record | The image channel's version when both channels ran |
| channel_agreement, disagreeing_fields | `agree`, `disagree`, `one_missing`, `single_channel` |
| confidence, risk_tags, routing | Section 6.10; `individual` or `batch` |
| review_status | `pending`, `awaiting_second_review`, `approved`, `corrected`, `rejected`, `unresolved` (Milestone 5a) |
| reviewed_record, reviewed_by, reviewed_at, first_reviewer, second_review, decision_count | Review state (Milestone 5a): the corrected record (the extractor's `record` is never overwritten), who decided last, the first-round reviewer while a second review is pending, `not_required` / `pending` / `done`, decisions taken |
| published_release_id | The first release that published this candidate; set → no further decision or undo (Milestone 5b) |
| version | Optimistic concurrency: every decision and undo increments it |
| is_fixture | Set from the provider; never mixed with real |
| finding_count, blocking_finding_count | From the last validation run |

## `validator_findings`

`validator_id` (VAL-nn), `severity` (`blocking` / `warning` / `info`), `message`,
`candidate_ids` (empty = source-level), `detail`, `validators_version`.

## `family_dispositions`

Reviewer-recorded `absent_in_source` / `out_of_scope` / `not_a_tariff_category` per family,
with rationale, actor and time.

## `condition_records` (Milestone 4b)

| Column | Meaning |
| --- | --- |
| kind | `general_provision` (numbered, incl. `20(f)` sub-provisions), `footnote`, `clause_condition` |
| number, text, text_hash | The provision number and its verbatim text |
| scope_codes | Category codes the text names |
| interpretation_status | `verbatim_only` until a reviewer interprets it (Milestone 5) |

## `review_decisions` (Milestone 5a)

| Column | Meaning |
| --- | --- |
| candidate_id, sequence, review_round | Per-candidate sequence; round 1 or 2 |
| outcome, reviewer, candidate_version | `approve` / `correct` / `reject` / `unresolved`; who; the version decided on |
| rationale, cause_tag | Mandatory rationale except for approve; cause tag on corrections |
| corrected_record, corrected_fields | The full record after correction and the field names that changed |
| evidence_view_ids, evidence_viewed, time_spent_ms, view_to_decision_ms | The views cited (this reviewer's, this candidate's, incl. index 0); client-reported and server-measured time |
| before, after | Snapshots of the candidate's review state; undo restores `before` |
| undone, undone_by, undone_at | Undo marks, never deletes |
| idempotency_key, request_id | Traceability |

## `evidence_views` (Milestone 5a)

One row per rendered evidence image: candidate, evidence index, page, viewer, dpi, whether
the cited table was outlined, time.  Written only by the image endpoint; cited by decisions.

## `data_releases` (Milestone 5b)

| Column | Meaning |
| --- | --- |
| release_number, is_current, superseded_by_id | Cumulative releases per source; the current one carries every published fact |
| scope, scope_categories, scope_families | `whole_schedule` or `subset` with its lists |
| completeness, gaps | `complete` or `partial` with `[{key, reason}]`; partial is labelled everywhere it is read |
| rationale, published_by, published_at, source_version, request_id | Who, why, when, against which source version |
| fact_count, candidates_in_scope, unresolved_count, pending_count, awaiting_second_review_count | The consequences at publication |
| checklist_snapshot | Checklist summary, candidate status counts and family dispositions at publication (the coverage record) |
| preview_token | Hash of the state the reviewer confirmed |
| utility, period, is_fixture | Denormalised for the release list; fixture releases never count as coverage |

## `published_facts` (Milestone 5b)

One row per published candidate per release: `candidate_id`, `decision_id` (the final
decision), `review_status` (`approved` / `corrected`), the denormalised fact columns
(family, category, component, value, value_state, currency, per_unit, frequency,
decision_status, period, utility), `applicability`, `conditions`, `derivation`, the full
effective `record`, `is_fixture`.  No route reads candidates to answer an explorer query.

## `published_evidence` (Milestone 5b)

Evidence spans of published facts: `ordinal`, `page_index`, `printed_label` (resolved by
triage), `kind`, `grid_ordinal`, `row`, `col`, `line_no`, `header_path`, `row_path`,
`clause_path`, `excerpt`.  Citations are derived from these rows by backend code.

## `source_documents` — extraction and validation columns

`extraction_version`, `extracted_at`, `extraction_summary` (provider, versions, runs, cost,
tokens, candidates by family/confidence/agreement/routing, risk tags, new_profile);
`validators_version`, `validated_at`, `validation_summary` (findings by severity and
validator, candidates with findings / blocked, families without disposition, routing).

## `stage_artefacts`
Index of immutable per-stage outputs in the `artefacts` bucket (Section 6.2): `stage`,
`tool`, `tool_version` (e.g. `pymupdf@1.28.2+rules@1`; parse: `pymupdf@…+pdfplumber@…+tesseract@…+rules@1`, widened to 160 chars in 0003), `page_index` (0 = document-level),
`object_key` (`<sha256>/<stage>/<tool_version>/page-NNNN.json`), `content_sha256`,
`size_bytes`.  Unique per (source, stage, tool_version, page): a re-run at the same version
is a no-op; a new version writes beside the old.

## `source_documents` — triage columns
`label_rule` (JSONB: `segments[{start_index,end_index,style,offset,observed_pages}]`,
`observed_pages`, `declared_pages`, `pages_with_label_flags`, `rules_version`),
`page_class_counts` (JSONB histogram), `triage_version`, `triaged_at`.

## `jobs`, `job_events`
| Column | Meaning |
| --- | --- |
| job_type, payload, idempotency_key (unique) | What to run; enqueue is idempotent |
| status | `job_status`: queued, leased, succeeded, failed, cancelled |
| priority, available_at | Ordering and delayed retry |
| attempts, max_attempts | Bounded retries; exceeding yields `retries_exhausted` |
| lease_owner, lease_expires_at, heartbeat_at, run_id | Lease; every claim mints a new run_id; writes are fenced on it |
| stage, checkpoint, progress | Resume point and UI progress (e.g. `{next_page}`, `{pages_done, pages_total}`) |
| cancel_requested | Observed by the handler at its next checkpoint/heartbeat |
| error_type, error_message | Typed failure (taxonomy in `errors.py`) |

`job_events`: append-only trail (`enqueued`, `claimed`, `lease_expired_reclaimed`,
`checkpoint`, `retry_scheduled`, `failed`, `succeeded`, `cancel_requested`, `cancelled`).

## `audit_events`
Append-only (UPDATE/DELETE raise via trigger): `actor`, `action`, `entity_type`, `entity_id`,
`before`, `after`, `reason`, `request_id`, `at`.

## `idempotency_records`
`(key, actor)` → request fingerprint, stored status and body, for `Idempotency-Key` replays.

## Reserved for later milestones (not created yet)
Regulatory order, schedule version, effective rule, category/version, option group, category
mapping, charge component, slab/time band, condition/rule, evidence span, table grid,
failure report — Section 5.2 (candidate, review decision, condition/rule, network charge
determination, loss record, publication and coverage record exist as `candidates`,
`review_decisions`, `condition_records`, candidate families, `data_releases` with its
checklist snapshot, `published_facts` and `published_evidence`).
