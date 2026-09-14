# Data dictionary (through Milestone 3b)

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
candidate, review decision, publication, coverage record, network charge determination,
loss record, reading profile, failure report — Section 5.2.  `value_state` and
`decision_status` enums will be introduced with the candidate schema (Milestone 4).
