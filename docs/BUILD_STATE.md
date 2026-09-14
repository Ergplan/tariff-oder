# BUILD_STATE

Last updated: 2026-09-14. Branch `claude/keen-tesla-r9mvv5`.
Increments so far: (1) Milestone 0 + Milestone 1; (2) dev-project wiring and bucket ingest;
(3) first verification against the real project; (4) Milestone 2a — page triage; (5) Milestone
2b — OCR, second reader, table grids with agreement classes, heading inventory; (6) first
Terraform plan against the project and the image-bootstrap fix it exposed; (7) Milestone 3a —
reading profiles as data and the localisation stage with its reviewer checkpoint; (8) Milestone
3b — normalisation, clause outlines, grid integrity and the gated structure stage; (9) Milestone
4a — candidate schema, provider adapter with fixture mode, dual-channel extraction,
validators, routing and the review queue; (10) Milestone 4b — network-charge grids,
derivations, amendment consistency, condition records, cross-representation agreement.

## Current milestone and status

- **Milestone 0 — complete.** Repository was empty (no commits); audit, ADR-0001…0007,
  architecture, data dictionary, reliability ledger skeleton, error taxonomy, evaluation
  plan with the D/E/F question set, deployment doc, milestone checklist all written.
- **Milestone 1 — implemented and tested under the `local` profile; cloud gate still blocked.**
  Everything the gate requires runs locally against real PostgreSQL 16 + pgvector.  Terraform
  now targets the real project (`tariff-order-parsing`) and validates, but **nothing has been
  planned or applied**: this build environment has no `gcloud` and its Google token is rejected
  (`ACCESS_TOKEN_TYPE_UNSUPPORTED`, re-checked after the project details arrived).  The apply
  has to run on the `tariff-order` VM.
- **Milestone 2 — parts (a) and (b) implemented and tested under the `local` profile.**
  (a) page triage: classification, text-layer quality, printed-label maps, immutable stage
  artefacts, resumable and re-runnable.  (b) parse: tesseract OCR on the pages triage routed
  to it with per-word confidence; two independent table readers (PyMuPDF primary, pdfplumber
  secondary) with an agreement class per grid; a document-wide heading inventory.  **Open
  within Milestone 2:** grids from OCR word boxes are not attempted (flagged
  `grid_from_ocr_pending`, listed for review); Docling is not measured; the three real orders
  have not been run because their bytes are not in this environment.
- **Milestone 4 — parts (a) and (b) implemented and tested under the `local` profile with
  the fixture provider.**  (a) Versioned candidate schema; provider adapter (fixture +
  Anthropic Messages API path, the latter written but never run: no credentials here);
  structure and image channels per approved region; prose decisions for network-charge
  families; comparison, confidence, risk tags and routing; validators VAL-01–04, 06, 08–11,
  13, 15, 17, 18 with fixtures; the review queue and family dispositions.  (b) Grids inside
  `network_charges`, `loss_trajectory`, `green_tariff` and `amendment_diff` regions are read
  and extracted (wheeling, loss trajectories, cross-subsidy surcharge keeping only the
  approved column with the working columns as a recorded derivation, additional surcharge,
  green tariff premiums from prose); condition records (general provisions, sub-provisions,
  footnotes, clause conditions, all verbatim); validators VAL-05 (amendment consistency),
  VAL-07 (derivations: ARR ÷ sales at printed precision, lower-of, cap), VAL-12 (rate
  condition links) and VAL-16 (schedule vs summary agreement).  **Still not built:** VAL-14
  temporal consistency (needs a second order for the same utility); the live model channel
  is unexercised; **no real provider run has happened** (`tariff-api provider-smoke` exists
  to make the first one a two-cell synthetic input, not an order).  The Milestone 4 gate's
  "every charge family has candidates or a reviewed disposition for each supplied order" is
  blocked on the real orders and on a reviewer.
- **Milestone 3 — parts (a) and (b) implemented and tested under the `local` profile.**  (b)
  adds the versioned normalisation module, clause-outline reconstruction, grid integrity
  (header/row paths, continuation, merged cells, unit binding with source, footnotes) and
  the `localised → gridded` stage that runs only from reviewer-confirmed regions.  **The
  Milestone 3 gate is blocked on the real orders**: it asks for the NPCL localisation
  confirmed by a reviewer and the Karnataka vector tables read by OCR into grids; neither the
  bytes nor a reviewer are available here.  Grids from OCR word boxes are still not built.
- **Milestone 3 — part (a): reading profiles and binding-schedule localisation.**  Three seed profiles (`uperc-npcl`, `kerc-escoms`,
  `gerc-discoms`) as validated JSON; stage `parsed → localised` producing classified regions
  with textual cues; ambiguity halts; a mandatory reviewer checkpoint (confirm / correct,
  audited, versioned) that the rules can never pass on their own.  **Part (b)** — clause
  outlines, header/row-path reconstruction, continuation inheritance, merged-cell expansion,
  unit binding, footnotes, the normalisation module and the 6.1 structure/value fixtures — is
  next.
- **No provider connection, no extracted number exists.**  The only reviewer decisions that
  exist are localisation confirmations on synthetic fixtures made by the test harness's
  reviewer user; no real-source region has been confirmed by anyone.

### Increment 10 (Milestone 4b: network-charge grids, derivations, conditions, cross-checks)

