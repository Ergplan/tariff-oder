# Reading-reliability ledger

Living ledger for Section 6.1.  Every failure mode has a row; a row without a test is
**unhandled**.  Status values: `unhandled` (no detection yet), `detected` (flagged, not
handled), `handled` (handled and tested), `n/a-yet` (stage not built).  Fixture ids refer to
`tests/fixtures/`; test ids to pytest node ids.  Milestone 1 only inventories pages; no
extraction exists, so most rows are `n/a-yet` by design.

## Document-level

| # | Failure mode | Detection | Handling | Fixture | Test | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Scanned pages with no text layer mixed with born-digital pages | Per-page `text_chars == 0` in the inventory stage; `pages_without_text` summary and ranges | Recorded per page and in the source summary; UI marks `absent`; OCR routing is Milestone 2 | `synthetic_pdfs.mixed_text_and_image_pdf` (pages 5–6) | `tests/integration/test_sources.py::test_upload_inventory_reopen_and_dedup`; `tests/unit/test_profile_and_adapters.py::test_inventory_of_synthetic_fixture_direct` | detected |
| D2 | Corrupted text layer (missing Unicode maps, ligatures, reversed order, glyph substitution) | — (quality score in Milestone 2) | — | — | — | n/a-yet |
| D3 | Rotated or landscape pages inside a portrait document | `rotation` and page size recorded per page | Surfaced in inventory UI (`rotated_pages`) | `mixed_text_and_image_pdf` page 3 (90°) | `test_upload_inventory_reopen_and_dedup` | detected |
| D4 | Watermarks, stamps, signatures over table regions | — | — | — | — | n/a-yet |
| D5 | Printed page labels differ from PDF index / restart / roman numerals | PDF page-label entries recorded per page (`printed_label`); footer-derived labels and the offset map are Milestone 2 | Labels shown beside indices; never used as the index | `mixed_text_and_image_pdf` (i, ii, 1–4) | `test_upload_inventory_reopen_and_dedup` | detected (declared labels only) |
| D6 | Bilingual / regional-language content | — | — | — | — | n/a-yet |
| D7 | Very large files exceeding memory/time | `MAX_UPLOAD_BYTES`, `MAX_PAGES_PER_JOB`; typed `source_too_large` / `page_limit_exceeded`; page-batched inventory with checkpoints | Stops with typed reason; never lowers verification | — | `test_unreadable_and_non_pdf_are_typed_failures` (unreadable path); limits covered by config tests only | detected |
| D8 | Vector-drawn tables with no text layer (KERC 6.2/6.3) | `drawing_count` high with `text_chars == 0` is recorded; classification `vector_graphics_text_sparse` is Milestone 2 | — | golden `kerc-fy2025-28` PDF 226–240 (bytes absent) | — | n/a-yet |
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
| P12 | Golden-corpus expectations copied instead of verified | Registration stores `manifest_check` with expected vs observed and `all_match` | Mismatch is visible in the source view; never auto-corrected | `tests/golden/manifest.json` | `test_golden_manifest_compare`, `test_manifest_file_lists_three_supplied_orders` | handled (page count/size/text-layer counts) |
