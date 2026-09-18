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
derivations, amendment consistency, condition records, cross-representation agreement;
(11) Milestone 5a — reviewer workflow: decisions with rendered-evidence and stale-version
enforcement, corrections with cause tags, second review, undo, checklist, telemetry; (12)
Milestone 5b — publication transaction, published facts and evidence, explorer and
open-access view.

## Current milestone and status

- **Milestone 0 — complete.** Repository was empty (no commits); audit, ADR-0001…0007,
  architecture, data dictionary, reliability ledger skeleton, error taxonomy, evaluation
  plan with the D/E/F question set, deployment doc, milestone checklist all written.
- **Milestone 1 — implemented and tested under the `local` profile; deployed to `dev` on
  2026-09-14 (operator, on the `tariff-order` VM).**  Terraform applied in full against
  `tariff-order-parsing` (65 resources over three runs; the failures on the way — missing
  `hashicorp/time` in the provider lock, a missing Service Networking Admin role, the Cloud
  SQL edition default — are each recorded in `docs/deployment.md` with their fix).
  `make deploy-dev` ran the migrate job against Cloud SQL and updated the four services and
  jobs; `make smoke-dev` reported `/readyz` HTTP 200: PostgreSQL 16.15, migration head
  `0009_publication`, pgvector 0.8.5, all three buckets reachable through the object-level
  probe (the first probe used bucket metadata and failed on the least-privilege service
  account — fixed).  **All three real orders registered and read through localisation** by
  the scheduled worker on 2026-09-14: SHA-256 and page counts equal the golden manifest
  (NPCL 423, KERC 570, GERC 184 pages); each is at `localised`, the reviewer checkpoint.
  **Manifest deviations found by the real bytes** (recorded in `tests/golden/manifest.json`
  as `observed_on_registration`, expectations left as the specification stated them so the
  mismatch stays visible): NPCL has a text layer on all 423 pages, where the specification
  says 402–423 are image-only scans with no text layer; GERC has no text layer on PDF pages
  2 and 4, where the specification says all-text; KERC matches (and also has a text layer
  on the pages the specification calls scanned).  Whether the NPCL scans carry an embedded
  OCR layer is decided by the triage page classes and text-char counts, visible on the
  source page once a reviewer signs in — not assumed here.  Localisation: NPCL proposed
  (46 regions, no blocking finding), GERC proposed (41 regions), KERC **ambiguous** (50
  regions, 1 blocking finding: more than one approved-schedule candidate, as Part E's
  summary-plus-annexure layout would produce) — the reviewer corrects it at the checkpoint.
  **What the reviewer's first look at the NPCL page taught (2026-09-14)**, each fixed with
  a versioned rule or profile change and a test: (1) pages 402–423 are scans with a
  page-number footer as their only text (21–80 chars over a page-size image), so
  `has_text_layer` was true and triage classed them `annexure_cover` — triage rules v3 class
  a sparse-text page over a page-size image as `image_only` and route it to OCR (page 418
  is a real text page with a table, so the specification's "402–423" is one page too
  wide); (2) the approved schedule was localised exactly as Part D says (352–400, 401
  derived, green tariff 359–360); (3) the v1 banking cue `\bbanking\b` matched "internet
  banking" and "Banking and Finance Charges" (a financing cost) on seven pages — profiles v2
  tighten it to banking of power/energy, banked units, or banking next to open access
  (all three profiles, so the same noise does not reach the KERC/GERC reviews); (4) the
  heading inventory has 14 rate-schedule codes against the profile's 15 — one `LMV-4`
  where Part D lists `LMV-4(A)` and `LMV-4(B)`; recorded as a warning, to be settled by
  looking at the LMV-4 heading in the PDF, not by editing the expectation; (5) 34 footer
  observations conflict with the label rule (table numbers read as labels) — the rule is
  right and the conflicts are listed, precision of the footer reader is a later fix.
  Admin-job commands `assign-profile` and `rerun` exist so the operator can bind profile
  v2 and re-triage without the API.  **Verified on dev (2026-09-14, second look):** after
  `rerun triage_source` the NPCL page shows rules@3 with 402–417 and 419–423 as
  `image_only` (OCR'd, low-confidence pages flagged), profile `uperc-npcl@2` bound and the
  localisation re-proposed with the same schedule regions and the banking cue now firing
  only on "banked power" (p. 33) and "BANKING OF POWER" (p. 227).  (6) The manifest
  verdict on the page was stale — it was frozen at inventory time against the manifest
  baked into that image (expected 22 pages without text layer) after the manifest had
  been corrected to 0 — so the source detail and `sources --json` now re-check the
  persisted inventory facts against the current manifest on every read
  (`golden.current_check`, unit-tested); the stored record stays as the registration-time
  history.  (7) The source page was a flat dump (423 inventory rows, 299 table captions,
  every page list spelled out); it now leads with the one next action (yours or the
  worker's), keeps every section collapsible with a one-line summary, renders page lists
  as ranges, shows only flagged pages by default, and derives page roles from the
  localisation regions; the inbox shows the next step per source.  (8) Reviewer
  comments per region (`localisation_regions.reviewer_note`, `excluded`), asked for after
  the NPCL banking regions turned out to describe the utility's own inter-state banking of
  power rather than the open-access banking rule: a reviewer annotates any region from the
  checkpoint table, optionally excluding it; the structure and extraction stages skip an
  excluded span (`regions_excluded` in the structure summary, `excluded_regions` in the
  extraction summary) and the note follows the family into the review checklist so the
  disposition is taken with the reason in view.  Reviewer role, `expected_version`,
  audited, frozen once candidates exist, carried across a localise re-run for an
  unchanged span; `test_network_stage.py`.  (9) "Confirm localisation is not working": the
  button was disabled until the pages-viewed box was ticked and a five-character rationale
  typed, and said nothing about it.  Reproduced in headless Chromium against the local
  stack (click on the old build did nothing; the API stayed `proposed`).  The form now
  always accepts the click and states what is missing, shows API errors above the button
  with the request id, and turns a non-JSON answer (an expired IAP session) into a
  readable message; the same run on the new build recorded `confirmed` and queued the
  structure stage.

  **Increment 13 (2026-09-16): CSS as a computation, transmission references, Docling as an
  optional reader.**  (a) `tariff_api.css_formula` (spec 5.1, VAL-07 derivation rule): inside a
  `cross_subsidy_surcharge` region the extractor recognises the formula statement
  `S = T − [C/(1 − L/100) + D + R]` and the symbol definitions in the page text, reads the
  parameter tables (T, C, L, D or its parts DC + TC + WC, R, the printed computed S, the
  printed cap) per voltage level with a cell citation for every input, recomputes S and
  attaches the whole derivation to the approved candidate at that level
  (`derivation.formula`).  A level with a printed computed S but no approved row becomes its
  own candidate; a level with inputs and nothing printed is listed as missing, never computed
  into a value.  VAL-07 v2 compares the recomputed S with the printed one (tolerance: the
  printed rounding), the printed cap with 20% of T and the approved value with the cap; each
  mismatch blocks, agreement is an info finding.  The explorer's network view prints the
  formula line under the value.  Fixture: an NPCL-style page (formula, definitions,
  D = DC + TC + WC table, parameter table) in the synthetic network order;
  `test_network_stage.py` asserts inputs, evidence pages, recomputation, cap and findings.
  Extraction rules 2, validators 2.  **Not yet run on the real NPCL pages 316–318**: that
  happens when the operator drains the queue after the confirmed localisation; the page-317
  wording the reviewer quoted matches the patterns here, the table layout does not until seen.
  (b) A transmission loss or charge named as an input of an open-access determination
  ("Intra-State Transmission Loss (3.18%) … as determined … order dated …") is captured in
  the `transmission_reference` family with value, unit and the instrument it points to
  (`by_reference`), never as a transmission tariff of its own.  (c) Docling: installed as the
  optional extra `tariff-api[docling]` (6 GB with torch), reader adapter written and
  unit-tested against Docling's table model, `tariff-api reader-measure` added — and the
  measurement **not done**: this build environment cannot reach huggingface.co for the
  models and refuses the CPU torch index; ADR-0009 addendum records the promotion rule,
  `docs/deployment.md` the VM commands.  Pipeline behaviour is unchanged by (c).  Karnataka
  and Gujarat localisations remain unreviewed.

  **Increment 14 (2026-09-16): the first real extraction, and what it taught.**  NPCL reached
  `awaiting_review` with 370 candidates and 261 findings; the reviewer's reading of the page:
  the retail tariff appeared missing (it was there, hidden behind an alphabetical first-100
  list), the network families were flooded with numbers that are not determinations (every
  numeric cell of ARR working tables on pages 56, 171, 195 and 218 read as a loss or an
  additional surcharge; the CSS computation table on page 319 read as open-access losses), and
  the review workspace showed header/row paths instead of saying what was read and why.
  Fixed, each with a test: (1) a loss candidate must be a percentage at a level or for a year,
  a charge candidate must be named in its row or column and carry a per-unit basis, and any
  other amount table (Rs crore, MU, revenue, ARR) is skipped with a note; a grid that names
  no family is read only under a loss or CSS sub-role; (2) the CSS parameter tables are looked
  for in every network region (regions overlap), levels are keyed as readable voltage bands
  (`11 kV, up to 66 kV`), so page 319's `D = PC+TC+DC+WC` table feeds the formula instead of
  the loss family; (3) the paragraph that states per-level open-access losses ("for open
  access consumers connected at 33 kV, 0.79% distribution loss shall apply") yields `oa_loss`
  candidates with the sentence as evidence; (4) every candidate now carries `rationale` (a
  rule-written sentence naming table, row and column) and `context` (the caption above the
  table, sentences on the page naming the row or the value, the profile's note on the
  region), schema 2; (5) the queue has a `document` order — schedule categories first, fixed
  before energy, then the open-access families in page order — which the workspace uses by
  default (the API default stays `risk`, as Section 7.2 specifies); (6) the workspace was
  rewritten around one candidate at a time: the value in words ("Rs 6.50 per kWh per
  month"), where it was read as a sentence, what the order says around it, the surcharge
  arithmetic when there is one, what the checks found, the page with the table outlined, and
  Approve / Change / Reject / Cannot decide with the reason box; a sidebar lists the groups in
  document order.  The NPCL extraction must be re-run to pick up (1)–(4)
  (`rerun … extract_source`); the numbers above are from the run before these fixes.

  **Increment 15 (2026-09-16): rate blocks, category summaries, the table as read.**  From
  the reviewer's second look (NPCL HV-1, page 384): the two tables under "(a) Commercial Loads
  …" and "(b) Public Institutions …" are two consumer groups of one category, and the
  candidate shown as the fixed charge carried the energy-charge cell.  (1) Retail candidates
  now carry `applicability.rate_block`, the lettered block above their table, read from the
  page text and part of the candidate key; the workspace title shows it.  (2) Every schedule
  category gets a generated summary (`category_summaries`, `GET /sources/{id}/summaries`):
  in fixture mode a template that reads the candidates back by rate block; with the real
  provider, prose from the same inputs under a prompt that allows only printed numbers and
  requires component, unit and applicability per rate.  A deterministic grounding check
  lists any number the pages or candidates do not carry; the workspace shows the summary at
  the top of each category with its grounded/unsupported badge and the label "generated ·
  not a fact".  Summaries are never published and never feed a validator.  (3) The workspace
  can show the table as the reader read it (`GET /sources/{id}/tables/{page}/{ordinal}/rows`,
  primary and paired secondary grid, cited cell highlighted) so a column shift is visible on
  the spot and a `header_misbound` correction points at the reader.  **The page-384 shift
  itself is not yet diagnosed**: it needs the grid as read, which the operator can now paste
  from the workspace.  Fixture summaries are exercised end to end in `test_extract_stage.py`;
  no real-provider summary has been generated (no key).  **VAL-19 unit consistency** (validators
  3): a retail component priced per a unit it cannot be priced per (a fixed charge per kVAh,
  an energy charge per kVA per month) blocks with the likely cause named — the neighbouring
  column's cell, a column shift in the reader or the header binding — and a row whose fixed
  and energy cells share a unit warns; this catches the page-384 shift before a reviewer
  does, whatever reader produced it.  Terraform `provider_backend` (dev: `anthropic`) sets
  `PROVIDER_BACKEND` on the worker and admin jobs; the key is added to Secret Manager from a
  terminal prompt, never from a file (`docs/deployment.md`).  **The page-384 shift, diagnosed
  from the table-as-read panel**: the readers (both, in high agreement) returned nine columns
  for a three-column Word-exported table — heading in one sub-column, number in the next,
  blanks between — and the empty heading cells inherited the heading to their left, so the
  energy cell bound to "Fixed Charge".  Grid rules 2 collapse adjacent columns that never
  both carry text on the same row before binding headings (`collapse_split_columns`, flag
  `split_columns_merged`), while every cell keeps citing the reader's own column so the
  outline and the panel stay true to the grid; unit-tested on the exact shape.  The NPCL
  structure stage must be re-run (`rerun … grid_source`) for it to take effect.  The real
  provider is not yet proven: the first smoke failed on a missing HTTP client in the image
  (now a declared dependency), the second is unexplained until its log lines are read —
  `make admin-dev` now prints the job's own output after every run.  **Root cause, reproduced
  and fixed at the reader (readers 2, parse 2)**: the schedule's heading rows are shaded, and
  Word draws the shading as a borderless filled rectangle inset from the cell border; both
  readers took its edges as rulings, so every column became three and heading text was even
  sliced mid-number (HV-2, page 387: "For supply up to 1" | "1" | "kV").  A synthetic page with
  one shaded heading row reproduces the nine-for-three split exactly.  PyMuPDF's
  `lines_strict` strategy and a pdfplumber page filtered of borderless fills read the same
  table as three columns; the parse stage now reads both ways and prefers the strict twin per
  table (`prefer_strict`, IoU ≥ 0.5), so a table whose borders are themselves fills keeps the
  plain reading.  The split-column merge in the structure stage remains as a second line of
  defence.  NPCL must be re-parsed (`rerun … parse_source`), which re-runs localisation and
  reopens the checkpoint; region notes carry over.  The reviewer also asked for the
  time-of-day structure and rates to be captured — the schedule extractor already reads
  time-band rows as `tod_adjustment`; whether NPCL's ToD table survives the reader fix is
  checked on the re-run.

  **Increment 16 (2026-09-17): the model feedback loop (ADR-0016).**  After the channels
  and before validation, the model sees each category's candidates with Haystack-retrieved
  passages from its own pages and returns per value a verdict, a confidence, the consumer
  sub-category in the order's words, a one-sentence meaning and a verbatim quote; quotes are
  grounded mechanically, low confidence and contradictions add risk tags and force individual
  review, a grounded sub-category fills an empty rate block, and no value ever changes.  Shown
  as "Model check" in the workspace.  Fixture mode runs the same loop with a template
  (unit-tested for grounding, tag raising and the no-change rule; end to end in
  `test_extract_stage.py`).  `haystack-ai` added to the API package for the document store
  and BM25 retriever; the model call stays on the provider adapter.  **Not yet run with the
  real provider**: the smoke on dev is still unproven.
  **Increment 17 (2026-09-17): the rules are always the structure channel; the model reads
  pages in chunks; stacked rows split; CSS inputs keyed by category and band.**  The first
  real NPCL run showed the flaw: with the anthropic backend the model was handed the
  serialised structure of the 49-page schedule in one call and returned one retail candidate
  (HV-1 fixed, 7.70/kVAh, itself a mis-bound cell); the rules that had read every row in
  fixture mode were not a channel at all.  Now `rules_result` is the structure channel for
  every backend (run rows carry provider `rules`, cost 0, neither fixture nor model;
  `extraction-runs` reports `rules_runs` separately) and the model reads the page images
  as the independent second channel, `IMAGE_CHANNEL_PAGES_PER_CALL` pages per call (default
  2; the fixture channel is not chunked because it is derived from the rules) with a prompt
  that names the rate-schedule heading in force above the chunk, the profile's code shape
  and the fields a candidate must carry to pair with the rules (category code, lettered
  block, component, voltage, exact value and unit).  Chunk results are merged for the
  comparison; every call is a run row for cost.  Readers 3 / parse 3: a ruled row whose
  numeric cells stack the same number of printed lines is split into those rows (NPCL page
  316, the CSS computation table, read as one row per voltage group with six values in each
  cell); two-line headings and wrapped prose never split.  Grid 3: a row whose only text is
  a voltage (`----- 33 kV -----`) is a divider that scopes the rows under it and emits no
  cells.  CSS: bare `T`/`D`/`R`/`C`/`L`/`S` column headings are recognised; parameters are
  keyed `HV-1 @ 33 kV` (category and band), the approved row pairs by both, a category with
  inputs and a printed S but no approved row becomes a formula candidate, and the `L` column
  of a consumed table is a formula input, never an open-access loss (the 15.56% shown as
  `oa_loss` on 2026-09-17).  Review policy: `SECOND_REVIEW_FIRST_ORDER` is now a Terraform
  variable; dev sets it false (one reviewer on the project; material conditions and formula
  components still need two).  A stub model in `test_extract_stage.py` proves the real-mode
  path: the model is never asked for the structure, image calls carry at most two pages,
  and every rules candidate is matched.  **Not yet run on dev**: the NPCL re-extraction
  with these changes is the next operator step; the page-316 split and the divider rows
  were built from the reviewer's description of the table and are proven on a synthetic
  copy of that shape, not yet on the real page.
  **Defect found by the first deploy of increment 17 and fixed the same day:** the
  extraction-runs endpoint imported the provider module, which imported the assessment
  module, which imported Haystack at module level; the API process then took seconds and
  tens of megabytes to start (9 s on the build machine, longer on one Cloud Run CPU),
  overran its start-up probe, and the review workspace showed "The API is not reachable
  (fetch failed)".  Haystack is now imported only inside the retrieval functions, the
  constant the endpoint needed lives in the extraction module, and a test starts the
  application in a subprocess and asserts Haystack is not loaded.
  **Second defect from the same deploy (the first real chunked run):** the model wrote
  `"unknown"` into a candidate's `value` (a decimal string or null by schema); one such
  row in one chunk failed the whole call, the job was retried three times from the start
  and the extraction failed with `retries_exhausted`, each attempt billed.  Now each model
  candidate is coerced where the intent is unambiguous (a non-numeric value becomes null
  with `value_state` unknown and `value` listed as missing, a numeric value becomes its
  string) and validated on its own; a row that still fails is dropped and listed under
  the run's `missing` and `raw.rejected_candidates`, never the chunk.  A schema failure
  that survives that is no longer retried (`ProviderUnavailable(retry=False)`), because
  the same input fails the same way and a retry only repeats the cost.  The three failed
  attempts' cost is on the provider's bill, not in `extraction_runs` (a failed call writes
  no run row; recording failed-call usage is an open item).
  **Third defect, next run:** the model returned the candidates list as a JSON string cut
  off mid-object — its output limit reached while writing a two-page chunk — and the
  string could not be parsed.  Now the complete objects at the front of a cut array are
  kept and the cut is noted on the output's `missing` and the run record (`truncated`),
  and a chunk whose call was cut or stopped on `max_tokens` is re-read one page per call;
  the cut call stays on the run record for its cost.  Proven with a stub model that
  "loses" every two-page call: every page is re-read singly and every rules candidate is
  matched.
  **First successful real run (2026-09-17, after the three fixes):** NPCL extracted on
  `claude-sonnet-5`; HV-1 shows 15 candidates over pages 383–387 with both lettered blocks
  and a grounded category summary.  Two things seen on the first candidate are open: its
  evidence cites "(unlabelled row)" and a column path of all three headings, which is the
  model channel's way of citing (row and column as counted on the image), so either the
  rules channel missed that row or the workspace shows the model's record — `tariff-api
  page-dump <source> --page 384` now prints the grids, cells and candidates of a page as
  JSON so the operator can settle it without the browser; and the model check contradicted
  a correct value by matching block (b)'s table to a block (a) candidate — assessment
  prompt 2 says a passage from another lettered block is not a contradiction.  Context
  under "What the order says around it" no longer shows table fragments as sentences and
  starts with the lettered block.
  **Page-dump verdict on the HV-1 citation (2026-09-18):** both page-384 tables were read
  correctly (two grids, eight cells, right values); the rules gave *both* tables block
  (a) because the block finder anchored on the first line matching the row label ("For
  supply at 11kV" appears under (a) and again under (b)), so the (a) and (b) readings
  collided on one identity and the (a) table's four values were dropped as duplicates;
  the eight "unlabelled row" candidates were the model channel's, which never paired
  with the rules because it names the block by its letter and puts the row label in
  `voltage`.  Fixed: the block is found per grid in reading order (each table anchors
  after the previous one; wrapped block text is joined to the colon across blank lines);
  a candidate key compares texts normalised and a lettered block by its letter; the
  channel comparison pairs a rules row with a model row on block letter and row label
  however the two spell them; the image prompt (3) says description is the row label and
  the block is verbatim; a reviewed candidate from an earlier reading that the current
  reading no longer produces is tagged `stale_reading` (the 7.70/kVAh "fixed charge"
  approved once on 2026-09-17 is such a row: reject it in the queue).  Proven on a
  synthetic copy of page 384's text and grids; not yet re-run on dev.
  **Increment 18 (2026-09-18): the tariff table.**  The operator's verdict after the first
  real HV-1 review: one candidate at a time will not scale to 28 states.  New screen
  `/sources/<id>/review/table`: one card per category in document order, one grid per
  lettered block, rows as printed, fixed / demand / energy / other charges as columns;
  every value shows its words, whether the two readings agree (or what the model read
  instead), its review status, blocking checks and the model check's disagreement; approve,
  reject (with a recorded reason) and note (recorded, value stays undecided) on every
  cell; "Approve all agreeing" per category; "Change" hands off to the one-at-a-time
  workspace for corrections.  The rendered-evidence rule is kept, not bypassed: a new
  endpoint renders a page once with every cited table outlined and issues one evidence
  view per candidate on that page (`GET /sources/{id}/review/pages/{n}/image?candidates=`),
  the screen shows that page beside the table before any value on it can be approved,
  and each decision still goes through the same decision endpoint with its version, view
  id and audit event (integration test: views issued per candidate, decisions accepted
  with them, a candidate on another page still refused).  The queue and the source page
  link to the table first.  Not yet used on real material: dev needs a deploy and the
  NPCL re-extraction from increment 17.
  **Increment 19 (2026-09-18): what the first full NPCL table showed, and three reviewers.**
  The table (283 values) read the rate schedules correctly but slowly for a reviewer:
  the same rate read twice (table and clause: time-of-day rows, HV-3; a table repeated
  under a second heading: LMV-4), slab labels missing from row names, HV-2's voltage lost
  from column headings, plus and minus signs on time-of-day rates not shown, HV-4's list
  of industries read as charges, BHP versus HP counted as a disagreement, "<UNKNOWN>" as
  a category.  Rules 3 fixes each (duplicates merge into one candidate citing both
  places; unitless numbers under no charge heading are skipped; a voltage column heading
  becomes the row's voltage; block text stops at the table; unit aliases and trailing
  zeros are equal to the comparison; placeholder categories are cleared), each with a
  unit test on the shape seen.  The tariff table gained a category sidebar with progress,
  denser cells, row labels that carry the slab, signs on percentages, the model's
  one-line meaning under each value as the reviewer's cue, and "General provisions" for
  values tied to no category.  Reviewer assignment: `assigned_to` on sources, a reviewer
  takes an order or an administrator assigns one, the queue filters by assignee and shows
  open categories per order, `tariff-api assign-reviewer` for the admin job.  Plan agreed
  with the operator: three reviewers, one per ten commissions, in parallel.  Not yet
  re-run on dev.
  **Increment 20 (2026-09-18): commission folders, users in the app, JSON export.**  The
  operator's target: aayuda.energy creates users, makes one folder per commission, uploads
  each distribution company's orders there, assigns commissions to reviewers, and hands
  whole orders to engineering as files rather than pasted screens.  Built: an order
  belongs to a utility (`utility_id`, migration 0013; chosen on the upload form or named
  on ingest), the utility's active reading profile binds at registration (no detection,
  no CLI) and the commission's reviewer is inherited; `/commissions` lists each
  commission with its utilities, orders by state, open values and reviewer, and an
  administrator assigns a commission with cascade to its unassigned orders; `/admin/users`
  adds, re-roles and disables users through the existing audited endpoints; the source
  list filters by commission, utility and assignee; `GET /sources/{id}/export.zip`, the
  "Download everything as JSON" link and `tariff-api export` write the whole pipeline
  state as JSON files (bucket under `COMMISSION/UTILITY/`, local folder, or zip), and
  `exchange/` in the repo is the agreed place to commit them for engineering.  Sign-in
  stays Google through IAP: the recommended set-up is one Google Group in `iap_members`
  so the app's user list and the group are the only two places to add a person.  The
  tariff table hides the page panel until a page is shown.  Rules 3 also merges
  duplicates across row spellings and families, skips serial-number columns even when a
  unit was bound from the notes, and carries column headings that name a consumer group
  (Nagar Nigam, Nagar Palika) into the row.  Not yet deployed; the worker already runs on
  a Cloud Scheduler every five minutes, so on dev "click extract" is: confirm the
  localisation and wait.
  **Still open in the M1 gate:** Cloud Logging
  is visible (worker logs read through `gcloud logging read`); the backup/restore drill on
  Cloud SQL (Milestone 8) and the post-deploy integration run remain.
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
- **Milestone 5 — parts (a) and (b) implemented and tested under the `local` profile
  (ADR-0013, ADR-0014).**  (a)
  Per-order review queue in risk order with filters; completeness checklist derived from the
  heading inventory; evidence rendering that records the view (`evidence_views`); decisions
  (`approve` / `correct` / `reject` / `unresolved`) that refuse without the reviewer's own
  rendered evidence, with a stale version, without a rationale, without a cause tag and
  evidence selection for a correction, or by the first reviewer at second review; corrections
  keep the extractor's record and re-run the validators; second-review policy (material
  items, formula components, corrected channel disagreements, first order from a utility);
  batch approval limited to clean high-confidence candidates, each with its own evidence;
  undo from the decision's snapshot with history intact; idempotent decisions; audit events;
  telemetry without document text; web workspace `/sources/{id}/review` (side by side,
  keyboard-first, decision rendered only from the API's response).  (b) Publication as a
  preview-then-confirm transaction over a declared scope with a completeness declaration
  (`complete` refused on missing required items; `partial` must list every gap and is
  labelled partial everywhere); published facts and evidence in their own tables, copied
  from the effective records of finally approved candidates, with citations derived in code
  (pdf page, printed label, table id, cell, excerpt); cumulative releases that supersede
  the prior one; published decisions frozen; the explorer (category tree, completeness
  banner, citation drill-down to the rendered page) and the open-access / network-charges
  view; an API-layer test that the explorer module never touches candidates and that a
  pending candidate never appears.  **Not built:** structured interpretation of condition
  records; the reader-grid toggle in the workspace; browser tests (Section 7.5); a cache
  (nothing to invalidate yet: explorer reads the current release per request).  **The
  Milestone 5 gate's real-order part is blocked**: no real candidate exists (no deploy, no
  provider run) and no reviewer has
  decided anything real.
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
- **Reviewer access without a domain (ADR-0015, increment 13):** the API's `google_id_token`
  identity adapter (verified Google ID tokens, exact audiences = our Cloud Run URLs, roles
  from `users`), the web service forwarding the user token and minting its own service
  token, Terraform selecting the adapter by the presence of a domain, and the
  proxy-over-SSH runbook in `docs/deployment.md`.  The proxy path needs a laptop terminal
  the operator does not use, so on the operator's explicit authorisation (2026-09-14) the
  web service gets IAP directly on Cloud Run (`web_iap = true`: public `run.app` URL behind
  Google sign-in for `iap_members`; API stays internal and verifies the IAP assertion).
  **Exercised on 2026-09-14**: the operator signed in through IAP at the web service's
  `run.app` URL; `/status` reported `identity=iap`, database and storage ready, the operator
  registered as administrator.  Three platform facts learned on the way, each recorded in
  `docs/deployment.md`: a Terraform apply with the pinned provider clears the IAP flag (now
  re-enabled by `make deploy-dev`); the web service's egress must be `ALL_TRAFFIC` for its
  calls to reach the internal-only API; Cloud Run strips `x-goog-*` identity headers on
  delivery, so the web service forwards the assertion as `X-Forwarded-IAP-Assertion`.
- **No provider connection, no extracted number exists.**  The only reviewer decisions that
  exist are localisation confirmations on synthetic fixtures made by the test harness's
  reviewer user; no real-source region has been confirmed by anyone.

### Increment 12 (Milestone 5b: publication, published facts, explorer)

- Migration `0009_publication`: `data_releases` (scope, completeness, gaps, consequences
  at publication, checklist snapshot incl. dispositions, preview token, current /
  superseded), `published_facts`, `published_evidence` (with printed page labels),
  `candidates.published_release_id`, `source_documents.publication_summary`.
- `tariff_api.services.publication`: `preview` (facts to publish, pending / awaiting second
  review / unresolved / blocked-by-findings candidates, missing required items for
  `complete`, gap keys required for `partial`, prior release, token over the in-scope
  candidate state and the source version) and `publish` (state, `expected_source_version`,
  token, `confirm_consequences`, blocked candidates, completeness rules, nothing-to-publish;
  copies facts and evidence, supersedes the prior release, transitions the source to
  `published` or bumps its version on a re-release, audits).
- Routers: `publication` (`/sources/{id}/publish/preview`, `/sources/{id}/publish`,
  `/sources/{id}/releases`) and `explorer` (`/explorer/releases`,
  `/explorer/sources/{id}/tariff`, `/explorer/sources/{id}/network`, `/explorer/facts/{id}`,
  `/explorer/facts/{id}/evidence/{n}/image`), the latter reading only the published
  tables.  `SourceDetail.publication` summarises the current release.  Review decisions
  stay possible on a `published` source for candidates no release has published; decide
  and undo are refused on published candidates.
- Web: `/explorer` (current releases, real and fixture counted separately),
  `/explorer/{id}` (category tree, components, units, value states, applicability,
  conditions, citations linking to the rendered cited page, completeness banner),
  `/explorer/{id}/network` (screen 6a: per family, published facts with derivation inputs
  and decision status, or coverage insufficient with the reviewed disposition),
  `/sources/{id}/publish` (releases so far; scope → consequences → completeness
  declaration with per-gap reasons → rationale → confirmation → publish; result rendered
  only from the API's response; stale token explained).  Nav gains Explorer.
- Tests: `tests/integration/test_publication_and_explorer.py` (explorer module source has
  no candidate import; coverage-insufficient before any release; preview by reviewer only;
  complete refused with `extra.missing`; partial refused with `extra.undeclared_gaps`;
  nothing-to-publish; stale token after decisions; stale source version; unconfirmed;
  analyst refused; subset partial release → source `published`, facts and citations match
  the approved candidates' evidence, a pending candidate never appears, fact detail and
  evidence image, network view with the banking disposition, release list counts fixture
  separately; undo of a published decision refused; decisions continue after publication;
  second cumulative release supersedes the first; audit events by two actors).
- Honest limits: no cache exists, so "cache invalidation" is by construction (ADR-0014);
  the coverage dashboard (screen 1) is not built — the data it needs is in
  `data_releases`; no browser tests yet.

### Increment 11 (Milestone 5a: reviewer workflow)

- Migration `0008_review`: `review_decisions` (append-only, before/after snapshots, cause
  tag, corrected record and fields, evidence views cited, client and server times, undo
  marks, idempotency key), `evidence_views` (written only by the image endpoint), and the
  candidate review columns (`reviewed_record`, `reviewed_by`, `reviewed_at`,
  `first_reviewer`, `second_review`, `decision_count`).
- `tariff_api.services.review`: queue ordering (blocking findings, findings, channel
  disagreement, risk-tag count, coverage impact, confidence) with a reason per item;
  checklist (inventory headings without candidates are visible `not_started` gaps; any open
  or unresolved candidate keeps an item off green); evidence rendering with the cited
  primary-reader table outlined when its bbox is known; `decide` with every refusal typed
  (`validation_failed` with `extra.evidence_required`, `conflict_stale_version` with the
  current version and status, `invalid_transition` for decided candidates,
  `permission_denied` for undo by someone else); second-review reasons; batch eligibility;
  undo; telemetry.
- Endpoints under `tariff_api.routers.review`; `CandidateOut` carries the review state;
  `/review/queue` counts `awaiting_second_review` as pending.  Validators now run over the
  effective (corrected) record; review state survives the re-run.
- Web: `/sources/{id}/review` (checklist, filters, queue) with `review-workspace.tsx`
  (evidence image fetched through a same-origin proxy that passes the view id header; the
  approve/correct controls stay disabled until the image has loaded; structured correction
  form with cause tag; rationale; keyboard n/p/a/c/r/u/Enter/z; undo; stale-version message
  says to reload and that nothing was overwritten); proxies for decision, evidence image and
  undo; links from the review queue and the source page.
- Tests: `tests/unit/test_review_policy.py` (second-review policy, checklist status
  derivation, batch eligibility) and `tests/integration/test_review_workflow.py` (the
  approve-without-evidence, other reviewer's view, stale version, first/second reviewer,
  re-decide, audit, idempotent replay/conflict, correction refusals and success with
  re-validation, reject/unresolved, undo permissions and history, checklist and queue
  updates, telemetry; batch approval refusals and one-by-one results).
- Settings: `second_review_material`, `second_review_first_order` (both default on),
  `evidence_view_max_age_seconds`, `evidence_render_dpi`.
- Honest limits: the evidence image outlines the table, not the cell (readers store no
  cell bboxes yet); both reader grids are not yet toggled in the workspace (the tables
  endpoint exists; the toggle is UI work for 5b); no browser tests yet (Section 7.5 starts
  when publish exists).

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
- `gcp`: exercised on 2026-09-14 from the operator's VM: images built and pushed to Artifact
  Registry, Cloud Run services/jobs deployed, migrations applied to Cloud SQL, readiness
  green, the NPCL order ingested from the bucket by the admin job.  The identity adapter is
  `iap` in its UNCONFIGURED state (no domain, no load balancer): the API refuses every
  authenticated request by design until a domain exists; all administrative work runs
  through the `tariff-admin` job.  Nothing was built or run against Google Cloud from this
  build environment.

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
  `/jobs/{id}`, `/jobs/{id}/cancel`, `/registry`, `/utilities`, `/users`, `/audit`;
  Milestone 3–5: localisation, structure, candidates, findings, runs, conditions, review
  queue/checklist/evidence/decisions/batch/undo/telemetry, publish preview/publish/releases,
  explorer releases/tariff/network/facts/evidence image.  OpenAPI at `/docs`.
- Review workspace (`/sources/{id}/review`), publication (`/sources/{id}/publish`), explorer
  (`/explorer`, `/explorer/{id}`, `/explorer/{id}/network`) — Milestone 5.

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

- **NPCL registered on 2026-09-14** through the admin job (`ingest inbox/NPCL_…pdf`):
  `size_bytes` 6,314,646 matches the manifest; the SHA-256 and page count are in the
  operator's job output and the inventory run (not yet pasted into this session, so not
  asserted here).  KERC and GERC not yet registered.
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

- **244 passed, 0 failed, 0 skipped** (~80 s): 196 unit (13 adapters/profile/fixtures, 32
  triage rules, 31 readers/headings/OCR, 11 profiles/localisation, 60 normalisation, 10
  clause outline, 7 grid integrity, 21 extraction/comparison/routing/validators, 8
  network extraction/derivations/conditions/VAL-05/07/12/16, 3 review policy), 48
  integration (8 sources, 6 ingest/CLI, 6 queue, 1 worker-kill recovery, 5 triage stage, 4
  parse stage, 4 localisation stage, 2 structure stage, 3 extraction/validation incl. the
  perturbed image channel and the adversarial fixture, 3 network/dual-representation/
  amendment stage runs, 2 review workflow, 2 publication/explorer, 2 migrations incl.
  0008–0009 downgrade/upgrade).  Without tesseract the OCR unit tests and the stage tests
  from parse onward skip and say so.
- Increment 11 baseline was 242 passed (196 unit, 46 integration); increment 10 was 237
  (193 unit, 44 integration).
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

**First real provider call: 2026-09-17, `tariff-api provider-smoke` on dev** — provider
`anthropic`, model `claude-sonnet-5`, 4,534 input and 407 output tokens, 0.0197 USD, one
candidate returned exactly as printed (LMV-1 energy, Rs 3.00/kWh, slab "Up to 100 kWh /
month").  Three failures preceded it, each with its cause and fix recorded: the image lacked
the HTTP client (now a declared dependency), Haystack's telemetry wrote to a home directory
the job user does not have (telemetry off before import, user given a home), and the model
returned the tool input first with the candidates list stringified and then nested one
level deeper (`unstringify` and `normalise_tool_output` before validation).  A stored key
that had been pasted into a chat was found invalid and replaced; the runbook reads the key
from a terminal prompt only.  The NPCL extraction was then re-queued on the real provider
and the worker drained six runs without failure; its results are unread at the time of
writing.  Everything below this paragraph describes the state before that call.

**Zero real provider calls before 2026-09-17.**  Every extraction run so far used the `fixture` provider
(labelled on every run and every candidate; cost 0).  The Anthropic Messages API path exists
in `tariff_api.providers` but has never been executed: no key in this environment.  OCR
(tesseract, local) is the only non-fixture tool that has run.  The first real call should be
`tariff-api provider-smoke` (a two-cell synthetic input, cost printed) once
`ANTHROPIC_API_KEY` is in Secret Manager; that too has not happened.

## Reviewer decisions obtained versus pending

None obtained on real material.  The review workflow exists and is exercised only by the
test harness's reviewer and administrator users on synthetic fixture candidates (approve,
correct, reject, unresolved, second review, undo).  No real-source candidate exists and no
real decision has been taken by anyone.

## Review/publication status and completeness declarations

Nothing real reviewed, nothing real published, no coverage declared for any utility.
Publication exists and is exercised only on synthetic fixture orders inside the test suite
(partial subset releases labelled FIXTURE); the explorer lists zero real releases.

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

000. **Operator, on the `tariff-order` VM (increment 20):** `git pull && make deploy-dev`
   (migration 0013), then in `infra/gcp/envs/dev.tfvars` replace the per-person
   `iap_members` with a Google Group you own (e.g. `"group:tariff-reviewers@aayuda.energy"`)
   and `make tf-plan tf-apply ENV=dev`; from then on a new person is: add to the group,
   add on `/admin/users`.  Register the existing three orders under their utilities so the
   commission folders fill: `make admin-dev ARGS=sources` for the ids, then for each the
   assignment is one `PUT /sources/{id}/assignment` from the page or the CLI; new uploads
   choose the utility on the form.  Share an order with engineering: download the zip from
   the source page, unzip into `exchange/<COMMISSION>/`, commit, push.
00. **Operator, on the `tariff-order` VM (increment 19):** `git pull && make deploy-dev`
   (runs migration 0012), re-extract NPCL (`make admin-dev ARGS=rerun,5f900540-a863-4f43-a570-7640114a190e,extract_source,--actor,bootstrap && make drain-dev`),
   then add the reviewers: each email into `iap_members` in `infra/gcp/envs/dev.tfvars`
   and `make tf-plan tf-apply ENV=dev`, then `make admin-dev ARGS=users,add,--email,<email>,--role,reviewer,--actor,<you>`,
   then `make admin-dev ARGS=assign-reviewer,<source_id>,--email,<email>,--actor,<you>`
   (or the reviewer clicks "Take it" on the source page).
0. **Operator, on the `tariff-order` VM (increment 18):** `git pull && make deploy-dev`, then
   `make admin-dev ARGS=rerun,5f900540-a863-4f43-a570-7640114a190e,extract_source,--actor,bootstrap && make drain-dev`,
   then open the source and click "Open the tariff table": HV-1 should show two blocks of
   two rows with fixed and energy charges, most values "2 readings agree"; approve, reject
   or note them there.  Reject the row tagged `stale`.
1. **Operator, on the `tariff-order` VM (increment 17, done 2026-09-17/18):** `git pull && make tf-plan tf-apply
   ENV=dev` (adds `SECOND_REVIEW_FIRST_ORDER=false` to the services; expect only env changes),
   `make deploy-dev`, then re-run NPCL from parse so the page-316 split and the divider rows
   take effect: `make admin-dev ARGS=rerun,5f900540-a863-4f43-a570-7640114a190e,parse_source,--actor,bootstrap`
   and `make drain-dev` until the source is `localised`; confirm the localisation again
   (regions are re-created by the stage), then `make drain-dev` through grid, extract and
   validate.  Expect about 25 image calls for the schedule region (two pages each) plus the
   assessment and summary calls; the `extraction-runs` page shows the cost.  Read the queue
   in document order: every HV and LMV category with its (a)/(b) blocks should be present
   from the rules channel, each with the model's agreement or disagreement per value.
   Then `gcloud secrets versions destroy 2 --secret ANTHROPIC_API_KEY --project tariff-order-parsing`.
2. Engineering (next run): Milestone 6 — historical comparison (preceding-order ingestion,
   amendment relationships, effective rules and the temporal resolver, reviewed category
   mappings with evidence, the deterministic comparison service citing both releases, the
   comparison screen incl. wheeling/CSS/additional surcharge/green tariff across years),
   with the fixtures the gate names (unchanged rates, changed conditions, splits/merges,
   incompatible units, zero and missing baselines, retroactive corrections, overlapping
   schedules).  Small follow-ups first: the coverage dashboard from `data_releases`, the
   reader-grid toggle in the review workspace, the first browser tests (Section 7.5).  Before
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