- Grid stage now reads tables in every read role (`approved_schedule`, `approved_summary`,
  `network_charges`, `loss_trajectory`, `green_tariff`, `amendment_diff`), each grid once
  even where reviewer regions overlap; clause outlines stay limited to the approved roles.
- `tariff_api.extraction`: `network_extract` classifies a network grid by its vocabulary
  (wheeling, cross-subsidy surcharge, additional surcharge, losses, green) with the region's
  role as fallback.  CSS tables yield one candidate per voltage level from the *approved*
  column only; the other columns (formula value, cap, existing) are kept as
  `derivation.inputs` with the rule (`lower_of` / `cap`) — never emitted as tariff values.
  Wheeling working tables (ARR Rs Cr, sales MU, Rs/kWh) produce a `derivation` with rule
  `arr_over_sales`.  Loss trajectories carry `applicability.voltage` from the row path
  (`Candidate.key()` now includes voltage, which the fixture exposed: all loss rows had
  collapsed to one key).  Green-tariff premiums are read from prose, and a "regulatory
  discount … not applicable" sentence is excluded.  `extract_conditions` records numbered
  provisions, mid-line sub-provisions (`20(f) …`), cell footnotes and clause conditions
  as `verbatim_only` rows in `condition_records` (migration `0007_conditions`;
  `GET /sources/{id}/conditions`).  Summary tables take their category from the profile's
  `category_code_pattern` when the region is `approved_summary`.
- Extraction stage: each grid feeds exactly one region (`claimed_grids`); prose facts are
  de-duplicated by evidence span so overlapping regions do not double-count.
- Validators: VAL-05 blocks when an amendment's modified text is absent from the
  consolidated text, or when the schedule still carries the superseded text; VAL-07 recomputes
  derivations at the printed precision; VAL-12 blocks a candidate whose condition text is
  neither a recorded condition nor a ≥12-character fragment of one; VAL-16 compares schedule
  and summary candidates per (category, component, period) where the profile declares the
  summary authoritative — disagreement blocks, absence of a summary warns.
- Fixtures: `network_order_pdf` (10 pages; the CSS table's HV-2 row deliberately has an
  approved value that is not the lower of the two, so VAL-07 must flag it),
  `dual_representation_pdf(disagree=True)` (KERC-style summary 585 vs schedule 650 for LT-2),
  `gerc_amendment_order_pdf(mismatch=True)` (existing/modified time bands).
- Defects found by the fixtures and fixed: overlapping network regions raised an
  IntegrityError in the grid stage; `region_role` missing from the cell columns; duplicated
  candidates from overlapping regions; `_level_from` returned only the matched word so CSS
  rows lost their level; text-only amendment tables yield no structure cells, so VAL-05
  reads the parse grid artefacts instead.
- `tariff-api provider-smoke`: with the fixture backend it prints why and exits 2; with a
  real backend it runs one two-cell synthetic structure and prints provider, model, tokens
  and cost.  It has not been run with a key.
- Docs: ledger rows N2, N5, N7, N11 handled+tested; S2 → VAL-16, S6 → VAL-05; ADR-0012
  addendum; data dictionary (`condition_records`, `derivation`); architecture.

### Increment 9 (Milestone 4a: candidates, validators, routing)

- `tariff_api.tariff_schema` (schema v1): `Candidate` with exact decimal strings, original
  text, `value_state` on every numeric field, `decision_status` on network families,
  applicability dimensions (slab/load band with basis, season, time band, metering type,
  consumer class, alternative, rate block, description), conditions as text, evidence
  (cell: page/grid/row/col + header and row paths; clause: page/line + clause path; prose)
  with the exact excerpt; `ExtractionOutput` with `missing`.  The same model is the tool
  schema handed to a provider.
- `tariff_api.extraction` (rules v1, prompt v1): serialised structure input that declares
  all text as data; deterministic rules structure → candidates (cells and clauses; `Nil`
  stays a zero state without a number; cross-references stay references; conditions and
  footnotes attach); prose decisions (`approved_zero`, `not_levied_pending_petition`,
  `deferred_to_separate_petition`, `by_reference`); channel comparison; routing per 6.10
  plus `single_channel` (recorded deviation).
- `tariff_api.providers`: `FixtureProvider` (labelled, zero cost, optional perturbation
  file for tests) and `AnthropicProvider` (tool-forced structured output, versioned system
  prompt, cost from configured prices, key via the secrets adapter).  Settings:
  `provider_backend=fixture` by default, budgets `provider_max_cost_per_order_usd` /
  `provider_max_tokens_per_order` → `budget_exceeded` stops the job, nothing skipped.
- `tariff_api.validators` (v1): 13 validators with ids and severities, each with a unit
  fixture; findings attach to candidates and force individual review.
- Stages `gridded → extracted` (runs, artefacts per channel, telemetry) and `extracted →
  validated → awaiting_review`; migration `0006_candidates`; API for candidates, findings,
  runs, the review queue and dispositions; web review queue page and candidates section.
- Rule change found by the fixture (headings v2): a repeated heading with a continuation
  marker (`RATE SCHEDULE LMV - 1 (continued)`) canonicalised to a different code, so the
  continuation page's candidates got the wrong category.  Continuation markers are now
  stripped.
