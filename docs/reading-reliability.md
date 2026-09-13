# Reading-reliability ledger

Living ledger for Section 6.1.  Every failure mode has a row; a row without a test is
**unhandled**.  Status values: `unhandled` (no detection yet), `detected` (flagged, not
handled), `handled` (handled and tested), `n/a-yet` (stage not built).  Fixture ids refer to
`tests/fixtures/`; test ids to pytest node ids.  Milestones 1–2a inventory and triage pages; no
extraction exists, so most structure- and value-level rows are `n/a-yet` by design.

## Document-level

| # | Failure mode | Detection | Handling | Fixture | Test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Scanned pages with no text layer mixed with born-digital pages | Inventory: `text_chars == 0`; triage: class `image_only` when a raster covers ≥35% of the page, flag `no_text_layer` + `ocr_needed`, `ocr_recommended=true`; listed per source (`triage.ocr_recommended_pages`) and filterable (`?ocr_recommended=true`) | Classified and routed; **OCR execution itself is Milestone 2b** — these pages are listed, not read | `labelled_order_pdf` p8; `mixed_text_and_image_pdf` p5–6 | `tests/unit/test_triage.py::test_classification_rules`; `tests/integration/test_triage_stage.py::test_inventory_chains_into_triage_and_resolves_labels` | detected (classified; OCR pending) |
| D2 | Text layer present but corrupted (missing Unicode maps, ligatures, reversed order, glyph substitution) | Three independent components per page: glyph coverage (replacement/control/private-use chars), dictionary hit rate (gated on ≥30 alphabetic tokens so numeric tables are not condemned), reading-order sanity (backward y-jumps). Flags `glyph_mapping_damaged`, `text_not_wordlike`, `suspected_column_interleaving` → `low_text_quality` + `ocr_needed` | Flagged and listed (`triage.low_quality_pages`); reconciliation with OCR is Milestone 2b | `garbled_text_pdf` | `test_triage.py::test_glyph_soup_is_flagged_even_with_perfect_glyph_coverage`, `::test_numeric_table_page_is_not_condemned_for_having_few_words`, `::test_damaged_glyph_mapping_and_interleaved_columns_are_separate_flags`; `test_triage_stage.py::test_garbled_text_layer_is_flagged_and_listed` | detected |
| D3 | Rotated or landscape pages inside a portrait document | `rotation` recorded at inventory; triage adds flag `rotated` | Surfaced per page and in the source summary; readers receive the rotation in Milestone 2b | `mixed_text_and_image_pdf` p3 (90°) | `test_triage.py::test_classification_rules[rotated]`; `test_sources.py::test_upload_inventory_reopen_and_dedup` | detected |
| D4 | Watermarks, stamps, signatures over table regions | — | — | — | — | n/a-yet |
| D5 | Printed page labels differ from PDF index, restart per section, or use roman numerals | Footer label read per page (`Page N of M`, `… Page N` at line end, bare number/roman); declared PDF labels kept separately; document-wide rule inferred as segments of (style, constant offset) with singleton disagreements excluded and adjacent agreeing segments merged; every page resolved with a recorded `label_source` (observed / rule / declared / none); disagreements flagged `label_conflict` / `label_off_rule`, never smoothed | Citations resolve printed ↔ PDF index through the rule (KERC/GERC shape: roman front matter then index − 16; NPCL: identity); footer-less pages inherit the rule | `labelled_order_pdf` (i–iii, then −3 with a footer-less run and one wrong footer); `mixed_text_and_image_pdf` (declared only) | `test_triage.py::test_label_rule_inference_roman_front_matter_then_offset` (printed 209 → PDF 225, 534 → 550), `::test_label_rule_npcl_shape_identity`, `::test_single_disagreeing_page_does_not_become_a_rule`, `::test_footer_label_extraction`, `::test_resolution_precedence_and_conflicts`; `test_triage_stage.py::test_inventory_chains_into_triage_and_resolves_labels`, `::test_declared_labels_survive_triage_and_sparse_pages_are_unknown` | handled |
| D6 | Bilingual / regional-language content | — | — | — | — | n/a-yet |
| D7 | Very large files exceeding memory/time | `MAX_UPLOAD_BYTES`, `MAX_PAGES_PER_JOB`; typed `source_too_large` / `page_limit_exceeded`; page-batched inventory with checkpoints | Stops with typed reason; never lowers verification | — | `test_unreadable_and_non_pdf_are_typed_failures` (unreadable path); limits covered by config tests only | detected |
| D8 | Vector-drawn tables with no text layer (KERC Tables 6.2/6.3) | Class `vector_graphics_text_sparse` when text is absent or sparse and drawing operators ≥150; flags `no_text_layer`, `ocr_needed`, `overlapping_graphics`; `ocr_recommended=true` | Routed to rasterise-and-OCR; **execution is Milestone 2b**. Threshold is a profile-overridable datum | `labelled_order_pdf` p7 (840 path strokes, 0 chars) | `test_triage.py::test_classification_rules[vector]`, `::test_thresholds_are_overridable_per_profile`; `test_triage_stage.py::test_inventory_chains_into_triage_and_resolves_labels` | detected (classified; OCR pending) |
| D9 | Non-embedded body fonts | `fonts_not_embedded` recorded per document | Warning badge in the source view; cross-architecture diff is Milestone 2+ | golden `kerc-fy2025-28` (Arial, Times New Roman) | — | detected |