- Adversarial fixture: an instruction-like row label and a `SYSTEM:` footnote; outputs
  unchanged except the extra row; nothing approved or published.  This proves the
  deterministic channel and the plumbing, not a model.

### Increment 8 (Milestone 3b: normalisation, clause outlines, grid integrity)

- `tariff_api.normalise` (rules v1, one rule id per transformation, original text kept):
  currency/unit/frequency from the value's own text only; `Nil` → state `zero` with no
  number + `nil_word`; `-`/`NA` → `not_applicable`; blank → `unknown`; bare marker →
  `footnote_only`; signed percentages with a named base; parenthesised negatives; bracketed
  secondary figures; Indian/western grouping; stray spaces flagged; cross-references and
  formulae as states.  `parse_slab` with explicit/inferred/ambiguous inclusivity, telescopic
  kinds and reference bounds; `check_slab_sequence` marks a twice-claimed boundary or a gap
  ambiguous.
- `tariff_api.clause_outline` (v1): clause paths from titles keyed by depth (state carries
  across pages), `PLUS` connector, `ALTERNATIVELY` alternatives closed by a sibling clause,
  roles from the title vocabulary with opposite signs for ToU discount vs charges, two-column
  metering-type binding, conditions kept as conditions, rule lines keep thresholds as
  parameters.  All F.3 M3 items for RGP, AG and HTP-1 pass on the clause fixture.
- `tariff_api.grid_integrity` (v1): header paths with span inheritance; label columns =
  every mostly non-numeric column; row paths with merged-cell propagation (within a grid and
  across the page break for a merged continuation, D.2 hazard 1); heading-less continuation
  inherits the header; unit binding cell → header → row-unit column → title → footnote with
  the source recorded and currency/denominator combined from different sources (KERC);
  footnotes attached; `resolved` only with header + row + unit; everything else flagged.
- Stage `tariff_worker.stages.grid` (`localised → gridded`, tool
  `grid@1+clauses@1+normalise@1`): refuses to run until the localisation record's
  `extraction_allowed` is true; reads `approved_schedule` / `approved_summary` only and
  lists skipped regions; rows in `structure_cells` / `clause_values`; per-grid, per-region
  and summary artefacts; queued by the reviewer's decision, re-run by a new decision.  API:
  `GET /sources/{id}/structure/cells` (page, unresolved_only, flag) and `/structure/clauses`
  (category, kind); detail carries `structure`.  Web: integrity summary, unresolved cells,
  clause outline.
- Fixtures: `structure_order_pdf` (merged cells over a page break with the header repeated,
  footnote, `% of Energy Charges` TOD with signed and zero forms, `Nil`/`-`/`NA`, Indian
  number, cross-reference, slab boundary claimed twice, heading-less closing page, derived
  Annexure-II), `gerc_structure_order_pdf` (the clause fixture over three pages),
  `tests/fixtures/text/gerc_clauses.txt`.
- Rule defect found by the fixture and fixed with a test (triage rules v2): a 3-row ruled
  rate table was classed `narrative` because its vertical strokes were shorter than the
  long-ruling threshold, so the readers never ran on it and the region had no grids.  Three
  horizontals crossing two verticals is now a table.  Migration `0005_gridded`; re-runs may
  go back to `localised` from `gridded`.
- Ledger: S5, S8, S10–S13, S15–S21, V1–V5 moved from n/a-yet to handled/detected with test
  ids; P21 added.  ADR-0011.

### Increment 7 (Milestone 3a: reading profiles and localisation)

- `packages/reading-profiles/profiles/*.v1.json` + `schema.json` generated from the pydantic
  model (`tariff_api.profiles`; drift test).  The schema expresses every Part D/E/F
  difference as data: representation, schedule-heading kind, unit placement, currency, ToD
  adjustment type, effective-rule type, scope, conversion factors, inventory expectations,
  locator cues with a `note` per cue naming the spec paragraph.
- `tariff_api.localisation` (rules v1): span locators open `approved_schedule`; it runs to the
  last schedule heading, over heading-less continuation pages, and closes at foreign
  material or an image-only run; page locators classify `approved_summary`,
  `existing_tariff`, `proposed_tariff`, `amendment_diff`, `formula_parameters`,
  `network_charges` (with sub-role), `loss_trajectory`, `green_tariff`, `illustrative`,
  `derived_not_tariff`; image-only runs are `other`; contents pages (dot leaders) never open
  a region; several/no approved candidates and profile-declared absent codes are blocking.
- Stage `tariff_worker.stages.localise`: profile detected from the heading inventory with a
  recorded rationale (or assigned by an administrator, audited, re-run); per-page text from
  the layer in reading order or the OCR artefact; immutable artefact
  `<sha>/localise/rules@1+profile@<ref>/document.json`; record + regions rows; state
  `localised` even when halted, so the halt is visible.
- API: `GET /profiles`; `GET /sources/{id}/localisation`; `POST
  /sources/{id}/localisation/decision` (reviewer+: confirm refused on ambiguous records,
  pages_viewed required, rationale required, optimistic version, audit with full before/after
  regions); `PUT /sources/{id}/profile` (admin).  Detail carries `reading_profile` and a
  `localisation` summary.  Web: checkpoint section with findings, region table with cues,
  and the reviewer form (confirm / correct with editable regions).