## Structure-level (Milestone 3 unless noted)

| # | Failure mode | Status |
| --- | --- | --- |
| S1 | Approved schedule only in an annexure after hundreds of ARR pages | n/a-yet |
| S2 | Same approved numbers in two authoritative places must agree | n/a-yet (cross-representation validator, M4) |
| S3 | One order → several years / several utilities with one schedule | n/a-yet (schedule-version model, M5) |
| S4 | Per-utility table variants differing only in a title cell | n/a-yet |
| S5 | Schedule as numbered clauses joined by PLUS / ALTERNATIVELY (GERC) | n/a-yet (clause outline, M3) |
| S6 | Existing/Modified amendment diff tables with superseded left column | n/a-yet (M3 localisation, M4 validator) |
| S7 | Textually identical schedules annexed to separate per-utility orders | n/a-yet (M5 shared-scope review) |
| S8 | Rates keyed to metering type, consumer class, season, election | n/a-yet |
| S9 | Same category in existing / proposed / approved / illustrative / ARR tables | n/a-yet — **single most common failure; localisation is a mandatory human checkpoint** |
| S10 | Tables continuing across pages with repeated/omitted/altered headers | n/a-yet |
| S11 | Multi-level headers with units in header/super-header/footnote/title | n/a-yet |
| S12 | Merged cells spanning categories or voltage levels | n/a-yet |
| S13 | Row labels stacked with indentation as the only hierarchy signal | n/a-yet |
| S14 | Category code spelling variants (`LMV-1`, `LMV 1`, `LMV1`) | n/a-yet |
| S15 | Cross-references instead of values | n/a-yet |
| S16 | Footnotes / general conditions far from the table | n/a-yet |
| S17 | TOD seasonal variants; percentage-of-energy-charge adjustments | n/a-yet |
| S18 | Minimum / fixed / demand charges adjacent with different denominators | n/a-yet |
| S19 | Energy charge keyed to demand band; tiered demand charges + excess rate | n/a-yet |
| S20 | Per-connection fixed charges by load range beside per-kW/HP charges | n/a-yet |
| S21 | Opposite-direction terms with near-identical names (ToU discount vs charges) | n/a-yet |

## Value-level (Milestone 3 normalization module)

| # | Failure mode | Status |
| --- | --- | --- |
| V1 | Mixed units within one table (Rs/kWh, paise/kWh, Rs/kVA/month) | n/a-yet |
| V2 | `6.50`, `650`, `Rs. 6.50/kWh`, `6.50/-`, `Nil`, `-`, `NA`, `*`, blank each mean something different | n/a-yet |
| V3 | Indian thousands separators, decimals with stray spaces | n/a-yet |
| V4 | Percentages with/without sign; negatives in parentheses | n/a-yet |
| V5 | Slab ranges with ambiguous inclusivity | n/a-yet |
| V6 | Effective dates in prose / by event (publication + 7 days; first meter reading on/after) | n/a-yet (effective-rule model, M5) |
| V7 | Order naming that does not match the period | n/a-yet |

## Network, open-access and loss determinations (Milestone 4)

| # | Failure mode | Status |
| --- | --- | --- |
| N1 | Decision is a sentence, not a table (approved as zero; not levied pending petition; by reference) | n/a-yet |
| N2 | Working tables deriving the approved figure; only the approved column is leviable | n/a-yet |
| N3 | Injection/drawal matrices with losses in brackets | n/a-yet |
| N4 | Carve-outs by application date and route sending readers to separate orders | n/a-yet |
| N5 | Caps and selection rules (20% of tariff; lower-of; linear reduction) | n/a-yet |
| N6 | `-` = not applicable vs `0` = zero in the same table | n/a-yet |
| N7 | Units switching between paise/unit and Rs/kWh across sections | n/a-yet |
| N8 | Per-utility tables with utilities as column headers | n/a-yet |
| N9 | Exemptions living outside the order cited by the petitioner | n/a-yet |
| N10 | Two distribution-loss numbers with different roles | n/a-yet |
| N11 | Green tariff as a premium with category-specific values and exclusions | n/a-yet |

## Pipeline-level