- Fixtures: `uperc_like_order_pdf` (14 pages, optional second annexure for the ambiguity
  case), `kerc_like_order_pdf` (12), `gerc_like_order_pdf` (11) following the three real
  layouts: contents pages quoting the locators, proposals, existing/proposed tables per
  ESCOM, derived ABR table, amendment diff, FPPAS chapter, scanned pages.
- Migration `0004_localise`; `0003`'s downgrade made data-safe (it dropped the column width
  under rows the parse stage had written; found by the round-trip test once the suite order
  changed).


### Increment 6 (first plan against the project)

- The operator ran `make tf-init tf-plan ENV=dev` on the VM against `tariff-order-parsing`:
  65 to add, 0 to change, 0 to destroy; the sources bucket adopted (IAM only), no load
  balancer, no IAP, no budget (`billing_account_id` empty), Cloud Run internal-only.  Nothing
  has been applied.
- Deployment defect found by reading that plan and fixed before apply: every Cloud Run
  service and job referenced `python:dev` / `web:dev`, images that cannot exist because the
  Artifact Registry repository is created by the same apply, and Cloud Run refuses a
  resource whose image is missing.  `make deploy-dev` also pushed only git-sha tags (never
  `:dev`) and did not update the `tariff-admin` job.  Now: `make bootstrap-dev` (targeted
  apply of APIs + registry, then build and push images tagged `:dev` and the git sha), then
  the full apply; `ignore_changes` on the image attribute so a deploy never shows as drift
  and Terraform never rolls a service back to the bootstrap tag; `GCP_PROJECT` falls back to
  the tfvars value before any output exists.  `terraform fmt` + `validate`: clean.
- `make bootstrap-dev` and the full apply ran on the VM: images pushed, everything created
  except the last resource, the worker-failure alert policy, which Google rejected because the
  log-based metric created seconds earlier was not yet queryable ("could take up to 10
  minutes").  Fixed with a creation-time wait (`time_sleep`, 180 s) between the metric and the
  policy; re-running the apply adds the policy.  Not yet re-applied.
- The three real orders are in the bucket at the golden sizes (see below); registration
  waits on `make deploy-dev`.

### Increment 5 (Milestone 2b: OCR, readers, grids, headings)

- Stage `triaged → parsed` (`tariff_worker.stages.parse`), chained after triage; page-batched
  checkpoints; resume after a hard kill without re-parsing completed pages (tested); a re-run
  at the same version replaces a page's grid rows and writes no new artefacts.  A stage
  re-run now cancels the queued downstream stage jobs of that source (found while testing:
  the parse job triage had chained ran first against the rolled-back state and failed).
- OCR (`tariff_api.ocr`): tesseract 5 as a subprocess with TSV output — every word has a
  confidence and a box; defaults dpi 300 / psm 4 chosen by measurement (psm 6 read 15% of a
  known page, psm 4 100%); `ocr_no_text` and `ocr_low_confidence` flags; OCR never replaces
  a text layer — where both exist their token-Jaccard agreement is stored and < 0.5 flags
  `ocr_layer_disagreement`.  Vector-drawn and grey pages OCR to zero words and stay
  unreadable: recorded, never guessed.
- Readers (`tariff_api.readers`): `TableGrid` from PyMuPDF `find_tables` and pdfplumber;
  ruling-line strategy first, whitespace strategy only on triage-classed `table`/`mixed`
  pages when rulings find nothing; grids paired by bbox overlap; classes `high_agreement`
  (≥ 98% cells equal), `minority_cell_disagreement` (≤ 20%, risk `reader_disagreement`),
  `structure_disagreement`, `primary_missing`, `secondary_missing`; an all-empty grid carries
  `empty_grid` (P1: pdfplumber returns a 20×6 grid of nothing on the vector page).
- Headings (`tariff_api.headings`, rules v1): `RATE SCHEDULE LMV – 1`, `TARIFF SCHEDULE
  LT-3(a)`, `11. RATE: HTP-1`, annexure, chapter, table captions; raw kept, canonical code
  unifies dash/space variants; consecutive duplicates on a page counted once (KERC habit);
  `repeated_codes` surfaces the same schedule seen twice.  Headings on OCR'd pages come from
  the OCR text and say so (`text_source = ocr`).
- Rule defect found by running over the fixtures and fixed with a test: the chapter pattern
  anchored only the start of the line, so 42 contents/prose lines beginning "Chapter n …"
  counted as chapter headings; a chapter heading must now be the whole line (number, optional
  short title, no dot leaders, no sentence).
- Schema 0003: `table_grids`, `document_headings`, OCR/parse columns on pages and documents,
  `stage_artefacts.tool_version` widened to 160 (composite tool version).  API: `GET
  /sources/{id}/tables` (filters page, agreement class, primary only), `GET
  /sources/{id}/headings` (kind filter), `parse` summary on the source detail, OCR fields on
  pages, `parse_source` accepted by the stage re-run.  Web: parse section (grids, agreement
  classes, OCR pages, tables needing review, grids-from-OCR pending, heading inventory) and
  per-page OCR/reader badges.
- Fixture `readers_and_headings_pdf` (5 pages: KERC duplicate heading + unruled table, GERC
  rate clauses, UPERC ruled table, a raster scan of that page, CHAPTER 6 + Table 6-7).
  Limitation recorded: PyMuPDF's base font renders an en dash as a middle dot, so the fixture
  heading uses a spaced hyphen; a single-glyph substitution is below the quality detector's
  threshold (ADR-0009, ledger D2).
- System dependency: `tesseract-ocr` + `tesseract-ocr-eng` in the Python image and CI.


### Increment 4 (Milestone 2a: page triage)

- Stage `inventoried → triaged` (`tariff_worker.stages.triage`), chained automatically after
  inventory; page-batched checkpoints; pages already triaged at the current rules version are
  skipped on resume; one immutable JSON artefact per page plus one per document under
  `<sha>/triage/pymupdf@<v>+rules@<v>/`, indexed in the new `stage_artefacts` table.
- `tariff_api.triage` — pure, versioned rules (`TRIAGE_VERSION = "1"`): eight page classes
  with a recorded rationale each (`unknown` when nothing matches); three independent
  text-quality components (glyph coverage, dictionary hit rate gated on token count,
  reading-order sanity) with separate flags; footer label extraction anchored to line ends;
  document-wide label rule inferred as segments of (style, offset) — singleton disagreements
  excluded, agreeing neighbours merged — and every page resolved with a recorded source.
- API: pages carry `label_declared/observed/source`, `text_quality`, `ocr_recommended`,
  `triage_rationale`; `?page_class=` and `?ocr_recommended=` filters; source detail carries a
  `triage` summary (class histogram, label rule, OCR/low-quality/unknown/label-flagged page
  lists) and its artefact index; `POST /sources/{id}/stages/rerun` (admin) re-runs a stage
  through the transition table, audited.  Web: triage section and per-page badges.
- Fixtures: `labelled_order_pdf` (12 pages: roman i–iii, then index − 3 with footer-less
  pages, a ruled table, a vector-drawn table with no text, an image-only page, a blank page,
  an annexure cover, one wrong footer) and `garbled_text_pdf`.
- Three rule defects were found by running the rules over the fixtures before locking
  thresholds, and fixed with tests: a weighted quality score let consonant soup pass; running
  prose ("see page 12 of the petition") was read as a footer label; a numeric table was
  classed `mixed` because prose was measured in characters rather than words.  A fourth in
  label inference: one wrong footer split a continuous rule in two.

### Increment 2 (dev-project wiring and bucket ingest)

- `infra/gcp/envs/dev.tfvars` and `dev.backend.hcl` carry the real values: project
  `tariff-order-parsing`, region `asia-south1`, state in `gs://tarifforderstudio_tfstate`.
- Terraform **adopts** `gs://tarifforderstudio_sources` instead of creating a source bucket
  (`var.existing_source_bucket`); artefacts/exports/backups are still created in `asia-south1`.
- The load balancer, managed certificate and IAP are created only when `var.domain` is set.
  With no domain (the current dev state) Cloud Run is `INGRESS_TRAFFIC_INTERNAL_ONLY` — no
  public endpoint exists at all.  The budget resource is likewise gated on `billing_account_id`.
- New `scripts/verify-gcp-setup.sh`: read-only check of project, billing and budget, the 15
  required APIs, both buckets (location, uniform access, versioning, public-access prevention),
  the presence of the three PDFs with their expected hashes, the `agent-builder` roles, and the
  VM's zone.  Prints OK / MISSING / DEVIATION with the fix command and exits non-zero on MISSING.
- **Bucket ingest**: `GET /sources/inbox` lists objects with registration state;
  `POST /sources/ingest` registers one by key.  The bytes are re-read and hashed, so an
  object's name is never identity; dedup, golden-manifest reconciliation and the inventory job
  are the same code path as a browser upload.  `ObjectStore.list` added to both adapters.
- Two test-quality defects found and fixed while writing those tests: the synthetic PDF
  generators were not byte-reproducible (PyMuPDF stamps timestamps and randomises the trailer
  `/ID`), which made every hash-based assertion vacuous; and the object store was shared across
  tests, so an immutable key served an earlier test's bytes.  Both now have tests
  (`test_synthetic_fixtures_are_byte_reproducible`, per-test `object_store_root` fixture).
- ADR-0008 records the dev topology and the two accepted deviations (multi-region source
  bucket; `roles/editor` on the build SA).  `CLAUDE.md` and `docs/build-spec.md` added.

## Deployment profile(s) exercised

- `local`: PostgreSQL 16.15 + pgvector 0.6.0 (apt packages, ephemeral cluster on :5433),
  filesystem object store, env secrets, local identity allow-list.  API + worker + Next.js
  web ran together end-to-end in this session (upload through the web proxy → inventory →
  detail page → authorized file reopen).
- `gcp`: adapters implemented (`GcsObjectStore`, `SecretManagerProvider`,
  `IapIdentityProvider`) but **not exercised** against real services.  Docker daemon was
  unavailable, so images were not built here; Dockerfiles are validated only by reading.

## Implemented user-visible behaviour

- Status page: readiness (DB, migration head, pgvector, storage), profile/adapters, tool
  versions, limits, queue depth, dataset counts; states plainly that coverage is empty.
- Source inbox: upload with dataset choice (real/fixture) and idempotency key; dedup result
  banner; list with state, page count, text-layer counts (unknown badges until inventoried).
- Source detail: pipeline stage track, latest job with live progress (`pages_done/total`),
  document metadata (PDF version, producer, encryption, tagging, fonts not embedded),
  golden-manifest reconciliation, page inventory table (index, declared label, size,
  rotation, text chars, text layer, images, drawings, class=unknown, role=unknown),
  authorized "open the PDF" link.
- Jobs page and Registry page (seeded jurisdictions/commissions/utilities, no coverage claim).
- Source detail (Milestone 2): triage summary and per-page class/quality/label badges; parse
  summary — primary grids, agreement-class histogram, OCR pages, tables needing review,
  grids-from-OCR pending, heading inventory with repeated codes flagged.
- API: `/healthz`, `/readyz`, `/status`, `/me`, `/sources` (POST/GET), `/sources/{id}`,
  `/sources/{id}/pages`, `/sources/{id}/tables`, `/sources/{id}/headings`,
  `/sources/{id}/stages/rerun`, `/sources/{id}/file`, `/sources/{id}/reprocess`, `/jobs`,
  `/jobs/{id}`, `/jobs/{id}/cancel`, `/registry`, `/utilities`, `/users`, `/audit`.
  OpenAPI at `/docs`.

## Exact commands to run and test

```bash
make install                      # uv sync --all-packages && pnpm install --frozen-lockfile
make ephemeral-postgres           # or: docker compose stack via `make dev`
export DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/tariff_dev
export LOCAL_USER_ALLOWLIST="admin@example.com:administrator,reviewer@example.com:reviewer,analyst@example.com:analyst"
make migrate seed
make api                          # :8000
make worker                       # long poller; `uv run tariff-worker --drain` for one pass
API_BASE_URL=http://127.0.0.1:8000 LOCAL_WEB_USER=admin@example.com make web   # :3000
make test                         # TEST_DB defaults to :5433/tariff_test
make lint && make contracts-check && make build-web
make tf-plan ENV=dev              # requires gcloud auth + filled envs/dev.tfvars (blocked here)
```

## Schema, API, adapter, and reading-profile changes

- Migration `0001_foundation`: datasets, users, jurisdictions, commissions, utilities,
  source_documents, source_pages, jobs, job_events, audit_events (append-only trigger),
  idempotency_records; enums dataset_kind, user_role, jurisdiction_kind, source_state (full
  Section 6.2 set), job_status; extensions vector, pgcrypto.
- Migration `0002_triage`: stage_artefacts, triage columns.  Migration `0003_parse`:
  table_grids, document_headings, OCR/parse columns, `tool_version` → 160 chars.
  `0004`–`0006`: localisation records, structure cells/clauses, candidates/findings/runs/
  dispositions.  `0007_conditions`: `condition_records` (verbatim provisions, footnotes and
  clause conditions, unique per source/page/line/kind/text hash).
- API contract exported to `packages/contracts/openapi.json`; types generated; no drift.
- Config: `ocr_engine/ocr_lang/ocr_dpi/ocr_psm/ocr_min_confidence`, `primary_reader`.
- Adapters: storage (filesystem, gcs), secrets (env, secret_manager), identity (local, iap).
- Reading profiles: none yet (`packages/reading-profiles/` holds a README; Milestone 3).

## Source files and dataset coverage actually used (hashes)

- **The three real orders are now in the bucket** (operator upload on 2026-09-13, listing
  pasted into the session): `inbox/NPCL_TariffOrder1-pdf72202631759PM.pdf` 6,314,646 bytes,
  `inbox/96731743148968.pdf` 21,755,322 bytes, `inbox/Gujaratdocument.pdf` 2,803,465 bytes —
  each size equals the golden manifest's `size_bytes` exactly.  The bytes are still not
  available in this build environment (no Google credentials), so **no hash has been
  verified and nothing has been ingested**; `tests/golden/manifest.json` keeps
  `bytes_present: false` until registration computes the SHA-256.  Expected hashes:
  `ff36813e…174b1a` NPCL, `d84997a4…95fcf50` KERC, `1c4697f8…95925e1a` GERC.
- The console-made folder placeholder `inbox/` (a zero-byte object) is now skipped by the
  inbox listing and refused by ingest before any bytes are read (found in that listing; tested).
- Synthetic fixtures only (dataset `fixture`): `mixed_text_and_image_pdf` (6 pages), `text_only_pdf` variants, `not_a_pdf`.

## Reading reliability ledger changes

`docs/reading-reliability.md` created with every Section 6.1 failure mode as a row.
Handled+tested: D5 (printed-label maps), P4, P6, P7, P8, P9, P10, P11, P12, P13–P15
(ingest, reproducible fixtures), P16 (immutable versioned artefacts), P17 (unknown is visible).
Increment 5: D1 and D8 moved to handled+tested (OCR runs, confidence recorded, nothing
guessed); D2 gains the single-glyph limitation; P1 (silent empty table) handled+tested; P18
(whitespace strategy invents tables) and P19 (KERC double heading) added and handled; S14
detected at inventory (canonical codes); S2 note (both representations' headings recorded).
Detected: D3, D7, D9.  Everything value- and network-level `n/a-yet` pending Milestones 3–4.
Increment 10: N2 (wheeling derivation), N5 (CSS approved vs formula), N7 (loss trajectory by
level), N11 (green-tariff exclusions) handled+tested; S2 (summary vs schedule) → VAL-16; S6
(amendment vs consolidated text) → VAL-05.

## Tests and evaluations executed, with results and denominators

Run in this session against PostgreSQL 16.15 on :5433 (`uv run pytest -q`), tesseract 5
installed:

- **237 passed, 0 failed, 0 skipped** (~80 s): 193 unit (13 adapters/profile/fixtures, 32
  triage rules, 31 readers/headings/OCR, 11 profiles/localisation, 60 normalisation, 10
  clause outline, 7 grid integrity, 21 extraction/comparison/routing/validators, 8
  network extraction/derivations/conditions/VAL-05/07/12/16), 44 integration (8 sources,
  6 ingest/CLI, 6 queue, 1 worker-kill recovery, 5 triage stage, 4 parse stage, 4
  localisation stage, 2 structure stage, 3 extraction/validation incl. the perturbed image
  channel and the adversarial fixture, 3 network/dual-representation/amendment stage runs,
  2 migrations).  Without tesseract the OCR unit tests and the stage tests from parse
  onward skip and say so.
- Increment 9 baseline was 226 passed (185 unit, 41 integration); increment 8 was 200 (162
  unit, 38 integration).
- Test-infrastructure defect found by the reordered run and fixed: the synthetic fixture
  generators were byte-reproducible only ~98% of the time.  MuPDF writes the regenerated
  half of the file `/ID` as a PDF literal string `(…)` when that is shorter than hex, and the
  normaliser matched only `<hex>`, so about one file in fifty kept a random ID and a
  different SHA-256 — the key that dedup, golden manifests and ingest tests assert on.  The
  normaliser now matches both string forms, fails loudly if it does not find exactly one
  `/ID`, and re-opens the result to prove no offset broke; probed 150 calls per generator,
  one hash each; two tests added (a 150-call check and the literal/escaped/nested form).
- Increment 4 baseline was 70 passed (43 unit, 27 integration); one earlier intermittent
  lease-expiry failure (2 s lease, 2.5 s wait) was fixed by widening the wait to 3.5 s.
- Worker-kill recovery: 1 hard kill (`os._exit(137)` after checkpoint `next_page=3`), lease
  2 s, resumed by a second worker; 6/6 page rows, 0 duplicates, attempts=2, events include
  `lease_expired_reclaimed`.
- Migrations: downgrade to base and upgrade to head (through 0004) in the suite: pass.
- `ruff check` + `ruff format --check`: clean.  `tsc --noEmit`: clean.  `next build`: success
  (8 routes).  `terraform fmt` + `terraform validate` (google 6.30.0 via filesystem mirror):
  valid, 2 provider warnings about `secret_data_wo`.
- Contract drift script (`pnpm --filter @tariff/contracts check`): executed, reports
  `contracts: no drift` against the committed `openapi.json` and `api.d.ts` (now including
  the inbox/ingest endpoints).
- End-to-end smoke (manual, this session): web upload → HTTP 201 → worker drained 1 job in
  0.04 s → detail page shows `inventoried` → file reopened via web proxy (6,714 bytes, same
  hash).
- Not run: container image builds (no Docker daemon), anything against Google Cloud.

## Real provider calls versus fixtures

**Zero real provider calls.**  Every extraction run so far used the `fixture` provider
(labelled on every run and every candidate; cost 0).  The Anthropic Messages API path exists
in `tariff_api.providers` but has never been executed: no key in this environment.  OCR
(tesseract, local) is the only non-fixture tool that has run.  The first real call should be
`tariff-api provider-smoke` (a two-cell synthetic input, cost printed) once
`ANTHROPIC_API_KEY` is in Secret Manager; that too has not happened.

## Reviewer decisions obtained versus pending

None required and none obtained.  The only candidates that exist were produced from synthetic fixtures inside the test suite (dataset `fixture`, provider `fixture`); no real-source candidate exists and nobody has reviewed anything.

## Review/publication status and completeness declarations

Nothing reviewed, nothing published, no coverage declared for any utility.

### Increment 3 (first real verification against the project)

`scripts/verify-gcp-setup.sh` was run on the VM by the operator.  Findings and what changed:

- **Two bugs in the verify script itself**, both fixed: `read` with the default IFS collapses
  consecutive tabs, so gcloud's empty fields shifted every bucket column left (it reported the
  public-access-prevention value as "uniform access"); and the billing check reported
  "billing account not linked" when the real cause was that the caller has no billing
  permission.  Bucket facts are now parsed from JSON (accepting both the `gcloud storage` and
  JSON-API field spellings), and the script distinguishes MISSING from a new **UNKNOWN**
  state — "could not verify" is never reported as "fine".
- **Two deployment bugs found by reasoning about the verify output**, both fixed with tests:
  with no domain `IAP_AUDIENCE` is empty, and `IapIdentityProvider` refused to construct — the
  API container would have crash-looped on first deploy.  It now starts and fails closed
  (refuses every request, logs a warning, shows `UNCONFIGURED` in `/status`).  And the worker
  and CLI were building an identity provider they must never have; `build_adapters` now takes
  `include_identity=False` for processes that serve no requests.
- **The build VM cannot reach the deployed system**: it is in the default VPC in `asia-south2`,
  while Terraform builds its VPC in `asia-south1` with private-IP Cloud SQL and VPC-internal
  Cloud Run.  Rather than widen the network, administration runs as a new `tariff-admin` Cloud
  Run Job inside the VPC, driving the same `tariff-api` CLI.  New CLI commands: `inbox`,
  `ingest`, `users add|list` (`--actor` must be an email, so the audit trail names a person).
- **A latent test-harness trap**, fixed: adapters were built in the FastAPI lifespan handler, so
  fixtures that touched `app.state.adapters` worked or failed depending on the order fixtures
  appeared in a test signature.  They are built eagerly in `create_app` now.

Outstanding on the project itself, for the operator: four APIs to enable
(`secretmanager`, `iap`, `cloudscheduler`, `cloudbuild`), object versioning on both buckets,
the three PDFs to upload, and the budget to confirm and its account id to paste into
`envs/dev.tfvars`.  Re-run the verify script after fixing them.

## Known defects and blocked acceptance gates

- **Blocked (M1 gate):** deployment to the `dev` project, migrations against Cloud SQL, Cloud
  Logging visibility, backup/restore on Cloud SQL, post-deploy integration run.  The project,
  billing, buckets, service account and VM now exist; what is missing is a run of
  `scripts/verify-gcp-setup.sh` + `make tf-plan/tf-apply ENV=dev` **on the VM**, since this
  environment cannot authenticate to Google.
- **Deferred by decision (ADR-0008):** IAP-protected browser access, pending a domain.  Until
  then Cloud Run has no public ingress and the API is driven from inside the VPC.  The
  web → API service-to-service identity token is written but untested.
- **Blocked (M1 gate):** "upload the real NPCL file" — bytes not supplied.  When supplied,
  registration will verify hash/size/page count/text-layer ranges against the manifest.
- Web → API service-to-service auth under the gcp profile needs a Cloud Run identity token
  (documented in `docs/deployment.md`); untested.
- Cloud documentation was not reachable (proxy 403); service limits/pricing in
  `docs/deployment.md` are to be re-verified before apply.
- Declared PDF page labels only; footer-derived printed labels and the offset map are
  Milestone 2.
- `apps/web` has no automated browser tests yet (Section 7.5 browser tests start when the
  review flow exists).
- Docker Compose stack and Dockerfiles untested in this environment (no daemon); the
  tesseract apt lines in `infra/local/Dockerfile.python` are therefore unbuilt here (the CI
  job installs the same packages and runs the OCR tests).
- `pnpm --filter web lint` (`next lint`) no longer works under Next 16 and CI does not run
  it; typecheck and build are the web gates.  To replace with an ESLint script.
- Grids from OCR word boxes are not built (`grid_from_ocr_pending`); the KERC vector-drawn
  charge tables will reach a reviewer OCR'd but un-gridded until then.
- Docling unmeasured; PyMuPDF is primary by decision (ADR-0009), to be revisited on real pages.

## Architecture decisions and rationale

ADR-0001 service boundaries · ADR-0002 migration owner + OpenAPI contract · ADR-0003
PostgreSQL queue with fenced leases · ADR-0004 platform adapters, filesystem local store ·
ADR-0005 PyMuPDF inventory tooling · ADR-0006 asia-south1, per-env projects, Cloud Run Job
worker (revisit in M8) · ADR-0007 fixture/real isolation via datasets · ADR-0008 no domain
yet, internal ingress, admin Cloud Run Job · ADR-0009 PyMuPDF primary + pdfplumber secondary
readers, tesseract OCR by subprocess, agreement classes, no grids from OCR yet.

## Next smallest actionable task

1. **Operator, on the `tariff-order` VM:** `git pull`, then `make tf-plan tf-apply ENV=dev`
   (the bootstrap already ran; `tf-plan` now runs `tf-init` first, which records the
   `hashicorp/time` provider the alert-policy fix added — the "Inconsistent dependency lock
   file" error seen on 2026-09-14 was exactly that missing init; expect the alert policy and
   its wait to be the only additions), then
   `make deploy-dev`, then register the three orders through the `tariff-admin` job
   (`docs/deployment.md`, "Loading the three tariff orders") and paste the job output.
2. Engineering (next run): Milestone 5 — reviewer workflow (individual and batch review
   with pages viewed, rationale, optimistic versions, audited decisions; corrections that
   re-run validators) and publication (versioned, reviewer-gated, never automatic).  Before
   any real extraction: `ANTHROPIC_API_KEY` into Secret Manager, `tariff-api provider-smoke`,
   then one small NPCL category set reported separately from fixture runs.  VAL-14 temporal
   consistency waits for a second order of the same utility.  Also Milestone 3 close-out on real material once the deploy is done
   (ingest, inventory, triage, parse, localise the three orders; a reviewer confirms; grid;
   compare with Parts D–F), grids from OCR word boxes for the Karnataka vector tables, then
   Milestone 4 (versioned tariff schema, provider adapter with fixture mode, dual-channel
   candidates, validators).  As soon as the deploy is done — ingest, inventory,
   triage, parse, and compare with Parts D–F (NPCL 402–423 `image_only` now OCR'd; KERC
   226–240 `vector_graphics_text_sparse` and the printed 209 → PDF 225 rule; GERC all-text
   with roman front matter and the −16 rule; NPCL exactly 15 `RATE SCHEDULE` headings and no
   LMV-10).  Then Milestone 2 close-out: grids from OCR word boxes for the KERC charge
   tables, and a Docling measurement on real pages behind the reader interface.  Then
   Milestone 3 (localisation and reading profiles).