| # | Failure mode | Detection | Handling | Fixture | Test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | A parser silently returns an empty/truncated table | — | — | — | — | n/a-yet (M2 consensus) |
| P2 | OCR confidence high but geometry wrong (cells shift a column) | — | — | — | — | n/a-yet |
| P3 | Schema-valid but factually unsupported model output | — | — | — | — | n/a-yet (M4 evidence-existence validator) |
| P4 | Partial run + retry creates duplicate artefacts | Queue: fenced writes on `(job_id, run_id)`; page rows upserted `ON CONFLICT DO NOTHING`; checkpoint resume | A killed worker's job is reclaimed after lease expiry and resumes; exactly 6 page rows after kill + resume | `mixed_text_and_image_pdf` + `_killable_worker.py` | `tests/integration/test_worker_recovery.py::test_worker_killed_mid_job_is_resumed_from_checkpoint`; `tests/integration/test_queue.py::test_claim_heartbeat_fencing_and_lease_expiry` | handled |
| P5 | A corrected order upload supersedes the earlier one without the relationship recorded | Hash dedup prevents silent duplicates; `superseded_by_id` exists | Supersede action with confirmation is Milestone 5 | — | `test_upload_inventory_reopen_and_dedup` (dedup only) | detected (partial) |
| P6 | Identical re-upload creates a second source | SHA-256 unique; dedup response `deduplicated: true` with audit event | Exactly one source per byte string | `text_only_pdf` variants | `test_upload_inventory_reopen_and_dedup`, `test_idempotent_upload` | handled |
| P7 | Retry after timeout / double submit registers twice | `Idempotency-Key` replay; same key + different bytes → `idempotency_conflict` | One effect per key | — | `test_idempotent_upload` | handled |
| P8 | Non-PDF or corrupt upload accepted | Header check + PyMuPDF open; worker re-verifies hash and opens again | `source_unreadable` (422) at upload; `failed` state with reason if it slips to the worker | `not_a_pdf`, `plain_text_bytes` | `test_unreadable_and_non_pdf_are_typed_failures` | handled |
| P9 | Fixture data mixed with real data | `datasets` table with one row per kind; FK on utilities and sources; `dataset_kind` on every list | Visible FIXTURE badge; filters | — | `test_fixture_and_real_datasets_are_separate` | handled (M1 scope) |
| P10 | Unauthenticated or under-privileged access to sources | Identity adapter + backend role check on every route | 401 `unauthenticated`, 403 `permission_denied` with request id | — | `test_unauthenticated_and_role_enforcement` | handled |
| P11 | Local identity adapter reaching the cloud | Constructor refuses `DEPLOYMENT_PROFILE=gcp`; settings reject local adapters under gcp | Startup failure, not a silent downgrade | — | `tests/unit/test_profile_and_adapters.py` | handled |
| P13 | A bucket object registered under a name that does not match its content | Ingest re-reads and hashes the bytes; the object name only becomes `original_filename` | Identity is always the SHA-256; a renamed copy of a registered order deduplicates to the same source | `text_only_pdf` under two keys | `tests/integration/test_ingest.py::test_ingesting_the_same_bytes_twice_deduplicates`, `::test_ingest_registers_hashes_and_inventories` | handled |
| P14 | Non-PDF or missing object named in an ingest request | Object existence and size checked before download; PDF header and parse checked as for uploads | `not_found` (404) / `source_unreadable` (422); nothing registered | `plain_text_bytes` in the bucket | `tests/integration/test_ingest.py::test_ingest_idempotency_and_missing_or_unreadable_objects` | handled |
| P15 | Non-reproducible fixtures making hash-based tests vacuous | Fixture generators pin timestamps and normalise the PDF trailer `/ID`; a test asserts byte-equality across calls | Same generator call always yields the same SHA-256, so dedup and manifest tests assert something | all generators | `tests/unit/test_profile_and_adapters.py::test_synthetic_fixtures_are_byte_reproducible` | handled |
| P16 | A tool or rules upgrade silently overwrites earlier stage outputs | Artefact keys embed source hash, stage and `tool@version+rules@version`; `stage_artefacts` has a unique constraint per (source, stage, tool_version, page); object puts are immutable no-ops | A re-run at the same version writes nothing new and duplicates nothing; a new version writes beside the old; stage re-runs go through the transition table and are audited | `labelled_order_pdf` | `test_triage_stage.py::test_stage_rerun_keeps_old_artefacts_and_is_audited`, `::test_triage_resumes_after_worker_kill_without_reprocessing` | handled |
| P17 | A page that matches no classification rule is treated as fine | Class `unknown` with a recorded rationale; `triage.unknown_pages` listed; rendered with the *unknown* badge, never green | Unknown is a first-class, visible state | `mixed_text_and_image_pdf` (two-line pages) | `test_triage_stage.py::test_declared_labels_survive_triage_and_sparse_pages_are_unknown` | handled |
| P12 | Golden-corpus expectations copied instead of verified | Registration stores `manifest_check` with expected vs observed and `all_match` | Mismatch is visible in the source view; never auto-corrected | `tests/golden/manifest.json` | `test_golden_manifest_compare`, `test_manifest_file_lists_three_supplied_orders` | handled (page count/size/text-layer counts) |
