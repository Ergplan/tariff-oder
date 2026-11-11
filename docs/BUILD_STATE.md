# BUILD_STATE

Last updated: 2026-11-10 (increment 155: ARR 101, a public walkthrough with the sample utility's 64 formats, on Vercel; increments 43–154 are recorded under "Current milestone and status"; increment 42: a third real order (HPERC), short-form years, Amount columns, the unit veto; increment 41: a reading preview at the chapter checkpoint; increment 40: the identity checks run over both real orders; increment 39: a second real order (BERC, combined), the mapping workbench; increment 38: the value reader measured and fixed on the real order's tables; increment 37: the first real ARR order through the reader — chapter proposal fixed against it; increment 36: case activity and the history workbook; increment 35: combined orders read per licensee; increment 34: benchmarks across licensees; increment 33: discovery profiles for five commissions, each run live; increment 32: UPERC's year-by-year listing; increment 31: true-up and APR cases, ADR-0020). Branch `claude/keen-tesla-r9mvv5`.
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
  **Increment 21 (2026-09-18): every commission in the registry; commission-first screens.**
  The seed now holds all 27 state commissions and the two joint commissions (Goa and
  Union Territories; Manipur and Mizoram; Jammu & Kashmir and Ladakh as a joint
  commission) with 70 distribution licensees under them, as identities only, names as
  commonly used in 2026 and correctable on the Registry page; Telangana is TGERC with
  TSERC as an alias, Arunachal Pradesh is APSERC to keep it apart from Andhra Pradesh's
  APERC.  The Commissions page is an alphabetical list with each commission's
  distribution companies underneath, an "upload an order" link per company that lands on
  the inbox with the company preselected, the commission's reviewer, and an inline
  "add a distribution company" for administrators.  The source inbox and the review
  queue group orders by commission the same way (orders not filed under a company last).
  `make admin-dev ARGS=seed` is idempotent and adds only what is missing.
  **Increment 22 (2026-09-20): rules 4 pairing and de-duplication from the NPCL re-run.**
  The re-run under rules 3 left 253 open values with four repeating shapes, read from the
  tariff table the operator pasted (not from files yet: the exchange folder is still
  empty).  Each is now handled and unit-tested (`tests/unit/test_tod_regions_and_units.py`,
  9 tests): a time-of-day row is named by its band however the hours are printed
  ("19:00 hrs – 02:00 hrs" = "19:00-02:00"), so the table cell and the clause line under
  a season heading merge and the model's ToD reading pairs; an unlettered heading above
  a table ("Summer Months (April to September)") is a season or a note, never a block
  that keeps two readings apart, while two different seasons always stay two rows; a unit
  missing on one side ("per day" against "per connection per day") no longer splits one
  fact; the same fact read in two overlapping regions (HV-3 traction in the schedule
  region and again in the railway region) survives once in the worker, preferring the
  pair both channels agree on and a table cell over a clause line, with the other place
  noted on the survivor; the model's outer block "(A)" pairs with the rules' inner
  sub-block "(ii)" when exactly one row on each side names that row (LMV-5), and never
  when it is ambiguous; the row-part containment test now works in both directions (it
  silently depended on set size before).  The image prompt is version 4: the rate block
  is the innermost heading printed closest above the table, and a season goes in
  `season`.  On the tariff table, condition paragraphs and "not stated" readings leave
  the rate grids for a folded "Conditions and notes (n)" section under each category,
  every block is a collapsible section, and a block's heading comes from the table's
  own reading when a clause reading arrived first (the HV-1 "(b) Private institutions"
  applicability sentence no longer names the "(b) Public Institutions" rate table).
  Not deployed; the NPCL run has not been repeated under rules 4; the numbers above
  are from the operator's paste, and LMV-3/LMV-5 page dumps still wait on the export
  into `exchange/UPERC/`.
  **Increment 23 (2026-09-21): Milestone 12 specified; ARR taxonomy and mappings as data.**
  `docs/arr-spec.md` (fact identity versioned by order and voice, the taxonomy branches,
  the commission mapping, twelve identities, registry and source changes, the chapter
  pipeline, the chapter-first review screen, the power-purchase-mix what-if with fixed
  cost retained) and ADR-0017.  `packages/arr-taxonomy/taxonomy.json` holds 123 line
  items with generic aliases, six value types, seven reason categories and identities
  ARR-I1 to ARR-I12; `mappings/{uperc,kerc,gerc}-arr.v1.json` are skeletons naming the
  licensees, the orders expected with the years and voices each decides, chapter cues
  and voice words, with empty alias, clause and unplaced lists.  Four unit tests keep the
  files coherent.  Nothing reads them yet; no pipeline, schema or UI code was written,
  by decision.  Everything in the taxonomy is a domain expectation, not verified against
  any order.  Gate to the next increment: the hand-mapping of one exported order per
  commission with its unplaced list reviewed.
  **Increment 24 (2026-09-25): orders typed, transmission licensees, the ARR loader and
  the hand-mapping scanner.**  Migration 0014: `source_documents.order_type` and
  `decides` (the years and voices an order determines), set on the upload form, on
  `tariff-api ingest --order-type/--decides`, or by an administrator on the source page
  (`PUT /sources/{id}/classification`, audited); `utilities.licensee_kind` with UPPTCL,
  KPTCL and GETCO seeded as transmission licensees and the kind shown on the Commissions
  page and chosen when adding a licensee.  Export version 2 adds `page_texts.json` (every
  page's text layer) so ARR hand-mapping and page diagnosis work from files.
  `tariff_api.arr.taxonomy` loads the taxonomy and mappings through pydantic models
  (`schema.json` is now generated); `tariff_api.arr.scan` and `tariff-api arr-scan` place
  every table-like line of an order's text on the taxonomy by exact alias, longest
  contained alias, licensee kind and the table's unit (a "Solar" row is energy under an
  MU header and cost under a crore header), list the ambiguous and unplaced lines with
  pages, and collect the fiscal years and voice words seen in headers.  Taxonomy v1
  gained `C.TX` (transmission charges total, parent of inter/intra/SLDC/other) and lost
  the bare "others" alias.  Twelve unit tests and two integration tests added; the
  Python image copies `packages/arr-taxonomy`.  Not run on any real order: the scanner has
  seen only synthetic text; the first real report needs the NPCL export in `exchange/`.
  **Increment 25 (2026-09-25): the taxonomy in the app; the tariff table walks open
  values.**  `GET /arr/taxonomy` and `GET /arr/mappings/{commission}` serve the data files
  read-only (analyst and above) and `/arr` shows every line item nested by parent with
  unit, kind, branch and generic aliases, the voices, the reason categories and the
  identities, so the reviewer sees the taxonomy where the hand-mapping will land.  The
  tariff table gains "Next open value" / "Previous" (keys n and p): the next undecided
  value scrolls into view, is outlined, and its page is shown; opening a block shows the
  page its first value is printed on.  Reading-reliability ledger rows S22 to S29 record
  the rules 3 and 4 failure modes and their tests.  323 passed; web typecheck and build
  green.  Nothing deployed; no real order has been through rules 4 or the scanner.
  **Increment 26 (2026-09-28): a reviewer reverses a decision from the tariff table.**
  A decided value shows "Undo my decision" to the reviewer who took it: the latest live
  decision is fetched and undone through the existing endpoint, the value returns to
  pending, the decision stays in the history as undone; refused by the API after
  publication or for another reviewer's decision.  Until now undo existed only in the
  one-at-a-time workspace and only within the session that decided.  Web typecheck and
  build green; no API change.
  **Increment 27 (2026-11-01): ARR Increment A — read, formulate, file (architecture,
  fixtures only).**  Operator decisions of 2026-10-31 (`docs/prompts/arr-build-prompt.md`):
  the output is a draft petition a person edits and files; architecture ahead of the
  hand-mapping gate; UPERC / NPCL first.  ADR-0018.  Migration 0015: `candidates.payload_kind`
  (tariff | arr; every tariff stage, queue, checklist and publication now filters on
  `tariff`), `source_documents.arr_state` / `arr_summary` (the ARR track beside the tariff
  state machine), `arr_chapters`, `arr_facts` (identity unique among current rows,
  superseded never overwritten), `arr_assumption_sets` / `arr_assumptions` (user with a
  rationale, or regulation clause with a citation), `arr_formulations` /
  `arr_projection_lines`, `filing_drafts` (a check constraint allows only `draft`); order
  type `arr_petition`.  Modules `tariff_api.arr.{schema,chapters,extract,provider,identities,
  formulate,filing,service}`; worker stages `arr_localise_source` (chapters from the
  mapping's heading cues + the hand-mapping scan), `arr_extract_source` (rules over the
  primary grids + the model channel over page images, fixture-only in A; compared field by
  field), `arr_validate_source` (ARR-I1, I2, I3, I4, I7, I8, I12; I5, I6, I9–I11 not evaluated
  yet).  Review reuses the tariff machinery (evidence views, second review, undo) through
  `review.parse_record`; **a real ARR candidate cannot be approved or corrected while its
  commission's mapping is not confirmed** (`arr_mapping_unconfirmed`, 409).  Formulation:
  a versioned formula library (`lib-1`), per-commission plans as data
  (`packages/arr-taxonomy/formulation/`), base-selection rule in the plan, missing
  parameters block their line and its dependants, frozen versions reproduce bit for bit.
  Filing: templates as data (`packages/filing-templates/`), numbers only through
  placeholders with a trace annex, literal digits and untraced numbers refuse generation,
  DOCX + XLSX watermarked "not filed".  Web: `/arr/<licensee>` (facts), its formulations
  (projections, blocked first, the "why" of every line) and drafts (trace annex, downloads);
  `/arr` lists licensees.  Data: `syntherc-arr.v1.json`, `syntherc-plan.v1.json`,
  `syntherc/petition.v1.json` (SYNTHETIC commission for tests); `uperc-plan.v1.json` and
  `uperc/petition.v1.json` are **skeletons** with no parameter values.  Found on the way and
  fixed: the mapping's voice word `RE\b` matched the end of "Crore" in a caption (voice words
  now match from a word start); the Python images did not copy `packages/filing-templates`
  (both Dockerfiles fixed).  Gate (synthetic, end to end, also run in the live sandbox
  stack): 5-page SYNTHETIC order → 3 chapters → 45 candidates, both channels agreeing →
  one blocking ARR-I1 on the petition's total (the deliberate break) → harness reviewers
  approve 44 with second review and reject the bad total → 44 facts published → history
  with disallowances → assumption set (one parameter grounded on the SYNTHETIC
  regulation's clause; a wrong excerpt and a value not in the excerpt refused) →
  formulation with 5 blocked lines → complete formulation (ARR 6,889.88 crore, gap 193.88,
  ACoS 7.41) frozen and reproduced identically → draft with 58 traced numbers (32 fact,
  2 assumption, 24 projection); an untraced number in a template refused.  **No real order
  has been read for ARR; no real ARR fact, assumption, formulation or draft exists.**
  **Increment 28 (2026-11-01): the client application (ADR-0019).**  Operator request: a
  client application holding every state's orders and MYT petitions/orders of the last three
  years, where a client starts the ARR process.  Migration 0016: `organisations`,
  `organisation_members` (owner/editor/viewer), `organisation_id` on assumption sets and
  formulations (set names unique per owner), `arr_cases`, `library_entries`; order type
  `myt_petition`.  `tariff_api.workspace` decides access: desk objects as before; an
  organisation's objects for its members only — another organisation gets 404, a platform
  administrator may read but not change.  ARR cases (`/cases`): annual ARR or MYT control
  period; readiness lists the base facts present/missing (reviewed facts only) and the
  parameters to supply per year; assumptions, formulate, freeze, draft, revise drive the
  Increment A engine.  Library (`/library`): `seed` creates expected slots per real
  licensee × year × kind (tariff order, ARR petition) plus control-period MYT order and
  petition and the commission's regulations — expectations, never data; `PUT /library/entries`
  records an official URL; the worker job `acquire_library_entry` fetches it (PDF only,
  size-capped) and registers it exactly as an upload; failures are recorded on the entry;
  `reconcile` links registered orders; coverage by state → commission → licensee with
  reading levels missing / located / failed / acquired / read / reviewed / published.  Web:
  `/client` (workspace), `/client/library` (coverage), `/client/licensees/<code>`,
  `/client/cases/new`, `/client/cases/<id>` (step-by-step: readiness, assumptions,
  formulation with blocked lines, freeze, draft), desk `/library` (seed, record URL, acquire)
  and `/admin/organisations`; navigation follows the caller's role and memberships.
  Live sandbox stack: the library seeded for FY2024-25…FY2026-27 holds **605 expected slots
  for 72 licensees in 29 states/UTs, all `missing`** — nothing acquired yet.  Acquisition was
  tried against UPERC from the cloud session: the site answers, but its tariff-order list is
  a search form driven by ASP.NET postbacks (`Tariff_Order_Users.aspx`); KERC, GERC, MERC,
  TNERC and DERC do not answer from the cloud session at all.  Found and fixed: a draft
  download with an em dash in its name crashed the response header (RFC 5987 now).
  **Increment 29 (2026-11-01): the live ARR reading channel and document discovery.**
  `AnthropicArrImageChannel` reads a confirmed chapter's page images six pages per call with
  the ARR candidate schema as its only tool; each candidate is validated on its own (a bad
  row is dropped with its reason), the order and licensee are set by code, the canonical value
  is recomputed from the printed one, cost comes from the configured prices; the stage passes
  the pages, licensee, commission, voices and taxonomy codes.  Tested with the HTTP call
  mocked; **never run against a real order or with a real key**.  Library discovery
  (`POST /library/discover`, desk `/library` → Find documents): from a commission's listing
  page, fetched or pasted (for lists behind search forms such as UPERC's), every PDF link
  with a guessed kind, year and licensee and the reasons it is incomplete; the desk ticks
  and records them (`/library/entries/bulk`), nothing is saved without a person.
  **Increment 30 (2026-11-01): every state readable; the ARR review screen.**  A commission with
  no mapping, plan or petition template of its own falls back to generic skeletons
  (`mappings/generic-arr.v1.json`, `formulation/generic-plan.v1.json`,
  `filing-templates/generic/`): any state's licensee can be read, formulated and drafted; the
  generic mapping is never confirmed, so real lines read with it cannot be approved.
  Formulations record their plan id and are reproduced and drafted with exactly that plan.
  The ARR review screen `/sources/<id>/arr` (spec section 7): read the order, confirm its
  chapters (with the scan's unplaced rows shown), a chapter rail with progress and identity
  failures, a grid of line items × year/voice per chapter, the cited page rendered beside it
  before any value can be approved (shared evidence-view gate), approve/reject per value,
  publish when no blocking identity is open.  Found in the live stack and fixed: a page
  shared by two chapters put the next chapter's table in the previous one; tables are now
  assigned to the last chapter heading above them on the page, and every ARR candidate
  records its chapter.  The review screen also approves, in one step, the values of one page
  that both readings agree on and no identity check or risk tag flags (each still gets its
  own decision citing the reviewer's view of the page).

  **Increment 31 (2026-11-01): true-up and APR cases (ADR-0020, migration 0017).**  A client
  starts a true-up of a past year or an APR of the running year from the case wizard.  The
  approved figure of each line is the current reviewed fact of voice `approved` for the year;
  the client enters each actual with its source — a reviewed fact of voice `actual`, a page
  of a registered document (excerpt found on the page, value printed in it: mechanical), a
  statement naming a document the application cannot see (labelled unchecked everywhere),
  or, for an APR only, an estimate.  The statement sets approved against actual with the
  variance (actual less approved; never an allowed amount), runs the ARR identities over the
  actuals (a total that does not add up blocks the freeze), and hashes its inputs; freeze and
  draft re-check the hash.  The draft (DOCX + XLSX, built-in layout) names every unchecked
  figure, leaves the reasons for each variance to the licensee, and traces every number
  (approved → order and page; actual → its source; variance → the two trace ids).  Exercised
  in the live stack through the browser on SYNTH-DISCOM FY2025-26 (15 lines: one actual
  entered through the form, statement computed, frozen, drafted; 45 numbers traced).
  Synthetic data only; no real true-up has been prepared.

  **Increment 32 (2026-11-01): commission discovery profiles.**  How the library finds each
  order's official URL is now data per commission (`packages/discovery-profiles/`), followed by
  an engine (`tariff_api/discovery.py`) for plain listing pages and ASP.NET WebForms pages with
  a financial-year drop-down (view state carried as a browser would; disabled inputs and empty
  drop-downs not posted, which UPERC's event validation otherwise refuses; one request at a
  time with a pause).  `uperc.v1.json` (status draft) pages through UPERC's tariff-order list:
  "Previous Years" postback, select the year, "Show".  **Run live from this session on
  2026-11-01** (`tariff-api library-discover --commission UPERC --years FY2024-25 FY2025-26
  FY2026-27 --registry`): 8 requests, 34 + 16 + 19 documents listed, 69 proposals covering a
  tariff-order proposal for each of the seven UP licensees (NPCL, UPPTCL, PVVNL, PUVVNL,
  MVVNL, DVVNL, KESCO) in each of the three years (21 slots); 7 complete, the rest flagged:
  scanned twins of a listed text or digitally signed copy, corrigenda (recorded with the order
  they correct), two documents competing for one slot (the person chooses), titles naming no
  registry licensee (NIDP, UPSLDC), one APTEL appeal order.  Nothing was recorded or fetched:
  proposals wait for a person.  The run found and fixed real defects in the generic
  proposer: UPERC's links are unquoted (`href=App_File/….pdf`, previously missed), the
  description sits in the table row (the link shows the file name), and "Tariff Order … in
  Petition no 2039/2023" was guessed a petition.  Proposals now also carry the years and
  voices the title says the order decides (true-up FY X, APR FY Y, ARR FY Z), the copy variant
  and preference, and the listing; an order for "State Discoms" is proposed for each of the
  five discoms.  An entry whose URL another entry has already acquired is linked to that
  source without fetching again.  API `GET /library/discovery-profiles`,
  `POST /library/discover/profile` (administrator); the library admin form switches to the
  profile when the commission has one.  **Not done:** the sandbox containers have no
  outbound network, so the same run through the API here reports `request failed:
  ConnectError` per page (on the VM it reaches the site); profiles for other commissions;
  UPERC's petitions and regulations pages; a combined order is registered once with the
  first licensee as its source licensee (reading the other discoms' ARR from it needs a
  source with several licensees — open).

  **Increment 33 (2026-11-01): discovery profiles for BERC, HPERC, JSERC and JERC (Goa & UTs).**
  Of 24 commission sites tried from this session, 8 answer (MPERC, BERC, OERC, JSERC, HPERC,
  UERC, JERC, CERC); the others time out here (they may answer from the VM).  Profiles were
  written for four of the reachable ones and run live; the engine gained what their sites
  need: following a page per order to its PDF, including a PDF embedded through a viewer link
  (BERC), pagination, `rows_only` (only PDFs in the orders table, not the site menu: HPERC),
  a listing's own licensee for titles that name none (HPERC → HPSEBL, JERC's Goa page →
  GOA-ED), and profile-level licensee aliases the registry lacks (EDG, PED, the full JBVNL
  name).  The proposer now drops documents whose every named year is before the years asked,
  sets aside press releases, tariff charts, notices and review orders, reads "Approval of …"
  and "Determination of …" as orders and "truing up" as a true-up, proposes an order naming
  several licensees once per licensee, and tells an annual order that mentions its control
  period ("ARR and Tariff for FY 2026-27 & final true-up of the 4th MYT control period") from
  the MYT order.  **Live run, FY2024-25 to FY2026-27, nothing recorded:** UPERC 69 proposals
  (15 complete) in 8 requests; BERC 31 (2 complete: the FY2026-27 order for NBPDCL and SBPDCL)
  in 30 requests; HPERC 29 (2: HPSEBL FY2024-25 and FY2026-27) in 1; JSERC 56 (3: JBVNL
  FY2024-25 and FY2025-26, a regulation) in 1; JERC Goa & UTs 23 (4: GOA-ED and PED-PY
  FY2026-27 tariff and FY2024-25 true-up) in 2.  The rest carry the note that stops them
  (competing copies, MYT orders for the 2026-31 control period with several documents, titles
  in short-year forms like "FY 26" which are not read as years).  All profiles are `draft`.

  **Increment 34 (2026-11-01): benchmarks across licensees.**  `GET /arr/benchmarks` and
  `/client/benchmarks` (linked from each licensee's page): for one year and voice, six ratios a
  petition is argued with — power purchase cost per unit of input, O&M and ARR per unit sold
  (Rs/kWh), distribution loss, the revenue gap as a share of the ARR, return on equity as a
  share of expenditure — derived in Decimal from the current reviewed, published facts, never
  stored; each value lists its facts (order, page) and its formula words, the peers' median,
  minimum and maximum, and the rank (1 = lowest).  A licensee missing an input, or an input in
  an unexpected unit, has no value and a reason.  Fixture licensees only when asked for, and
  labelled.  No real licensee has published ARR facts yet, so the page shows fixtures only.

  **Increment 35 (2026-11-01): combined orders (migration 0018, ADR-0018 amendment).**  One
  order often decides several licensees' ARR (UPERC's State Discoms order, BERC's NBPDCL and
  SBPDCL order).  An order's licensees are its primary licensee plus `source_licensees`, set by
  an administrator (`PUT /sources/{id}/licensees`, the "Licensees in this order" box on the ARR
  screen) or by the library when the same document is acquired for another licensee.  The
  structure channel attributes each value to the licensee its column header names (year and
  voice from the caption) or its table's caption names; a total column, or a column with no
  licensee readable, is skipped and reported.  The licensee is part of a candidate's identity
  and correctable; identities run per licensee; publication files each fact under its own
  licensee and refuses a value whose licensee is not the order's; the live model channel is
  told the licensees.  The ARR review grid has a column per licensee, year and voice.  Tested
  end to end on a synthetic two-licensee order and run in the live stack (20 values, no
  identity failure).  **Not yet seen on a real combined order:** the UPERC and BERC orders lay
  out per-discom figures in ways this has not been checked against (a separate table per
  discom, annexures per discom, discoms as rows) — the first real read will tell.

  **Increment 36 (2026-11-01): case activity and the history workbook.**  `GET
  /cases/{id}/activity`: who did what in a case, newest first (the case's own audit events and
  those of the assumptions in its set chain), private to the organisation; shown as an
  "Activity" panel on both case screens.  `GET /arr/utilities/{code}/history.xlsx`: a
  licensee's reviewed, published ARR facts as a workbook, one row per fact with its order, page,
  excerpt and fact id, plus a "Disallowance (derived)" sheet that says it is derived; linked
  from the history page as "Download as Excel".

  **Increment 37 (2026-11-01): the first real ARR order through the reader.**  UPERC's NPCL
  tariff order for FY2026-27 (true-up FY2024-25, APR FY2025-26, ARR FY2026-27; issued 02/07/26)
  was downloaded from `https://www.uperc.org/App_File/NPCL_TariffOrder-pdf72202631759PM.pdf`
  (SHA-256 `ff36813e…a1b`, 423 pages, 6.3 MB) and registered in the local stack as a real source
  for NPCL.  Triage, OCR (17 near-textless pages), parse and localisation ran in about 12 minutes.
  **`POST /sources/{id}/arr/read` proposed 229 chapters** — the chapter proposer, written against
  synthetic orders, took the running header printed on every page of a part ("AGGREGATE REVENUE
  REQUIREMENT OF FY 2026-27"), contents entries, table captions ("TABLE 4-99 …"), table rows
  ("1 Sales (MU) 3.53 …"), numbered paragraphs ("4.4.12. Accordingly, …") and dates
  ("17.06.2026 GFA") for headings.  Chapter rules v2: running headers and footers (a line in the
  first or last three lines of five or more pages) are page furniture and name the part a
  chapter sits in; contents pages and lines with dotted leaders, captions, table rows (two or
  more numbers, or cells set apart by wide gaps), numbered prose and dates are not headings; when
  an order numbers its sections, only the heaviest never-decreasing run of section numbers
  opens and closes chapters (a list item "5.1" inside section 4.16 is not a section), and a
  top-level part heading without a cue ("4. TRUE UP OF FY 2024-25") ends the chapter before it.
  **Re-proposed through the real pipeline: 30 chapters**, matching the order's own sections —
  4.3–4.19 of the true-up (pp. 52–168), 5.3–5.18 of the APR (pp. 171–209), 6.3–6.18 of the ARR
  for FY2026-27 (pp. 214–295), 8 Revenue Gap (pp. 306–310) — each with its part in the note;
  plus 3.4 and 3.6 of the public-hearing chapter (stakeholders' submissions, to be excluded by
  the reviewer) and 9.1 open-access charges (capped, to be ended by the reviewer).  **Stopped
  there:** confirming the chapters of a real order is a reviewer's decision, and the UPERC
  mapping is still a skeleton (`mapping_confirmed: false`), so real lines could not be
  approved anyway.  The scan of the same order placed 617 table rows on the taxonomy and left
  1,939 unplaced (top unplaced keys: the running headers, "Total", tariff-category rows such as
  "LMV-1: Domestic Light, Fan & Power", "Grand Total") — the hand-mapping list for the
  reviewer.  The order is in the local stack only; nothing was deployed.

  **Increment 38 (2026-11-01): the value reader measured on the real order's tables.**  A
  read-only evaluation (the structure channel's rules over the 384 primary grids of the 30
  proposed chapters, nothing recorded, no chapter confirmed) found the reader read **30 of 384
  tables and 53 values**: real ARR tables put the year in the caption and only the voice in
  the header ("TABLE 6-81 SUMMARY OF ARR AS APPROVED BY THE COMMISSION FOR FY 2026-27" over
  "Claimed | Approved"), print an earlier order's approval beside the claim and the decision
  ("Approved in TO dated 10.10.2024 | Claimed | Approved"), put reference, formula and unit
  columns beside the label ("A", "C=A+B", "Rs. Cr."), split headers over two rows ("FY 2024-25
  (True-Up)" over "Claimed | Approved"), and mark values with footnotes ("517.23*").  Rules
  arr-rules-2: the year from the caption (or the part's running header) when the header names
  only a voice; the voice of an approval from the nearest words — the header, then the part,
  then the caption — so an approval inside the true-up is the trued-up value, inside the APR
  the provisional one, and "Approved as per TO dtd …" stays the earlier approval; the label
  column chosen by its header or its text, never a reference, formula or S. No. column; a
  units column gives the row's unit; a second header row is recognised; footnote marks and a
  trailing per cent sign are not part of a value; a label's unit only from brackets or its end
  ("@ 40% of R&M" is not a unit).  **Measured again: 188 of 384 tables read, 657 values, 714
  rows placed.**  Spot-checked against the page text: the FY2026-27 ARR summary (p. 294) reads
  claimed/approved power purchase 2,448.33/2,477.36, ARR 3,387.16/3,420.27, revenue gap
  289.79/319.29 Rs crore, sales 4,399.84 MU; the APR summary (p. 207) reads the earlier
  approval, the APR claim and the provisionally considered value in their own voices.  The
  other 196 tables are mostly schedules that are not line × voice (asset classes × GFA, months
  × units, plants × availability) and stay unread; 965 rows stay unplaced, now genuine line
  labels for the UPERC mapping ("Inter-State Losses", "Units at UP Periphery", "Contracted
  Quantum").  These are proposals of a real order measured outside the pipeline: none is a
  candidate or a fact, and none can be approved until a reviewer confirms the chapters and the
  UPERC mapping.

  **Increment 39 (2026-11-01): a second real order, and the mapping workbench.**  BERC's combined
  tariff order for NBPDCL and SBPDCL, FY2026-27 (true-up FY2024-25, APR FY2025-26, ARR FY2026-27;
  case nos. 50/2025 & 51/2025; `https://berc.co.in/images/pdf/tariff-order/2026-27/DISCOMs_FO_
  TARIFF_CN_50_51_DT_180326.pdf`, SHA-256 `a247053b…4794`, 612 pages), found through the BERC
  discovery profile, was registered locally as a real source for NBPDCL with SBPDCL as its second
  licensee (no BERC mapping exists, so the generic skeleton reads it).  Parsed and localised in
  9 minutes.  **Chapters, first try with the v2 rules: 36**, matching sections 4.2–4.25 (true-up),
  5.2–5.22 (APR) and 6.3–6.28 (ARR), each now noting its top-level section ("in section: 4.
  Truing-up for FY 2024-25").  The read-only evaluation found two defects of the reader on it,
  both fixed: the prose above a table was taken as its caption (a per-licensee column took its
  voice from "The Commission, accordingly, considers …"; a table whose title names two years
  took the part's year) — a table's year and voice now come only from its own title (its last
  "Table …" line and continuation, else the line right above it), a title naming several years
  is ambiguous and never filled from the part, and a running header that names no part ("NBPDCL &
  SBPDCL Tariff Order for FY 2026-27") is no context.  **Measured (read-only, nothing
  recorded):** NPCL 183 of 384 tables, 650 values; BERC 177 of 548 tables, 573 values, each
  attributed to NBPDCL or SBPDCL by its column ("Approved for NBPDCL for FY 2026-27").  The
  title rule costs about a quarter of BERC's previous count; the dropped ones were the
  unreliable ones.  Placement errors of the generic mapping remain (a working-capital row "Less:
  (i) Power purchase cost …" placed on C.TX) — the mapping's job.

  The **mapping workbench** (migration 0019, `/arr/mappings/<commission>`, linked from the ARR
  taxonomy page): every label a commission's read orders leave unplaced, most frequent first,
  with the orders and pages, word-overlap suggestions (never placements), and a reviewer's
  decision on each (an alias to a taxonomy line, or "not a line"), audited and withdrawable;
  `GET /arr/mappings/{c}/draft` and `tariff-api mapping-draft --commission C --out …` render the
  next mapping version with the decisions written in, status `draft … not confirmed` — a person
  commits it and a reviewer confirms it.  The ARR scan now drops page furniture too (running
  headers and "Page n of m" no longer top the unplaced list).

  **Increment 40 (2026-11-01): the identity checks over both real orders (read-only).**  The ARR
  identities, run over the measured values of each year, voice and licensee: on NPCL, three
  blocking ARR-I1 failures ("C.TOTAL is 539.30 but its components give 2,951.81") — a power
  source's "Total Cost" row placed on total expenditure by the generic alias "total cost".  Now
  the ARR's own totals (C.TOTAL, R.ARR, R.GAP, R.REV.EXISTING) are placed only in an ARR or gap
  chapter or in a table titled as the summary; elsewhere the row is reported unplaced with the
  reason.  The I1 failures are gone.  **What remains is for the reviewer, not the reader:** on
  NPCL, ARR-I3 for FY2026-27 — the printed revenue gap (approved 319.29, claimed 289.79 Rs crore)
  is not ARR less revenue at existing tariff (228.23, 195.12): UPERC's gap carries more than the
  year's ARR (the mapping's `gap_convention` is unset and decides this identity); on BERC, ARR-I4
  for four year-voice-licensee groups — energy input differs from sales grossed up by the
  distribution loss by 0.6–2.0 %, a definitional difference (which loss, which sales) the BERC
  mapping must state.  Identity messages now state a computed side to four places.

  **Increment 41 (2026-11-01): a reading preview at the chapter checkpoint.**  When chapters are
  proposed, the localisation stage now also runs the reading rules over each proposed chapter's
  tables (the same table-to-chapter assignment the extraction uses) and stores, per chapter,
  the tables read of the tables found, the values by year and voice, the blocking identity
  failures and the commonest unplaced rows — recorded nowhere but in the summary, never as
  candidates.  The ARR screen shows it beside each proposed chapter, so a reviewer sees what
  confirming a chapter would read: on the real NPCL order (re-proposed in about 10 s) the two
  public-hearing chapters would read nothing, the true-up, APR and ARR chapters 493 values, two
  identity failures (the gap convention of increment 40).  The extraction now uses the shared
  table-to-chapter helper; the synthetic end-to-end test asserts the preview predicts the
  reading exactly.

  **Increment 42 (2026-11-01): a third real order, and three more reading rules.**  HPERC's
  order for HPSEBL, FY2026-27 (`https://hperc.org/wp-content/uploads/2026/03/fto2627.pdf`,
  SHA-256 `0f3d9e9d…ec74`, 525 pages; found by the HPERC discovery profile), registered locally
  as a real source; parsed and localised in 7 minutes.  **44 chapters on first contact**, matching
  its sections (4 final true-up, 5 true-up of uncontrollables, 6 of controllables, 8 APR, 9 ARR
  FY2026-27), each noting its section.  The preview read only 85 of 410 tables: HPERC writes
  years short ("ARR approved by the Commission for FY27") and prints one "Amount" column whose
  voice is in the title ("Petitioner Submission – … for FY24").  Rules: "FY27" with its prefix is
  FY2026-27 (Indian usage; a bare two-digit number never is); a lone Amount column takes its
  year and voice from the title.  A spot check then showed "Cost of electricity purchase
  including own generation" (a Rs crore row) on an MU line: **a row whose printed unit
  contradicts the line's is now reported, never placed** (money is never energy, nor a
  percentage money).  The workbench can also draft a commission's first mapping from the
  generic skeleton (letters-only codes).  **Measured through the live preview, all three real
  orders, read-only:** NPCL (UPERC) 181 of 353 tables, 508 values, 2 identity failures; NBPDCL +
  SBPDCL (BERC) 161 of 503, 434 values, 3; HPSEBL (HPERC) 190 of 410, 618 values, 0.  The
  spot-checked HPERC ARR table (Table 244) reads petition and approval of power purchase
  (5,684.75 / 5,678.19), O&M (3,470.68 / 3,468.46) and SLDC charges as printed.

  **Increment 43 (2026-11-01): a fourth real order with another layout — paragraph-numbered
  orders.**  JSERC's MYT, true-up and APR order for JBVNL (`https://jserc.org/pdf/tariff_order/JBVNL-2026.pdf`,
  SHA-256 `0391dd27…119108`, 3,665,495 bytes, 372 pages), registered locally as a real source.
  JSERC numbers every *paragraph* ("5.13 Based on the information provided above…", up to
  5.131) and heads its sections with unnumbered Title Case lines inside "Chapter N:" parts, so
  the numbered rules proposed nothing useful.  **Chapter rules:** when an order has "Chapter N"
  parts, fewer than five numbered headings with a cue, and numbered sentences outnumbering them
  three to one, the numbers mark paragraphs: chapters follow the Title Case and capitals
  headings, each noting its "Chapter N" part, a part's own page ends the chapter before it, and
  the same line in two parts is two chapters.  A "Chapter N:" title that wraps ("TRUE-UP FOR FY"
  over "2024-25") is joined with its capitalised continuation (a page number never).  A part
  that reports the petition or the hearing ("Brief facts of the petition", "Public consultation")
  is noted as likely not the Commission's decisions.  **74 chapters**, structured by Chapter 5
  (true-up FY2024-25), 6 (APR FY2025-26), 7–8 (business plan and MYT FY2026-27 to FY2030-31), 9
  (gap); chapters 1–36 are the petition and hearing parts for the reviewer to exclude.  UPERC
  30, BERC 36 and HPERC 42 chapters are unchanged (a numbered order without "Chapter N" parts
  never enters the new mode).  **Reading rules:** running headers and footers are no longer a
  table's caption (a continued table under "…Tariff determination for FY 2026-27" took that
  year); a taxonomy line can list `not_when` phrases that refuse a match inside a longer label
  ("Total Energy Available for Sales" is not the sales, "Energy Input Directly to State
  Transmission System" and "Direct Input Energy from State Solar System" are not the input at
  the distribution periphery); "power purchase" in a crore table is the cost, in an MU table the
  quantity; a multi-word alias matches its singular or plural.  **Measured through the live
  preview, all four real orders, read-only:** NPCL (UPERC) 181 of 353 tables, 515 values, 2
  identity failures (gap convention, A8); NBPDCL + SBPDCL (BERC) 160 of 503, 434 values, 3
  (loss definition, A8); HPSEBL (HPERC) 195 of 434, 648 values, 0; **JBVNL (JSERC) 128 of 292,
  470 values, 5.**  On JSERC the energy balance now satisfies ARR-I4 for FY2024-25 and FY2025-26
  in every voice (sales 11,055.39 MU at 13 % loss gives the printed 12,707.34 MU requirement); the
  5 failures are all ARR-I1 on the two ARR summaries, and each differs by exactly the inter-state
  plus intra-state transmission charges (558.56 + 382.02 = 940.58 for the FY2024-25 APR
  column): JSERC's "Total Power Purchase Expense" includes transmission, a convention for the
  reviewer's JSERC mapping.  Before the placement rules the JSERC preview was 290 values with
  the true-up's years wrong (FY2026-27 from the running header) and 12 failures.

  **Increment 44 (2026-11-01): mapping conventions — the identity failures become reviewer
  questions.**  A commission's mapping can now state `total_includes` (a line printed
  inclusive of others: JSERC's power purchase includes transmission), and ARR-I1 counts the
  included lines once.  With nothing stated, a failing ARR-I1 is re-tried with the known
  inclusions; one that reconciles is named in the finding ("it reconciles if C.PP includes
  C.TX … a convention for the mapping reviewer") and **the finding stays blocking**.  The
  chapter preview now keeps its blocking findings (up to 8 per chapter, with the hint), shown
  under the failure count on the order's ARR page with a link to the commission's workbench.
  The workbench gains a **Conventions** section: the questions the read orders pose (an
  inclusion an ARR-I1 hint names; the gap convention where ARR-I3 fails both ways), each with
  its evidence (order, chapter, finding); a reviewer answers (`PUT
  /arr/mappings/{c}/conventions`, reviewer role; migration 0020 adds the `convention` decision
  kind) and the drafted mapping writes the answer into `gap_convention` or `total_includes`
  (a valid mapping file, status draft, not confirmed).  **Live, on the real orders' previews:**
  JSERC poses "Does JSERC print C.PP inclusive of C.TX?" with 4 pieces of evidence (FY2024-25
  APR, petition and true-up; FY2025-26 petition); its fifth failure (FY2025-26 APR column,
  −380.56) reconciles under no known convention and stays unexplained.  UPERC poses its gap
  convention (2 pieces of evidence, FY2026-27 petition and approval).  **No convention has been
  answered:** that is the reviewer's decision.  ARR-I4 (BERC's loss definition) poses no
  mapping question yet: the mapping has no field for it.

  **Increment 45 (2026-11-01): the loss basis, the last convention behind a real-order
  failure.**  BERC's energy balance (Table 4.5) grosses up the sales *within the state*: retail
  sales 16,993.71 MU less inter-state sales to Nepal 196.49 = 16,797.22, at 11.46 % loss, give
  the printed 18,971.33 MU.  A taxonomy line `E.SALES.INTERSTATE` (cross-border sales counted
  in retail sales: "inter-state sales (Nepal)", "sales to Bangladesh"); a mapping
  `loss_basis` (`retail_sales` or `sales_within_state`) that ARR-I4 honours; unstated, a
  failing ARR-I4 that the within-state basis reconciles names it (still blocking) and the
  workbench asks "Does BERC's distribution loss apply to the sales within the state only?".
  **A first attempt was wrong and was measured wrong:** the generic aliases "inter-state
  sales" also caught HPSEBL's "Inter State Sale" (2,540.44 MU of surplus power sold to other
  states, not retail sales) and refusing "excluding" on the sales dropped NPCL's "sales
  excluding inter-state sales" (its retail sales, 3 values); both were reverted, so a bare
  inter-state sale stays unplaced for each commission's mapping to decide.  **Measured, all four
  real orders:** UPERC 515 values, 2 failures (gap convention, posed); BERC 440, 3 (1 posed as the
  loss basis; 2 — FY2025-26, which deducts "Nepal + SLDC Deviation" — unexplained); HPERC 648,
  0; JSERC 470, 5 (4 posed as power purchase inclusive of transmission; 1 unexplained).  Every
  blocking failure on the four real orders is now either a convention question for a reviewer
  or recorded as unexplained; none is waved through.

  **Increment 46, part 1 (2026-11-01): short-year titles in discovery.**  A listing title's
  "FY 26" / "FY26" / "FY'26" is read as the financial year ending then (FY2025-26) before the
  proposer's rules run; a bare two-digit number is never a year.  **Live, read-only:** the
  HPERC profile now proposes HPSEBL's tariff orders for all three years FY2024-25 to FY2026-27
  (3 complete of 14 proposals; increment 33 found 2).  JSERC is unchanged at 3 complete of 56:
  its 2026 MYT/true-up order is proposed for JBVNL's control-period slot, but two documents on
  the page compete for it, so a person chooses.

  **Increment 46, part 2: discovery profiles for Madhya Pradesh, Odisha and Uttarakhand.**  The
  three sites were mapped read-only (about 60 requests in all) and profiles written
  (`mperc.v1.json`, `oerc.v1.json`, `uerc.v1.json`, status draft).  The engine gained what they
  need: **titles for icon links from the table header** (MPERC links each order through an icon
  under a two-level header, "Tariff Order" and "True Up Order" column groups, with a true-up in
  the row of the year it trues up: the title is the group's name with the row's period); a
  file name made of words also tells the kind when the link shows none (MPERC's MYT order);
  **a listing may stand for a group of licensees** (MPERC's three State DISCOMs, OERC's four TP
  DISCOMs share one order a year); URLs have dot segments resolved and spaces encoded, and the
  same file under another letter case is one document (OERC); a dropped connection is retried
  (UERC); salient features, highlights, admittance, interim and daily orders, and a "petition
  for review of the Commission's Order" are set aside with the reason; "Tariff Orders" (plural)
  is an order.  **Live, FY2024-25 to FY2026-27, nothing recorded:** MPERC 15 of 15 proposals
  complete (tariff orders of three years, the FY2024-25 true-up, the 2022-27 MYT order, each for
  the three discoms); OERC 12 of 12 (the combined order of each year for each of the four
  discoms); UERC 4 of 71 (UPCL's orders of the three years and its MYT petition; the rest are
  generators, PTCUL and SLDC, which the registry does not hold, or procedural documents set
  aside).  The five earlier profiles re-run unchanged (UPERC 15, BERC 2, HPERC 3, JSERC 3, JERC
  4 complete).  Ten commissions now have profiles; MPPTCL's orders (only in MPERC's petition
  search form) and OERC's GRIDCO and OPTCL pages are not covered.

  **Increment 47 (2026-11-01): three more states read — Odisha, Madhya Pradesh,
  Uttarakhand.**  Each FY2026-27 order was downloaded from the URL its new discovery profile
  proposed and registered locally as a real source, read-only to `chapters_proposed`:
  OERC's combined order for the four TP DISCOMs (`DISCOM_TARIFF_ORDER_FY_2026-27.pdf`, SHA-256
  `d58d2817…ffde0ab`, 246 pp.), MPERC's order for the three State DISCOMs (petition 140/2025,
  `77ffe9d2…79f91afb`, 255 pp.) and UERC's order for UPCL (`1a929917…99eb91`, 414 pp.).  Each
  had a layout the rules had not met:
  - **Lettered parts** (A16): OERC structures its order "A. PROCEDURAL HISTORY" … "I.
    OBSERVATIONS AND DIRECTIONS OF THE COMMISSION" with numbered paragraphs, MPERC "A1: ORDER"
    … "A8: PUBLIC SUGGESTIONS"; read like JSERC's "Chapter N" parts (increment 43), with the
    proposal, objection and advisory parts flagged.  OERC 5 → 36 chapters, MPERC 0 → 21.
  - **Licensee per row** (A17): OERC's tables carry a "DISCOM" column (TPCODL, then blank cells
    for its rows) or a licensee's name on a row above its block; rows are attributed to it and a
    total row to none.  OERC 340 → 488 values.  Tables whose rows *are* the licensees are not read.
  - **Three-level sections in one part** (A18): UERC numbers its true-up part "3.1.3 Power
    Purchase Expenses"; a chapter of 40+ pages is now split at such headings, each noting its
    part ("3. … Conclusion on Truing Up for FY 2024-25").  Accepting three levels everywhere
    was tried first and removed NPCL's true-up and APR chapters (its list items), so it is
    limited to long chapters.  UERC 13 → 19 chapters.  Cues now also name their plurals
    ("Distribution Losses"), and "sales" is a generic energy cue: BERC 36 → 40 chapters (its
    interest on loans now apart from depreciation in each part), HPERC 42 → 45, JSERC 74 → 79.
  - **Wrong values caught in MPERC's preview** (A19): East DISCOM's *claimed* ARR was read as
    *approved* (the licensee's column took the caption's voice, ignoring "Claimed" on the
    second header row), and "Power Purchase Cost including Inter-State Transmission" was placed
    on inter-state transmission.  A group heading is now carried over its sub-columns, a
    licensee's column takes its own voice word first, and a label names what precedes
    "including / net of / excluding".  The carry also reads BERC's licensee-over-voice headers:
    BERC 442 → 559 values, its failures unchanged.
  - **Registry** (A20): MPERC's West DISCOM is "MPPaKVVCL"; codes were matched upper-cased and
    never found.  Codes now match whatever their case; the three MP discoms carry the order's
    own short names ("East DISCOM" …) as aliases, and re-seeding adds new aliases to existing
    licensees.  "admitted" is an approval voice.
  **Measured through the live preview, seven real orders, read-only:** UPERC 517 values (181 of
  353 tables), 2 failures; BERC 559 (203/503), 3; HPERC 657 (204/469), 0; JSERC 467 (128/294),
  5; **OERC 488 (44/166), 0; MPERC 249 (31/140), 6; UERC 164 (77/149), 0.**  MPERC's 6 are
  ARR-I1 on its summary, one per discom and voice: the interest sub-rows printed under
  "Interest & Finance Charges" ("On Project Loans", "On Working Capital Loans", "On Consumer
  Security Deposit") and "R&D Fund" are not placed (507.04 of East's 507.06 claimed gap) — the
  MPERC mapping's work, not a convention.  Seven states now have a real order read.

  **Increment 48 (2026-11-01): sub-rows read with their heading row.**  A row with a label and
  no values ("Interest & Finance Charges") is a heading, not a candidate; a following row whose
  label opens with a preposition ("On Consumer Security Deposit") is read with the heading's
  leading words ("Interest on Consumer Security Deposit").  MPERC's 6 ARR-I1 failures are gone.
  Dropping value-less rows as candidates lowered every order's count slightly (they were
  blank candidates) and **uncovered a misplacement**: UERC's blank "Revenue" heading row had
  stood on revenue at existing tariff and hidden the printed revenue, so ARR-I3 was never
  evaluated; once evaluable it showed "Gap/(Surplus) of previous year" (897.38, carried into this
  year's ARR) placed on this year's gap.  R.GAP now refuses previous-year and brought/carried-
  forward labels; UERC's gap is read from "Adjusted Revenue (Surplus)/Gap" (307.12 approved).
  Its 2 remaining ARR-I3 failures are UERC's gap convention, fully explained: its gap is net ARR
  (ARR − NTI + the previous year's gap) less total revenue with additional sales (10,626.83 −
  10,319.71 = 307.12); the identity's ARR less revenue at existing tariff misses −479.20 +
  897.38 − 241.23 = 176.95 exactly.  The workbench poses it as UERC's gap-convention question.
  **Measured, seven real orders:** UPERC 503 values, 2 failures; BERC 543, 3; HPERC 643, 0;
  JSERC 457, 5; OERC 479, 0; **MPERC 264, 0**; UERC 163, 2 (convention).

  **Increment 49 (2026-11-01): the ARR readings board.**  `GET /arr/readings` and `/arr/readings`
  (nav "Readings", reviewer and administrator desks): every order whose ARR is read, by state and
  commission, with its reading state, its chapter preview (chapters, tables read, values,
  identity failures and how many a convention question explains), its review counts, its
  dataset (fixture labelled), and **the next human step** in words (confirm the chapters, confirm
  the mapping before real values can be approved, decide the pending values, publish); each
  commission with its mapping and whether it is confirmed, its unplaced labels and its open
  convention questions, linked to its workbench.  The localisation now records how many
  distinct labels the scan could not place (the 50 most frequent are kept), so the board says
  "N unplaced labels (the 50 most frequent in the workbench)" instead of a capped 50.  Live: 8
  states, 10 orders (7 real), 3,052 values previewed in the real orders, every real order at
  `chapters_proposed` waiting on a reviewer.

  **Increment 50 (2026-11-01): a second year for three states.**  The FY2025-26 orders of OERC
  (`de53fe6f…bc069fb`, 169 pp.), MPERC (`66254f46…b2693c2`, 259 pp.) and UERC (UPCL's business
  plan and MYT order, `5fc2d18f…273bc41e`, 412 pp.), downloaded from the URLs their profiles
  propose and read read-only.  MPERC's and UERC's earlier year read with no new rule (19 and 18
  chapters; 282 and 286 values).  OERC's did not, twice:
  - its proposal summary numbers its paragraph-headings ("31. Power Purchase Expenses"), which
    kept the order in numbered mode (11 chapters).  Paragraph mode now also applies when the
    numbered cue headings lie in parts that report the petition or the hearing, and in that mode
    numbered cue headings are headings too: 32 → 25 chapters with part G (the Commission's
    decisions) covered.  Removing the guard altogether was tried and broke NPCL (30 → 56) and
    UERC (19 → 34): UERC's own prose list of its seven chapters on one page had counted as a
    structure of parts; such a list (most parts on one page) is no longer one.  A one-word line
    over a row of figures ("Expenditure" opening each true-up table) is a table's cell, not a
    heading (OERC FY2026-27 40 → 26 chapters, the per-licensee adjustments no longer split).
  - its tables came out of the primary table reader with each row merged into one cell
    ("TPWODL 1827.481 2436.6"); the secondary reader had them right.  **Where the two readers
    disagree on a table's structure and the primary merged its cells while the secondary did
    not, the ARR reading takes the secondary's cells** under the primary's ordinal (the evidence
    still highlights the same table) and each value's rationale says "cell read by the second
    table reader".  OERC FY2025-26 44 → 238 values.  The tariff track's primary choice is
    unchanged.
  **Measured, ten real orders (seven states, three of them two years):** UPERC 503 values, 2
  failures; BERC 543, 3; HPERC 643, 0; JSERC 457, 5; OERC FY2026-27 479, 0 / **FY2025-26 238,
  0**; MPERC 264, 0 / **282, 0**; UERC 163, 2 / **286, 2**.  UERC's failures in both years are its
  gap convention (ARR-I3), now one workbench question with 4 pieces of evidence across the two
  orders.  Known limits: paragraph numbers of three digits ("178.") are not counted as numbered
  prose (the orders clear the ratio on their shorter ones); one "Expenditure" cell remains in
  OERC FY2026-27.

  **Increment 51 (2026-11-01): the Petition Studio — a modern interface for preparing an ARR
  petition** (operator request: a modern UI in the visual language of anduril.com for the users
  who prepare petitions; the language only — no brand, name, logo or asset of that company is
  used).  A dark, high-contrast design system in `apps/web/app/globals.css`: every colour is a
  token (near-black surfaces, hairline rules, ok/warn/bad/info/fixture tints, one signal accent);
  condensed uppercase display type, monospace labels, square controls; system font stacks only
  (the build has no network for web fonts).  All 40 hard-coded light colours of the existing
  pages were mapped to tokens, so the regulatory desk's pages (review, readings, workbench) take
  the same theme legibly.  The top bar is "Tariff Order Studio" with the client links first and
  the desk and administration links in two dropdowns that close on navigation; on a phone the
  links wrap under the brand (no horizontal scroll at 390 px, measured).  For the petition user:
  - **Home** (`/client`): a headline and the call to start a petition; a stat line (states in
    the library, documents located of those expected, documents with reviewed facts, your
    petitions, drafts ready); your petitions as cards with a five-segment progress bar; the five
    steps of preparing a petition; the regulatory record state by state with a bar of how far
    each state's documents have come.
  - **New petition**: the filing as four tiles (annual ARR, MYT control period, true-up, APR),
    the licensee and years, and a live summary of what will be created (the target years as you
    type).
  - **A petition** (ARR/MYT and true-up/APR): a header block, a numbered stepper, a **Next**
    banner naming the one thing to do now (supply the missing inputs, unblock the blocked lines,
    freeze, draft, edit and file the draft — derived from the case's own state, never deciding
    anything), and numbered panels for data readiness, assumptions, formulation, the draft
    (watermarked "Draft · not filed") and activity.  Every action, endpoint and permission is
    unchanged.
  - **A licensee** (`/client/licensees/<code>`): a profile — the reviewed ARR history at a
    glance (twelve key lines by year, each the strongest reviewed figure: final true-up, else
    provisional, approval, petition; labelled with its voice and linked to its order), the
    licensee's petitions with their progress, and its documents in the library.
  - **A draft petition**: the studio header with the watermark, and the DOCX narrative and XLSX
    formats as download buttons above the trace annex.
  Checked by screenshots at 1440 px and 390 px of the home, the new-petition flow, an annual ARR
  petition, a true-up petition, a licensee, a draft, the readings board and the desk menu.  `next lint` remains broken
  under Next 16 (pre-existing); the web gate is `tsc --noEmit`, clean.

  **Increment 156 (2026-11-11): the project narrowed to a DISCOM ARR database with plain-English → SQL; ARR 101 replaced.**
  - **Directions (operator, 2026-11-11):**
    - "we will not go ahead with the project".
    - Then: "Only scrap the tariff orders and make a database of all Discoms ARRs, with NL to SQL
      queries with explanations".
    - "change the vercel site accordingly".
    - "continue for next 12 hours".
  - **Nothing was shut down.** The `dev` stack on Google Cloud and the studio code are untouched.
    I listed what is still running for the operator to decide on. No decision has been given yet.
  - **Scraping (`tools/arrdb/arrdb/scrape.py`):**
    - **Sources:** the existing discovery profiles were run for UPERC, BERC, HPERC, JSERC,
      MPERC, OERC, UERC and JERC Goa/UTs. DERC, CSERC and MERC have no profile, so a sub-agent
      read their listing pages; that list is `tools/arrdb/data/extra-sites.json`, and each URL
      was checked with a 1 KB range request. The ten orders read in earlier increments are in
      `known-orders.json`.
    - **Downloads:** 115 order URLs were fetched and all 115 downloaded. Each file is kept by
      SHA-256 in the session cache; the PDFs are not committed. `tools/arrdb/data/orders.json`
      lists each URL, SHA-256 and size.
    - **Unreachable from this session's network:** the commission sites of Gujarat, Karnataka,
      Tamil Nadu, Andhra Pradesh, Telangana, Punjab, Haryana, Rajasthan, West Bengal, Assam,
      J&K, Manipur/Mizoram, Tripura, Meghalaya, Sikkim, Nagaland and Arunachal Pradesh. They
      either did not answer or could not be connected to.
    - **Kerala (KSERC):** its order list loads from `dev.erckerala.org/api/orders`. This
      session's permission policy refused that request, and it was not worked around.
    - All of these DISCOMs are in the database's reference list with no figures.
  - **Reading (`tools/arrdb/arrdb/reader.py`, `heads.py`, `build.py`):**
    - **What it does:** reads the text layer of each order. A table is taken when its printed
      title names the ARR. Each column is given a DISCOM, a year and a voice. Every value keeps
      its page and the line as printed.
    - **Skipped tables:** wires-only or supply-only tables, consumer-category splits,
      generation or transmission companies' tables in combined orders, and tables of contents.
    - **Bottom line:** one is chosen per order, DISCOM, year and voice (`arr_headline`). One
      more than five times away from the same DISCOM's median is set aside with its reason
      (12 set aside, all visible in the table).
    - **Result:** 111 orders in the database, after files duplicated across URLs were merged.
      82 had ARR tables read, 27 had none found, and 2 have no text layer. 483 tables,
      24,512 values. 625 bottom lines are in use, covering 31 of the 67 listed DISCOMs.
  - **Measured (`arrdb.check`, `tools/arrdb/data/check.json`):** the reader was compared with
    every hand-read figure in `packages/order-reproductions` and `packages/reference-filings`
    that comes from a table it read (10 orders).
    - It found 337 of 337 non-zero figures with the same number on the same page. 27 zero
      figures (dashes) were not compared.
    - It agreed on the voice 223 of 223 times and on the DISCOM 128 of 128 times.
    - **The other 72 orders read have no hand-read figures: their accuracy is not measured.**
    - **Problems found by eye and fixed during the build:**
      - MSEDCL's agricultural / non-agricultural split was taken for MSEDCL's whole ARR.
      - Maharashtra's wires-only tables were taken for the whole ARR.
      - Odisha's ten-column table had adjacent columns merged, so values landed in the wrong
        columns.
      - Generation-company tables in Chhattisgarh's combined orders were read as CSPDCL's.
      - An "Approved" column inside a petitioner's table was read as this order's approval.
    - More such cases surely remain.
  - **Plain English → SQL (`apps/arr-db/nl2sql.js`):**
    - **What it handles:** fixed rules, no model. It reads DISCOMs by code or name, states,
      commissions and ownership; years written as FY2026-27, 2026-27 or FY27, plus ranges and
      "last N years"; claimed or approved; ARR, APR, true-up or MYT stage; and the cost head.
    - **Question types:** lists, rankings, totals and averages (which name the DISCOMs counted),
      shares of the ARR, claimed versus approved (both figures from the same order), trends,
      and questions about the database itself.
    - **Rules it applies and explains:** where several orders decide the same year, the newest
      order is used; state totals are left out unless asked for. It lists every choice it made
      and every assumption.
    - **The SQL:** shown and editable; it runs in the browser through sql.js.
  - **Site:** `apps/arr-db` replaces `apps/arr-101` (deleted; it remains in git history) as the
    Vercel project `arr-101`, at the same address, https://arr-101.vercel.app. It has four parts:
    - the question box, the explanation, the SQL, and the answer with the page and quote of each
      row;
    - coverage by commission and DISCOM;
    - the method, with the measured accuracy (read from the database);
    - the limits;
    - the schema.
  - **Tests:**
    - `node --test apps/arr-db/nl2sql.test.mjs`: 11 of 11 pass. They cover how years are read,
      that every example runs, UPCL's FY2026-27 net ARR and MP's Table 74 totals matching the
      hand-read figures, claimed − approved arithmetic, ranking, sums, and meta questions.
    - `tests/unit/test_arrdb_reader.py`: 4 of 4 pass, on a synthetic order page (grouped
      header, dash, brackets, wrapped label, footer), plus the head, voice, year and stage rules.
    - Ruff check and format are clean.
    - Browser at 1440 px and 390 px (local, sql.js served locally): every example answers, there
      are no page errors, and nothing scrolls sideways.
  - **Not done / next smallest tasks:**
    - Read the 27 orders where no ARR table was found; most are MERC mid-term reviews and BERC
      annexures.
    - Add discovery profiles for DERC, CSERC and MERC so their lists are not hand-collected.
    - Ask the operator whether to allow `dev.erckerala.org` for Kerala.
    - Measure more orders by reading a sample by hand.
    - Decide what to keep running on Google Cloud.

  **Increment 155 (2026-11-10): ARR 101 — a public walkthrough of an ARR filing on Vercel, with the sample utility's own formats.**
  - **Directions (operator):** a Vercel frontend "like ARR 101" that walks through the key filing
    steps for a small utility with 150 consumers of all types, using simple questions and sample answers.
    It must have "uperc regulations check for every step" and an Anduril-style day-mode UI, and should feel
    "scientific rather than theoretical".  Then the correction: "we did not want NPCL formats, we wanted
    sample ARR to output these formats with sample numbers".
  - **What it is:** `apps/arr-101/`, a static site with no build step.  It is separate from the
    studio and has no backend, no database and no tariff-engine call.  Its ten steps are filing,
    sales, energy balance, power purchase, O&M, capital, working capital, revenue, ARR and
    checks.  Each step shows:
    - questions, with sample answers the reader can change;
    - the method as explicit relations (`method.js`);
    - the live working (`calc.js`);
    - the formats the step produces;
    - UPERC checks, 43 in all (`uperc.js`).  Each check quotes the UPERC MYT Distribution
      Regulations 2025 with its page.  `tests/unit/test_arr101_uperc.py` checks every quote
      against the text of its page in the regulation PDF.
  - **The sample formats (`formats-sample.js`):** the sample utility fills **64 kinds of format**
    (BS1–BS3, the energy balance, P1–P11, ESR1–ESR7, F1–F33, PPC, the ARR summary).  The format
    codes follow UPERC's filing set; no NPCL figure is used.
    - **Source badges:** "From your answers" means the format comes from the reader's answers.
      "Partly illustrative" means it also uses small invented constants (`EXTRA`: past years,
      monthly shape, staff, arrears, network and others), stated in the format's note.  "Not in
      this sample" means the format needs a past order, a true-up or open-access consumers the
      sample utility does not have.
    - **Updates:** the formats update live as answers change.
    - **Download:** `xlsx.js` is a small XLSX writer with no dependency.  It builds one workbook:
      an index sheet plus 64 format sheets.
    - **These are invented sample figures for teaching. No figure is a real tariff value.**
  - **Removed:** the NPCL format counts and their script (`formats.js`,
    `scripts/arr101_formats.py`) were built on a misreading of the direction.  They are gone.
  - **Deployed:** Vercel project `arr-101`, production, from this branch, at https://arr-101.vercel.app.
    This is not Google Cloud and not the studio.
  - **A broken intermediate deploy:** commit b9cdb1e held only the deletions.  `git add` stopped
    on a path already removed, so the new files were not in it.  It was pushed and deployed, so
    the live page was probably broken until d582ba4 (all files) was redeployed.  Verified after
    the redeploy, through the agent proxy:
    - 64 formats across the ten steps;
    - the ARR shows 110.19;
    - the workbook downloads (`arr-101-sample-formats.xlsx`, 65 sheets, read back with openpyxl);
    - no page errors.
  - **Tests:** `node --test apps/arr-101/calc.test.mjs apps/arr-101/formats.test.mjs` passes 7 of 7:
    - the sample's worked figures;
    - exactly 64 formats, every cell finite;
    - each format agrees with the working (ARR, revenue, consumers, power purchase, depreciation,
      interest, RoE, IoWC);
    - cross-consistency: BS2 balances, BS3 net change equals BS1 profit, HT + LT loss equals the
      total, the F32 total equals the ARR.

    pytest on `test_arr101_uperc.py` passes 2 of 2.  The browser was checked at 1440 px and 390 px:
    no horizontal scroll, and an open format stays open while inputs change.
  - **Not done / limits:**
    - The illustrative constants are not checked against any real utility.
    - The tariff proposal is a uniform factor across categories, not a cross-subsidy design.
    - Each UPERC check tests the sample against one clause.  It is not a compliance review.
    - No reviewer has looked at the site.

  **Increment 154 (2026-11-07): every fill-map column labelled, and the kept cells corrected.**
  - **Direction (operator, 2026-11-07):** "label the remaining sheets' columns next".
  - **The header reader (`arr/reference.py`) labels only part of the map.** It reads a year
    and a voice from header rows that name two or more years; it has run on the 25 mapped
    sheets.  Across the 60 sheets with fill-map cells, 33 had no labels and 6 had only some.
    These sheets name one year per sheet (PPC FY 25, F3 monthly), stack years in row blocks
    (F24, F1, F13), or print the voice only in the title.
  - **`column-labels.json` (100 hand labels, `scripts/npcl_column_labels.py`):** each label
    gives a year, a voice and a basis that quotes the printed words it rests on (cell and
    text).  A label may carry a row range.  All 4,492 map cells now have a label.
    - **Commission figures (`restated`):** ESR5's "(Previous Year Trued-Up) FY 22-23"
      billing determinants (48 cells).
    - **Tariff rates (`input`):** the current-tariff sheets' rate columns (ESR_3 FY24, FY25,
      FY27) are the tariff the Commission's order sets.  The proposed tariff's rates (ESR4)
      are the petitioner's.  Both are entered, not backed out of revenue ÷ units, which is
      how the bindings check them.  504 cells.
    - **Row range:** the ARR snapshot's column D is "Approved in Tariff Order" in its upper
      table (D4).  Below row 79 the same column holds the ARR year's claimed energy, ABR and
      ACoS, so D88–D90 are the petitioner's.
    - **Voices left to the reviewer (`not_printed`):** columns where the sheet gives a past
      year but not whether the figure is audited or trued-up.  These are F19's base years,
      F20's "Past years", P3, P7, P8 and P11: 25 columns, 86 map cells.  They are not
      guessed into the kept set.
    - **P4:** under the true-up year's "Trued-Up" heading, the voice row reads "Claimed".
      These are the petitioner's figures, not the Commission's.
  - **The kept-cell bug, fixed** (see the correction under increment 153): `column_labels()`
    converts the 0-based index.  The template now keeps **717 cells**:
    - 182 Commission figures (ARR 66, ESR5 48, Energy Balance 25, F27 17, F17 10, F18 10,
      F21 4, F28 2);
    - 504 tariff rates;
    - 31 cells the petitioner computes another way.
  - **Round trip of the new template:** 4,489 of 4,492 map cells equal the filing to four
    decimals.
    - F26_ROE!D12 and D14 are equal at the printed two decimals.
    - F25_IOL!D9 is filed as a typed 0 and filled as 0.0115 (0.01 crore).  It is a follow-on
      of the FY2023-24 column's known differences (D10–D15, kept); the engine reads 0 = 0
      from the filed inputs.
    - The narrative changes the same 20 cells as before.
  - **Guards** (`tests/unit/test_column_labels.py`, 6 tests):
    - every map cell has a label;
    - every hand label's quotes are checked against the workbook (the test caught my own
      "(audited accounts)" appended to five quotes, now moved to a note);
    - every order-quoted column, from either source, has an order word in its own header
      (an index slip fails this);
    - the kept counts and named cells (ARR!C46 kept, ARR!B46 not; the ESR3 and ESR4 rates;
      ESR5's 48);
    - a row range wins over its column;
    - unprinted voices are not kept.
  - The layout reports `cells_kept_rate` and `cells_labelled`.  The panel names the rates.
  Nothing verified, nothing approved: the labels are for the reviewer to confirm.

  **Increment 153 (2026-11-05): the narrative's summary tables filled from the formats — and the template keeps the Commission's figures.**
  - **Direction (operator, 2026-11-05):** "do the narrative tables next".
  - **`arr/narrative_fill.py`:** the nine summary tables increment 93 bound row by row to the
    ARR format are now *written* from a workbook, not only checked.  They are in the true-up,
    APR and ARR texts, the executive summary and Form-1: five DOCX files.
    - **Bound figures:** each is the sum of the format cells its row names, with its sign.  It
      is written at the cell's printed precision and style (thousands commas, Indian or
      international grouping, brackets or a minus, a dash for nil, %).  Changed cells are
      shaded green.  A nil figure the filing leaves blank stays blank.
    - **Merged cells:** a cell merged down over two rows is left as filed and reported.  In
      Form-1's Table-II, 53.01 is printed once for both open access and NTI (A56).
    - **Unbound figures:** figures in rows the binding does not cover are the petitioner's
      own, shaded yellow and listed: loss on sale of retired assets, efficiency gains, and
      power purchase provisions (A58).
    - **The rest:** the prose and every other table stay as filed.  A first paragraph in each
      document says so.
  - **Round trip on the filing** (`tests/unit/test_narrative_fill.py`): filled from NPCL's own
    workbook, the fill changes exactly 20 cells.  All 20 are among the 21 increment 93 found
    differing (A56, A57, A58 and last-place roundings).  The 21st is the merged cell, left as
    filed.  Read back, 252 of 253 figures match; the one left is that merged cell.  A figure
    changed in the workbook reaches all three tables that restate it.  `render` is tested
    style by style.
  - **In the case flow:** the fill job also fills the narrative.  It stores a ZIP (the five
    documents plus the tables' report), returned by `GET …/workbooks/{id}/narrative`.  The
    workbook summary and the panel show updated / already right / merged / petitioner's
    own.  The layout says 9 tables in 5 documents.
  - **What the narrative fill exposed, and the change made:**
    - Filled from the inputs template, the narrative's *approved* carrying costs moved by
      Rs 66 crore and Rs 15 crore: (122.34) → (56.05) for FY2024-25, and (77.30) → (62.25)
      for FY2025-26.
    - The cause: the template blanked every cell the engine could compute, including the
      Commission's own figures quoted from its orders (approved and trued-up columns).  The
      draft rules then recomputed them; 16 of those 143 cells differ.
    - **The template now keeps 179 cells as filed** (`petition._kept_cells`), shaded yellow
      and listed on a "Kept cells" sheet with the reason for each:
      - the 143 order-quoted cells (columns `reference.json` marks `restated`): to be
        entered from the order;
      - 36 more cells whose reproduction is a known difference (`fill-roundtrip.json`): the
        petitioner's own method.
    - The fill still checks each kept cell and never overwrites it.  The layout reports the
      counts, and the panel says what they are.
    - **Result:** filled from the new template, the 4,492 map cells equal the filing at its
      printed precision, and the narrative changes exactly the same 20 cells as filling from
      the filing itself.
    - **Limit:** order-quoted cells are recognised only on the 25 sheets where `reference.json`
      records column voices.  Approved columns elsewhere are still blanked.
    - **Corrected in increment 154:** the "143 order-quoted cells" were the wrong cells.
      `reference.json` counts a column's `index` from 0, and `_kept_cells` read it as counting
      from 1, so every kept "approved" or "trued-up" column was the one to its left (ARR's
      trued-up column is C; B was kept).  The round trip still matched because the engine
      reproduces most approved cells, and because the known-difference cells were kept
      correctly.  Increment 154 fixes the index and pins the right columns with a test.
  - **Checked in the browser on the running stack:** a new template uploaded and filled
    through the panel; 4,244 computed, 69 carried, 289 entered figures agree, 59 differ, 0 left
    blank, 0 conflicts; 20 narrative figures updated, 231 already right, 2 merged, 7 the
    petitioner's own.  No horizontal scroll at 390 px.  Form-1 was rendered to PDF: Table-II
    shows the green cells, the merged 53.01 and the yellow provisions row.  Once filled, that
    table's k = i − j no longer adds up, because the formats carry no provisions row (A58,
    the reviewer's).
  - **Found while checking:** none in the application.  My browser script raced once (it
    clicked Fill on the older upload before the new row appeared), and was rerun.
  Nothing verified, nothing approved; the filled narrative is a working draft, not a filing.

  **Increment 152 (2026-11-05): the formats workbook on the client case page.**
  - **Panel "Formats workbook"** on the case page, for annual / MYT cases and for true-up /
    APR cases (`apps/web/app/client/cases/[id]/petition.tsx`, `petition-upload.tsx`). It
    shows:
    - **The layout:** the filing, its years, the cells a fill writes, the bindings left out,
      and the case-year warning when there is one.
    - **Step 1:** download the inputs template.
    - **Step 2:** upload an inputs workbook (editors and owners only).  Each upload is listed
      with its comparison against the filed inputs: changed / as filed / blank, fill cells
      already entered, formulas saved without a value.  A Fill button is beside each.
    - **Step 3:** each filled workbook with its status.  The page refreshes every 10 s while
      a fill is queued or running.  For a filled workbook it shows the counts (computed,
      carried, entered figures that agree or differ, left blank, conflicts, passes) and
      downloads of the workbook and the full JSON report.
    - **Format by format:** a table per sheet, then, for the latest fill, the conflicts, the
      entered figures that differ from the computation (the first 200) and the cells left
      blank with the engine's reason.
    - A "working draft · not filed" mark on the panel and on every filled workbook.
  - **The client proxy** (`app/api/client/[...path]`) passes a multipart body through
    unchanged, so the upload goes through the same allow-listed proxy as every other case
    action.
  - **Checked in the browser against the running stack** (API, worker, web at 1440 px and
    390 px; local PostgreSQL; an NPCL case):
    - template downloaded and uploaded through the form: 18,358 input cells as filed,
      0 changed;
    - Fill clicked, the job queued, and the worker drained it;
    - the page then showed 4,397 computed, 95 carried, 160 entered figures agreeing,
      9 differing, 0 left blank, 0 conflicts, 11 passes, and 278 outputs the formats do not
      print;
    - the 9 are the filing's own known findings, for example BS3!D8 entered 45.17 against
      101.03 computed (A93).
  - **Page width:** no horizontal scroll at 390 px.
    - The upload input was 11 px too wide; fixed.
    - The readiness panel's "missing FY…" badges were 8 px too wide (not new); they now wrap.
  - `tsc --noEmit` clean.  No API change, so no new tests; the API is covered by
    `test_petition_workbooks.py`.
  - **For the next round (filling NPCL's petition):** open an NPCL case and download the
    template.  Replace the inputs with the petition's figures, upload, and fill.  Then review
    the differences and the blank cells format by format.  The layout is FY2026-27's (see
    increment 150 for the year shift).

  **Increment 151 (2026-11-05): the petition fill in the case flow — a UPERC / NPCL case fills its formats workbook.**
  - **Direction (operator, 2026-11-05):** next round NPCL's petition is filled; make the
    application ready.  This increment does the API and the job; the client page is next.
  - **Storage:** migration `0022_petition_workbooks`, model `PetitionWorkbook`.  A row is a
    case's *inputs* workbook (uploaded) or a *filled* one (made from an inputs row).  Statuses:
    stored, queued, running, filled, failed.  None of them files anything; check constraints
    enforce the role, the status, and that a filled row names its inputs.
  - **Service `arr/petition.py`:**
    - **Layout:** a case's licensee and commission are matched to a reference filing that has
      a fill map.  Today that is only `uperc-npcl-fy2026-27`; its manifest now states its
      `petition_years` (true-up FY2024-25, APR FY2025-26, ARR FY2026-27, from its title).  If
      none of the case's years is in the layout, a warning says the bindings have not been
      moved a year.  A licensee without a fill map is told so.
    - **Inputs template:** the filing with the 4,492 fill-map cells blanked, plus an
      "About this template" sheet (3.5 s to build).
    - **Upload checks:** the file must be an XLSX, a valid zip with `xl/workbook.xml`.  Macros
      are refused, and so is a file that inflates past 400 MB, before any XML is parsed.
      Every sheet the fill writes must be present.
    - **Upload summary:**
      - the 18,358 numeric cells the fill does not write, counted blank / changed / as filed;
      - the fill-map cells already entered (these will be checked, not overwritten);
      - formula cells saved without a value (the fill would see these as blank).
      The upload check takes about 6 s and 220 MB.
    - **The fill as a job:** job type `petition_fill`, in `services/worker/.../stages/petition.py`,
      not retried.  The filled workbook is stored under `petition/<utility>/<case>/<id>/`
      together with its full report.  Each sheet carries a "WORKING DRAFT" header, the cells
      are shaded and a "Fill trace" sheet is added.  A failure is recorded on the row.
  - **Routes `/cases/{id}/petition/…`:** layout, template, list workbooks, upload, fill (202),
    one workbook, report, download.  Access works as for cases: a viewer may read and download
    but not upload or fill, and another organisation gets 404.  Uploads and fill requests are
    in the case's activity.
  - **The fill report now separates two kinds of uncomputed output** (`petition_fill.fill`):
    - *blocked* is a fill-map cell left blank;
    - *not printed* is an output the engine could not compute in a cell the filed format leaves
      blank, such as rates on empty tariff rows.
    On NPCL's template, all 278 such outputs were the second kind; none were blocked.
  - **Tested** (`tests/integration/test_petition_workbooks.py`, through the API and the
    in-process worker, about 100 s):
    - an NPCL case: layout, template, the refused uploads, upload, fill, report, download;
    - all 4,492 cells written, 0 blocked, 0 conflicts, the draft header present;
    - access for viewers and other organisations, and the activity trail;
    - a FY2027-28 case gets the year warning; PVVNL has no layout.
  - **The filed workbook itself, uploaded, is a pure check** (run once by script, not in the
    test): 0 cells written, 4,606 agree, 59 differ (the known differences and the ties that
    repeat them), 0 conflicts, one pass.
  - **What this does not prove:** the template *is* the filing blanked, so the test shows the
    fill writing the filing's own figures back.  It does not show that a new petition's
    inputs give a right petition.  That is the reviewer's check, cell by cell, on the first
    real fill.
  - **Not yet:** the client page (increment 152).  `readiness` does not yet count the fill;
    the upload summary carries the counts for the page to show.
  Nothing verified, nothing approved; a filled workbook is a working draft from draft rules.

  **Increment 150 (2026-11-05): the ARR petition flow checked, and the rule engine fills NPCL's formats workbook.**
  - **Direction (operator, 2026-11-05):** check the flow of the ARR petition; in the next round
    NPCL's petition will be filled — make the application ready.
  - **The flow checked** (`docs/arr-petition-flow.md`).  The client case flow — case, readiness,
    assumptions, formulate, freeze, draft — does not use the rule engine (R-RULE-3).  Its UPERC
    plan is a 16-line skeleton and its template two sheets, so a case cannot draft NPCL's 74
    formats.  The engine (280 draft rules, 112 bindings) could check those formats but not write
    them.
  - **Fill mode in the engine (`arr/reproduce.py`):**
    - every result names its cell and gives the unrounded figure in the cell's unit (`fill`);
    - it marks a tie (a figure carried from another format) and the cell the tie repeats
      (`primary`);
    - filling, an output whose cell is blank is still computed;
    - an input from an earlier, still-blocked evaluation is absent, not an error.
    - Checks are unchanged.
  - **`arr/petition_fill.py` and `scripts/petition_fill.py`:**
    - **The fill map** (`fill-map.json`, 4,492 cells): 4,406 the bindings compute and the filing
      prints, plus 86 carried cells whose formula in the filing links them to the format they
      repeat.
    - **The fill:** passes until nothing changes; a binding is re-run only when a sheet it reads
      was written.  Blanks are filled; an entered figure is never overwritten, only checked; a
      carried cell copies the figure it repeats; blocked outputs stay blank with the engine's
      reason; conflicts are reported.
    - **The output:** computed cells shaded green and carried blue, a "Fill trace" sheet, a JSON
      report.
    - **The inputs template:** the filing with the map blanked.
    - **Left out:** 28 verification-only bindings — order approvals, annexures, the ledger, the
      pipeline.  Two are newly declared `"fill": false` with a reason: `chain-arr.json` (the
      end-to-end check) and `esr2-sales-at-cagr.json` (the comparison with Reg. 30.2).  P9
      declares `fill_places: 0` (the format rounds to whole MW).
    - A new `f21-employee-components.json` binds F21's own totals (24 / 24), so F20's figure no
      longer stands in for F21's (A83).
  - **The round trip on NPCL's FY2026-27 filing** (`fill-roundtrip.json`; tested live):
    - **Known differences kept as filed** (the 49 cells whose reproduction already differs):
      **4,443 / 4,443 cells refilled equal to the filing at its printed precision**, no
      conflict, none left blank, 10 passes.
    - **None kept:** 4,427 / 4,492; the 65 others are the known differences and what follows from
      them through the chain.
    - A fill takes about 75 s.
  - **Not yet in the application:** no API, case or page uses the fill.  That is the next increment.
  - **A decision for the operator:** the fill map is tied to the FY2026-27 layout.  A FY2027-28
    petition shifts every year column, and the bindings would first have to move a year.
  Nothing verified, nothing approved; a filled workbook is a working draft from draft rules.

  **Increment 149 (2026-11-03): NPCL — the accounts (BS1–BS3), and every format of the filing accounted for.**
  - **One more format rule (45; UPERC 280):** a difference (one line less another).
  - **Checks:**
    - **`bs1-profit-and-loss.json` 18 / 21.**  Income, expenses, profit before the rate-regulated
      movement, before tax and after: all exact from the lines.  The three differences are the
      profit before tax against the cash flow's opening line (A93).
    - **`bs2-balance-sheet.json` 27 / 27.**  Each group from its lines, and the balance: assets with
      the deferral balance against equity and liabilities, each side from its lines, in all three
      years.
    - **`bs3-cash-flow.json` 25 / 27.**  Each section, the net change and the year-end cash; two
      differences (A94).
  - **Findings (petitioner):**
    - **`A93`:** the cash flow opens on a profit before tax that is never BS1's (45.17 / 47.67 /
      91.49 against 101.03 / 111.21 / 120.73).  FY2024-25's is built from F26's RoE less tax and
      dividends, less a typed 22.07.
    - **`A94`:** FY2023-24's year-end cash adds a typed 0.01.  Computed, it equals the balance
      sheet's exactly; carried forward, FY2024-25 ends 0.0038 over the balance sheet's.
  - **A new accounting status, `no_arithmetic`.**  `formats-index.json` declares it with a reason
    for each format; `scripts/reproduce_formats.py` reports it; the reference page shows the
    reason (typechecked, not screenshot-checked).  It covers four formats: F2 (assumptions in
    words), P2 (hours of supply as typed ranges), P6 (typed complaint counts), P10 (pending cases
    in words).
  - **Formats accounted: 67 reproduced, 4 with no arithmetic, 2 blank (ESR6 subsidy, F10 bulk
    supply tariff), 1 missing (ESR7, monthly billing determinants).**
    - **The operator's direction from increment 143 is done for the formats:** every one of NPCL's
      formats with figures to compute is now checked by a binding.
    - **It is not done for reliability:** every rule is a draft and every clause unverified; the
      sign-off panel has nothing signed; the 13 findings of increments 143–149 (A82–A94: 12 for
      the petitioner, A85 for the reviewer) await answers.
  Nothing verified, nothing approved.

  **Increment 148 (2026-11-03): NPCL — the performance formats with arithmetic: losses by voltage (P1A), the network (P4), arrears (P5), transformer failures (P7), accidents (P8), peak demand (P9), land (P11).**
  - **10 more format rules (44; UPERC 279):**
    - a stock rolled forward, a ratio, a shortfall (never negative), a figure grown at a rate,
      and a part scaled with its whole;
    - a level's energy lost or passed down, its loss share (computed or given), and the
      distribution loss as 1 − out / in.
  - **Checks:**
    - **`p1a-losses-by-voltage.json` 55 / 56.**  Energy passed from 33 kV to 11 kV to LT is carried
      as computed.  Energy in is tied to the ARR's row 8, energy out to ESR3's sales (which the
      ARR's row 9 carries), the loss to row 10.  Checked to five places.
    - **`p4-physical-statistics.json` 77 / 78.**  Each stock opens on the printed year before.
    - `p5-arrears.json` 8 / 8, `p7-transformer-failures.json` 92 / 92 (counts tied to P4),
      `p9-peak-demand.json` 12 / 12 (whole MW), `p11-land.json` 2 / 2.  P11's addition in rupees
      equals F13's leasehold-land scheme in crore, converted by the engine's units.
    - **`p8-accidents.json` 4 / 5.**
  - **Findings (petitioner):**
    - **`A90`:** P1A's FY2024-25 sales by voltage are 0.0024 MU short of ESR3's.
    - **`A91`:** P4's FY2024-25 LT meters are 939 above the roll forward.
    - **`A92`:** P8's FY2022-23 HV total is 2 where its entries add to 3.
  - **Formats accounted: 64 reproduced, 1 read, 6 present, 2 blank, 1 missing.**  Left: BS1–BS3 (the
    accounts); F2, P2, P6, P10, which hold text or typed statistics with no arithmetic; ESR6 and
    F10 (blank); ESR7 (not filed).
  Nothing verified, nothing approved.

  **Increment 147 (2026-11-03): NPCL — the rest of power purchase: merit order (F4), renewables (F5), competitive bids (F7), short term (F8), the procurement plan (F9).**
  - **2 more format rules (34; UPERC 269):** a monthly average, and a PPA's levelised tariff as
    capacity + energy charges.
  - **All exact:**
    - `f4-merit-order.json` 71: lines' cost and cost per kWh, totals tied to F1, three years.
    - `f5-renewable.json` 6: PPA by PPA to the totals and to F4's renewables line.
    - `f7-competitive-bids.json` 5: generation equal to PPC FY 25's for the same PPAs; levelised
      tariff = capacity + energy (4.05, 5.19).
    - `f8-short-term.json` 15: each line's cost per kWh, totals and average.
    - `f9-procurement-plan.json` 9: the monthly MW averages.
  - **F2 (assumptions for power purchase) is text** — no figure to compute.  It is left "present"
    until the accounting can say so in its own words (next increment).
  - **Formats accounted: 57 reproduced, 4 read, 10 present, 2 blank, 1 missing.**
  Nothing verified, nothing approved.

  **Increment 146 (2026-11-03): NPCL — power purchase by source (F1) and by month (F3, three years).**
  - **7 more format rules (`formats.v1.json`, 32; UPERC 267):** fixed, energy and other charges per
    source with their totals, and the average cost on the total.  The existing per-source billed /
    rate rules are reused.
  - **`f1-power-purchase.json`: 104 / 104** — each source's cost and cost per kWh, three years.
    Units are tied to the ARR's row 8; cost to the PPC formats' totals (the ARR's rows 20, 22, 23).
  - **`f3-monthly-2024-25` / `2025-26` / `2026-27`: 367 + 468 + 436 = 1,271, all exact** — each
    source month by month (cost, cost per kWh) and its year from the months.  A source is tied to
    F1 only where exactly one non-nil F1 row has the same units and cost — by value, never by name.
  - **Finding `A89` (petitioner):** F1's FY2026-27 rows "MPL-BLA Power" and "MPL-Sai Lilagar" read
    each other's PPC FY 27 rows: F1 keeps FY2025-26's order.  The two costs (101.60, 103.09) swap
    names; the totals are unaffected.
  - **Formats accounted: 52 reproduced, 5 read, 14 present, 2 blank, 1 missing.**
  Nothing verified, nothing approved.

  **Increment 145 (2026-11-03): NPCL — the revenue formats: open access (ESR1), the sales forecast (ESR2), billing determinants (ESR5).**
  - **The rule language gains `root(x, n)`**, the n-th root of a pure, non-negative number, n a
    whole-number literal.  It exists for a compound growth rate; anything else is refused (tested).
  - **`uperc/sales-forecast.v1.json` (2 draft rules):** the seven-year CAGR and a year projected at
    it.  The clause is Reg. 30.2 of the 2025 Regulations, p.38 of the copy in the session — not
    verified.  **`formats.v1.json` +8:** generic lines and totals (number, MU, Rs crore), a
    percentage change, and open-access revenue.  UPERC now has 260 draft rules in 30 files.
  - **`esr1-open-access.json`: 12 / 12** — four years to the ARR's row 51.  The charges are typed:
    no rate in the formats gives them.
  - **`esr2-sales-forecast.json`: 69 / 69** — 33 CAGRs and ten years' totals, sales tied to the
    ARR's row 9.  Checked to five places: the format's float shows in the sixth.
  - **`esr2-sales-at-cagr.json`: 5 / 10** — FY2026-27 at Reg. 30.2's basis.  Exact to 0.1 MWh for
    HV-2, LMV-2, LMV-4, LMV-5 and LMV-9.  The rest total 55.00 MU under that basis.
  - **`esr5-billing-determinants.json`: 108 / 120** — subtotals from the sheet's own SUM ranges, the
    grand total, ties to ESR3 and the ARR, and FY2023-24 summed against the ARR.  The 12
    differences are all the %-change column (A86).
  - **Findings:**
    - **`A85` (reviewer):** four categories at the petition's moderated rates rather than Reg.
      30.2's CAGR, which only the Commission can allow.
    - **`A86` (petitioner):** the "% change wrt previous" column divides by FY2022-23; on
      FY2023-24 the total is 13.51 %, not 19.33 %.
    - **`A87` (petitioner):** connected load is labelled kW but the figures are MVA.
    - **`A88` (petitioner):** LMV-7 sits under its CAGR with no departure stated, and ESR7, the
      monthly basis, is not filed.
  - **Formats accounted: 48 reproduced, 5 read, 18 present, 2 blank, 1 missing.**
  Nothing verified, nothing approved.

  **Increment 144 (2026-11-03): NPCL — the capital formats: assets not in use (F11), consumer contributions (F12), the investment plan (F13).**
  - **9 more draft rules in `uperc/formats.v1.json` (17; UPERC 250):** per-class cost, depreciation
    and written-down value of withdrawn assets with their totals; the consumer-contribution roll
    forward; the release on retirement; F13's equity column.  F13 reuses `uperc.capex.scheme`.
  - **`f11-assets-not-in-use.json`: 30 / 30** — three years, class by class, totals carried to F14's
    deletions (row 13) and depreciation (row 35).
  - **`f12-consumer-contributions.json`: 10 / 10** — three years chained on computed closings; the
    FY2024-25 opening is a literal in F12's own formulas (378.83, stated with its reason).  The
    release on retirement (−2.178) is F14's retired consumer-funded block (4.979) less its
    depreciation (2.800), exactly.
  - **`f13-investment-plan.json`: 18 / 18** — five years of schemes to totals, carried to F24 and
    F22 (FY2022-23), F14 (FY2023-24, FY2024-25), F16 and the snapshots (FY2025-26, FY2026-27).
  - **Finding `A84` (petitioner):** F13's grants, consumer-contribution and loan columns are blank,
    so its equity column is the whole capex; F14 funds the plan 70:30 net of contributions.
  - **Not counted:** F12's FY2024-25 closing also appears in the balance sheet (BS2!E59).  That tie
    is left to the accounts increment, so that one cell does not count BS2 as reproduced.
  - **Formats accounted: 45 reproduced, 7 read, 19 present, 2 blank, 1 missing.**
  Nothing verified, nothing approved.

  **Increment 143 (2026-11-03): NPCL — the whole ARR suite, first: non-tariff income (F28) and employees by grade (F20).**
  - **Direction (operator, 2026-11-03):** focus on NPCL and finish the whole ARR suite — every
    format of the filing's index checked, not only those a regulation computes.  Before this
    increment 32 of 74 were not reproduced (22 present, 9 read, 2 blank, 1 missing).
  - **A new rules file, `uperc/formats.v1.json` (8 draft rules):** the formats' own arithmetic —
    lines to totals, totals to the ARR format.  Not regulation; where a regulation computes a
    figure, its rule governs.  UPERC now has 241 draft rules.
  - **`f28-nti.json`: 19 / 19.**  The seventeen heads to F28's total, carried to the ARR's row 50;
    telecom and other business to row 49 — five columns.  The ARR year's non-tariff income is no
    longer a record taken on trust: FY2026-27 is now 17 computed, 18 tied, 11 records.
  - **`f20-employees.json`: 14 / 15.**  Grades to totals (head counts and cost) and each year's cost
    against F21's gross cost.
  - **Findings `A82`, `A83` (petitioner):**
    - **A82:** F28's approved FY2024-25 column has one figure, 53.01, on the rent head; the APR's
      approved 63.99 is a total with no heads.
    - **A83:** F20's FY2024-25 grades add to 95.445614, F21's components (carried to the ARR) to
      95.419847 — 2.58 lakh apart; earlier years agree to the sixth place.
  - **Formats accounted: 42 reproduced, 8 read, 21 present, 2 blank, 1 missing.**
  Nothing verified, nothing approved.

  **Increment 142 (2026-11-03): JSERC — depreciation, normative loan, equity, return and the ARR over the control period.**
  - **Two records** in the JSERC folder: `figures-capital-fy2027-31.json` (100 figures: Tables 124,
    125, 127, 133; paras 4.300–4.301) and `figures-arr-fy2027-31.json` (107 figures: Table 137 and
    FY2026-27's gap); 207 / 207 quotes verified.
  - **15 more draft JSERC rules (18 in all, from FY2026-27):** depreciation rate as audited
    depreciation over audited average GFA (Clause 10.39), depreciation, loan closing / average /
    interest (repayment = depreciation, 10.23), equity closing / average, equity added since
    1 April 2026, the return as the order applies it, and the ARR summary to the gap.
  - **Binding `approval-capital-fy27-31.json`: 34 / 40 exact**, five years chained on computed
    closings; the rest within the printed precision of the chained additions (≤ 0.0063).  The
    printed 4.39 % is applied unrounded (at 4.39 %, FY2026-27 would be 517.29, not 517.22).
  - **Binding `approval-arr-fy27-31.json`: 11 / 26 exact from the printed heads (all within two
    paise); end to end from the computed heads 13 / 16**, FY2026-27's gap 366.25 exact; FY2029-30
    a paisa over (its printed power purchase and O&M are each a paisa over their parts).
  - **Findings `J1`, `J2` (reviewer):**
    - **J1:** Table 124 is headed "Rs. Crore" but is Rs lakh (para 4.301's lakh table, 22,39,690.88);
      its average takes IT equipment's restated opening and no other row's.  On other bases the
      FY2026-27 depreciation is 517.40 or 517.09.
    - **J2:** the return is 15 % on half of *all* equity added since 1 April 2026; Clause 10.20 as
      quoted reads the full beginning-of-year equity plus half the year's addition — 356.78 more
      over FY2027-28 to FY2030-31.
  Nothing verified, nothing approved.

  **Increment 141 (2026-11-03): HPERC — O&M built from its parts, and the PIP's unit.**
  - **The record:** `order/figures-om-fy2026-27.json` in the HPERC folder holds 55 figures
    (Tables 227, 228, 231; para 9.18.7), 55 / 55 quotes verified.
  - **Four more draft HPERC rules (16 in all):** employee expenses, R&M, A&G, and O&M built
    from the three.
  - **Binding `approval-om-fy27.json`: 7 / 12 exact.**  Built from its parts, the approved O&M
    is Table 232's 3,468.46, also the ARR's O&M.  The other differences are a paisa off, except
    the two below.
  - **Findings `H3`, `H4` (reviewer):**
    - **H3:** the text approves the public interaction programme as "Rs. 0.71 Lakh", but Table
      231 adds 0.71 to A&G in crore.  O&M and the ARR carry the crore.  At lakh, A&G is 314.39
      and the ARR 0.70 crore lower.
    - **H4:** the MYT order's A&G is cited as 314.31 in the text, printed 314.39 in the table,
      and its parts add to 314.38.
  Nothing verified, nothing approved.

  **Increment 140 (2026-11-03): R-APP-3 — an amended clause applies only from its effective
  year.**
  - **The capability was already in the engine.**  A rule id may carry versions with
    non-overlapping years, and `RuleSet` takes the version in force each year.  A `superseded`
    version is dropped, and two different rules claiming one output in one year are refused.
  - **A unit test now pins it** with two constructed versions of one rule: 15% RoE to
    FY2025-26, and from FY2026-27 the same less a 10% haircut.  It also checks the superseded
    version and the rival rule.
  - **Already in use:** UPERC's 2019 and 2025 rules, and UERC's 2021 and 2024.
  - **Not built:** an effective date within a year, which resolves to the fiscal year; and
    exceptions with precedence.
  - The matrix row moves from none to partial.

  **Increment 139 (2026-11-03): the rules compared across commissions.**
  - **API (read-only, analyst): `GET /arr/rules-compare`** returns every commission's draft
    rules grouped by schedule (sales to tariff design, true-up sharing and carrying).  Each rule
    has its title, output = formula, the clause, whether verified, and its years, plus each
    commission's totals.  Approved: 0 anywhere.  Clauses verified: 0 anywhere.
  - **Web: `/arr/rules/compare`** — a panel per schedule and each commission's rules in it.
    For example, interest on working capital lists six commissions: BERC's 45 days with
    deductions, HPERC's average deposits, JSERC's nil floor, MPERC's wheeling and supply apart,
    UERC's month of O&M, and UPERC's NPCL formats.  It is linked from `/arr/reference`.
  - **The totals:** UPERC 233, UERC 47, MPERC 48, HPERC 12, BERC 5, OERC 5, JSERC 3 — 353
    draft rules, none approved.
  - **Checks:**
    - integration test: the commissions, the schedule, JSERC's floor, nothing approved,
      authentication;
    - contracts regenerated, no drift;
    - `tsc` clean;
    - screenshots at 1440 and 390 px: no horizontal scroll.
    Next's dev server again wrote `apps/web/AGENTS.md` and `CLAUDE.md`; they were removed, not
    committed.
  Nothing verified, nothing approved.

  **Increment 138 (2026-11-03): a seventh commission — OERC's four Odisha DISCOMs, FY2026-27:
  bad debts, RoE and depreciation.**
  - **The order:** OERC's FY2026-27 order for TPWODL, TPNODL, TPSODL and TPCODL (SHA-256
    `d58d2817…e0ab`, the loader's `OERC-DISCOMs-FY2026-27`).
  - **New folder `packages/order-reproductions/oerc-discoms-fy2026-27/`:** the record holds
    Tables 72 and 74–77 (76 figures, 76 / 76 quotes verified).
  - **Five draft OERC rules in `packages/arr-rules/oerc/rst-2022.v1.json`** (Regs. 5.8.1,
    3.6.1, 3.6.4, 3.5.2 (b) as the order quotes them):
    - bad debts at 1% of revenue;
    - depreciation, transferred plus new;
    - the equity for RoE: the reserve price and 30% of the assets put to use;
    - RoE approved, 16% of that;
    - RoE as proposed, 16% on the opening equity and half the additions.
  - **Binding `approval-dep-bd-roe-fy27.json`: four DISCOMs, approved and proposed, 23 / 24
    exact.**
  - **Findings `O1`, `O2` (reviewer):**
    - **O1:** the approval's RoE is on the opening equity, where Reg. 3.6.4 as quoted says the
      normative average.  The DISCOMs' proposals took the average.
    - **O2:** TPCODL's proposed RoE rows add to 171.20 against the 171.14 printed.
  - **Every order in this session now runs on the engine:** seven commissions (UPERC, UERC,
    MPERC, HPERC, JSERC, BERC, OERC), all served at `/arr/reference` and `/arr/orders/<id>`.
  Nothing verified, nothing approved.

  **Increment 137 (2026-11-03): a sixth commission — BERC's working capital for NBPDCL and
  SBPDCL, FY2026-27.**
  - **The order:** BERC's FY2026-27 order for the two Bihar DISCOMs (SHA-256 `a247053b…4537`,
    the loader's `BERC-DISCOMs-FY2026-27`).
  - **New folder `packages/order-reproductions/berc-discoms-fy2026-27/`:** the record holds
    Tables 6.81 and 6.82 and the rate (43 figures, 43 / 43 quotes verified).
  - **Five draft BERC rules in `packages/arr-rules/berc/myt-2024.v1.json`** (Reg. 26 as the
    order quotes and summarises it):
    - the sub-total: 45 days of revenue and spares;
    - the deductions: a month of power purchase, 45 days of depreciation, RoE and contingency
      reserve, the deposits, and 45 days of any grant;
    - the net requirement; the interest; and the rate, MCLR + 150 bp (10.25%).
  - **Binding `approval-iowc-fy27.json`: claimed and approved, each DISCOM a category, 10 / 14
    exact.**  The sums are a paisa off at most.  NBPDCL's claimed interest (38.449 against 38.46)
    is within its printed rate.  Approved interest: 40.44 (NBPDCL), 20.11 (SBPDCL).
  - **Six commissions now run on one engine:** UPERC, UERC, MPERC, HPERC, JSERC and BERC.
    Each new commission needed draft rules, records and a binding, but no engine change.
    Their formulas for the same head differ, all within the one rule language:
    - **working capital:**
      - UERC: a month of O&M with spares, less a month of power purchase;
      - MPERC: wheeling and supply apart, a negative admitted;
      - HPERC: average deposits;
      - JSERC: a negative floored at nil;
      - BERC: 45 days, with depreciation and RoE deducted;
    - **controllable sharing:** UPERC 2025 and UERC 2021.
  Nothing verified, nothing approved.

  **Increment 136 (2026-11-03): a fifth commission — JSERC / JBVNL, the MYT working capital
  FY2026-27 to FY2030-31.**
  - **The order:** JSERC's 2026 MYT order for JBVNL (SHA-256 `0391dd27…9108`, the loader's
    `JSERC-JBVNL-2026`).
  - **New folder `packages/order-reproductions/jserc-jbvnl-fy2026-27/`:** the record holds
    Table 131 (40 figures, 40 / 40 quotes verified).
  - **Three draft JSERC rules in `packages/arr-rules/jserc/tariff.v1.json`** (Clauses
    10.31–10.32 as the order quotes them):
    - the requirement: spares plus receivables, less a month of power purchase and the
      deposits;
    - the interest as computed;
    - the interest approved, floored at nil.  The floor is the order's practice (para 8.52),
      shown in constructed examples of both branches.
  - **Binding `approval-iowc-fy27-31.json`, five years, each its own evaluation: 14 / 15
    exact.**  One requirement is a paisa off.  The computed interest is negative for FY2026-27
    to FY2028-29 (−38.74, −21.71, −2.75) and approved nil; FY2029-30 and FY2030-31 are approved
    as computed.
  - **Two commissions, opposite treatments:** MPERC admits and nets a negative working capital
    (M1); JSERC approves nil.  M1 now records the contrast.  NPCL's FY2026-27 working capital
    under UPERC was also nil (increment 111); whether for the same reason is not established
    here.
  - **The desk:** five commissions' orders are now served at `/arr/orders/<id>`.
  Nothing verified, nothing approved.

  **Increment 135 (2026-11-03): a fourth commission — HPERC / HPSEBL, FY2026-27: working
  capital and the ARR's arithmetic.**
  - **The order:** HPERC's FY2026-27 order for HPSEBL (SHA-256 `0f3d9e9d…ec74`, the loader's
    `HPERC-HPSEBL-FY2026-27`).
  - **New folder `packages/order-reproductions/hperc-hpsebl-fy2026-27/`:** the record holds 85
    figures (Tables 232, 234, 236, 244, 247; para 11.5), 85 / 85 quotes verified.
  - **12 draft HPERC rules in `packages/arr-rules/hperc/myt-2023.v1.json`:**
    - working capital, Reg. 34 as quoted: a month of O&M, two months of revenue, spares at 40%
      of a month's R&M, less the year's average deposits, at MCLR + 350 bp;
    - O&M, power purchase, the ARR, the ARR with adjustments, and the surplus.
    The years the 2023 Regulations govern are not bounded yet.
  - **Binding `approval-iowc-arr-fy27.json`: 7 / 15 exact.**
    - Exact: power purchase (5,678.19), the ARR (9,689.18), and the month's O&M, receivables,
      spares and rate.
    - The working capital is within its inputs' printed precision.
  - **Findings `H1`, `H2` (reviewer):**
    - **H1:** Table 247's adjustments add to 8,640.69, but the order carries 8,641.16 — 0.47
      more — into its ACoS and its surplus of 3.61, which with the table's lines is 4.08.
    - **H2:** the working capital interest (140.58) implies an MCLR of 8.8166% printed as 8.82%.
  - **The desk:** the order is listed on `/arr/reference` and served at
    `/arr/orders/hperc-hpsebl-fy2026-27` with no change to the API or the pages.
  Nothing verified, nothing approved.

  **Increment 134 (2026-11-03): the reproduced orders on the desk.**
  - **API (read-only, analyst):**
    - `GET /arr/order-reproductions` lists each reproduced order with its check counts and
      number of findings.
    - `GET /arr/order-reproductions/{id}` gives the manifest (URL, SHA-256), the rules'
      status (draft, approved 0, clauses verified 0), the records (figures and pages), every
      binding's checks — each with its gap, the unrounded computation less the printed
      figure — and the findings.
    - The bindings are evaluated on request; nothing is stored.
    - Module `tariff_api/order_reproductions.py`; a path outside the folder answers 404.
  - **Web:**
    - `/arr/reference` now lists the reproduced orders beside the reference filings and links
      UERC's and MPERC's rules.
    - `/arr/orders/<id>` shows the findings, every binding's checks (printed, computed, gap,
      result) and the records.
    - The page explains that a difference is not a failure: each test bounds it by the printed
      precision of its inputs.
  - **Contracts:** regenerated, no drift.
  - **Checks:** `tsc --noEmit` clean.  After the commit, screenshots at 1440 and 390 px of
    `/arr/reference` and both `/arr/orders/<id>` pages showed no horizontal scroll.  Fixed after
    them: counts listed match-first, and the status sentence capitalised.  Next's dev server
    wrote `apps/web/AGENTS.md` and `CLAUDE.md` on start-up; they were removed, not committed.
  - **Today:** UERC / UPCL shows 65 match and 56 differ, 6 findings; MPERC / three DISCOMs
    shows 135 match and 60 differ, 4 findings.  Every difference is bounded by its test.
  Nothing verified, nothing approved.

  **Increment 133 (2026-11-03): MPERC — each DISCOM's ARR split between wheeling and supply, and
  the order's departures from its matrix.**
  - **The record:** `order/figures-allocation-fy2026-27.json` in the MPERC folder holds 96
    figures (the Reg. 8.11 matrix as quoted, Tables 75 and 76), 96 / 96 quotes verified.
  - **Four more draft MPERC rules (48 in all):** an item's wheeling and supply shares, and the
    two totals.
  - **Binding `approval-allocation-fy27.json`: one evaluation per DISCOM, the ARR items as
    categories.**
    - Table 74's admitted heads, split by the matrix and by the order's own splits where it
      departs; each departure is a stated constant with its reason.
    - 41 / 48 exact; the other 7 a paisa off (half-paise ties).
    - The two totals add to each DISCOM's ARR, West's a paisa short.
  - **Finding `M4` (reviewer):**
    - Working capital interest is put by activity (East: 23.79 wheeling, 46.74 supply) where
      the quoted matrix says 10:90 of the total (7.05 / 63.48).
    - Other income and the past true-ups are split 10:90, and the smart-meter lease and R&D are
      put with loan interest at 95:5.  The matrix as quoted lists none of these.
    - The effect falls on the wheeling charge.
  Nothing verified, nothing approved.

  **Increment 132 (2026-11-03): MPERC — O&M (escalation, R&M on GFA, DA) and the working
  capital's inventory base (M2).**
  - **The record:** `order/figures-om-fy2026-27.json` in the MPERC folder holds 83 figures
    (Table 54's yearly inflations, averages, weights and rates; para 2.190's DA; Table 55),
    83 / 83 quotes verified.
  - **Ten more draft MPERC rules (44 in all):**
    - escalation: the five-year average of yearly inflation, and the rate at 30% WPI and 70%
      CPI (Reg. 36.3, as the order quotes it);
    - R&M at 2.30% of the opening GFA (Reg. 36.4);
    - DA: the year's month-weighted rate on basic pay;
    - employee expenses; the O&M total, less capitalisation and plus RDSS OPEX; the State sum;
    - the inventory's base, the gross GFA at the start of the previous year, and the inventory.
  - **Binding `approval-om-fy27.json`: 24 / 31 exact.**
    - Exact: every escalation figure (4.93, 5.78, 5.05, 4.95 → 5.53, 4.98); R&M for all three
      DISCOMs; DA at 64% of basic.  The O&M totals are the ARR's and the working capital's.
    - Central's DA is a paisa off (basic printed rounded), and that carries into its employee
      and O&M totals.  These and the other differences are within printed precision, bounded.
  - **Finding M2, the inventory base, resolved by reproduction.**  1% of Table 55's opening
    gross GFA less Table 57's FY2025-26 additions, for two months at 80% / 20%, gives all six
    inventories exactly.  So "the Gross Fixed Assets for previous year" reads as the gross GFA
    at the start of the previous year.  The finding stays open for the reviewer to confirm.
  - **Not reproduced:** the employee and A&G base (three years' actuals, not printed beside
    the table) and the capitalisation, which the stated shares (3.75%, 1.46%, 1.53%) do not
    give from the printed heads.  Both are records.
  Nothing verified, nothing approved.

  **Increment 131 (2026-11-03): MPERC — each DISCOM's ARR (Table 74), end to end, and the
  working capital's loop.**
  - **The record:** `order/figures-arr-fy2026-27.json` in the MPERC folder holds 144 figures,
    claimed and admitted for each DISCOM and the State, 144 / 144 quotes verified.
  - **Four more draft MPERC rules (34 in all):** total expenses (eleven heads), ARR less other
    income, the total including the FY2024-25 true-ups (MP Transco's gap and MP Genco's surplus
    passed through, the DISCOM's own gap), and the State sum.
  - **Binding `approval-arr-fy27.json` (the table's arithmetic):** 5 / 20 checks exact, and
    every other check within 2 paise of eleven printed heads, on both the claimed and the
    admitted side.
  - **End to end (the test):** depreciation, project-loan interest, working capital interest
    and RoE as the other MPERC bindings compute them, unrounded:
    | DISCOM | Computed | Printed |
    |---|---|---|
    | East | 17,889.43 | 17,889.37 |
    | West | 24,841.79 | 24,842.10 |
    | Central | 19,892.55 | 19,892.55 (exact) |
    | State | 62,623.76 | 62,624.02 |
    Each DISCOM is within the precision of the rates the order prints to two decimals.  West's
    0.31 is mostly its 3.25% depreciation rate (184.15 printed implies 3.2548%).
  - **The loop:** each DISCOM's total including true-ups is the "annual revenue from tariff and
    charges" whose two months are its working capital receivables (Table 61).  That total
    includes the working capital interest.  With receivables at the printed total, the interest
    reproduces exactly (increment 129).  The engine refuses cycles, so the order's fixed point
    enters as a record; the test ties the two.
  Nothing verified, nothing approved.

  **Increment 130 (2026-11-03): MPERC — depreciation, project loans and equity for three
  DISCOMs, chained FY2025-26 → FY2026-27; the engine carries one licensee's balances.**
  - **Engine:** a computed input may name a category (`{"computed": …, "category": "east",
    "output": …}`).  One licensee of a combined order, or one asset class, is carried by its own
    unrounded balance from one evaluation to the next.
  - **The record:** `order/figures-dep-loan-fy2026-27.json` in the MPERC folder holds 138
    figures (Tables 57, 59, 65, paras 2.206 and 2.220 (g)), 138 / 138 quotes verified.
  - **Rules: 18 more draft MPERC rules (30 in all).**
    - Net GFA (less contributions and grants), its average, and depreciation at the DISCOM's
      weighted rate (the order's interim method).
    - Equity: 30% of the net addition, and admitted as the lower of that and the proposed
      (Reg. 22 as the order states it).
    - The loan addition as the net addition less the equity admitted.  This replaces a flat-70%
      draft written first, which West DISCOM disproved: its loans were 72%.
    - The loan's closing balance and average, and interest and finance cost on the average.
    - Closing and average equity, and RoE at 14% on the average (Reg. 31.3, quoted).
    - State sums.
  - **Binding `approval-dep-loan-fy27.json`: 36 / 66 exact.**
    - Equity and RoE: 19 / 19.
    - Every other check within its inputs' printed precision; the test bounds each kind:
      - balances carried from rounded figures, at most 2 paise;
      - interest, finance cost and depreciation, within their printed two-decimal rates —
        Central's finance cost implies 0.306% for "0.31%";
      - the State sums.
    - The FY2026-27 repayment is the order's printed depreciation, tied to Table 57.
  - **Finding `M3` (reviewer):** Table 65's FY2025-26 row "Equity addition admitted" prints
    East's and Central's proposed equity (226.34, 197.31).  The opening equity of FY2026-27 and
    Table 59's loans carry the lower 30% (181.25, 177.85).
  Nothing verified, nothing approved.

  **Increment 129 (2026-11-03): a third commission, a combined order — MPERC's working capital for
  the three MP DISCOMs; and checks now round as the rules declare.**
  - **The order:** MPERC's FY2026-27 order for East, West and Central DISCOMs (SHA-256
    `77ffe9d2…1afb`, the loader's `MPERC-DISCOMs-FY2026-27`).
  - **New folder `packages/order-reproductions/mperc-discoms-fy2026-27/`:** the manifest, the
    record (Table 61, 72 figures, 72 / 72 quotes verified), the binding and the findings.
  - **12 draft MPERC rules in `packages/arr-rules/mperc/tariff-2021.v1.json`,** from Regs. 23
    and 38 as the order quotes them:
    - wheeling: a month of O&M, wheeling receivables, the working capital;
    - supply: two months' receivables, a month of power purchase, the working capital less the
      deposits;
    - interest on each at the Base Rate + 350 bp (12.50%), and their sum;
    - State totals.
    The years the 2021 Regulations govern are not established here, so the rules carry no year
    bounds yet; the file says so.
  - **Binding `approval-iowc-fy27.json`: each DISCOM a category of one evaluation, the State the
    sum — 29 / 30 match.**
    - The State supply total adds unrounded rows (652.57 against the printed rows' 652.58).
    - West's negative supply working capital (−94.19) and its negative interest (−11.77),
      netted to 8.82, reproduce.
  - **Findings `M1`, `M2` (reviewer):**
    - **M1:** a negative working capital admitted and netted, where Reg. 38 as quoted does not
      say.  UPERC's practice was nil (increment 111).
    - **M2:** the inventory's GFA base is not printed.  21.07 implies about 15,802.50 for East,
      against Table 57's net 9,576.28.  The 80:20 split holds.
  - **Engine defect found and fixed — checks rounded half-to-even:**
    - Nine of the twelve check sites in `reproduce.py` used Decimal's default rounding, while all
      292 rules (UPERC 233, UERC 47, MPERC 12) round half-up and three sites already used it.  Central DISCOM's receivables
      (3,315.425) showed it.  Every site now rounds half-up (`_at`).
    - **Effect on earlier results, at exact half-paise only:**
      - NPCL's `reproduction.json`: 4 checks turn to "differs" — the three wheeling totals of
        increment 121 (451.705, printed 451.70) and Table 4-99's A5 vehicles average (0.705,
        printed 0.70) — and 1 turns to "match", Table 4-100's B2 buildings average.
      - Increment 121's allocation is now 24 / 31; the test bounds the wheeling total like the
        supply total.
      - Increment 123's UERC working capital is now 13 / 18: UPCL's claimed spares, 183.225,
        printed 183.22, now differ within precision.
  Nothing verified, nothing approved.

  **Increment 128 (2026-11-03): UERC — the FY2024-25 true-up gap carried into FY2026-27's ARR,
  across two regulations.**
  - **The record:** `order/figures-trueup-summary-fy2024-25.json` in the UERC folder holds 62
    figures (Tables 3.49, 3.50), 62 / 62 quotes verified.
  - **Eight more draft UERC rules (47 in all):**
    - in `tariff-2021.v1.json`: O&M after sharing (the norm less the consumers' signed third),
      the true-up ARR, the net ARR and the gap (with the deemed revenue on the excess loss);
    - a new `carrying.v1.json` for both regulations: carrying cost in a year (half a year on the
      addition), in the year of recovery (half a year on the opening), the closing balance, and
      the net impact after a correction.  The half-year conventions are the order's practice,
      read from its figures; the rule says so.
  - **Binding `trueup-carried-fy25-fy27.json` — one chain across FY2024-25, FY2025-26 and
    FY2026-27:** the true-up's gap from its heads, then carried to the 343.07 that Table 4.52
    puts in the ARR.
    - **From the printed gap (307.12),** the carrying chain is exact: 10 / 10 (18.53, 40.32,
      22.65; closings 325.65, 365.97, 388.62; 343.07).
    - **End to end from the heads:** the net ARR, 10,626.83, is exact.  O&M after sharing is
      893.467 against 893.46, inside its inputs' precision.  That paisa carried three years
      grows to 1.7 paise: 343.09 against 343.07.  The test bounds it by the growth factor.
  - **The UERC order now reproduces end to end through 47 draft rules:** the true-up year's
    sharing and gap, its carrying, and the ARR year's heads, net requirement and surplus.  Six
    findings (U1–U6) concern UPCL's claim.
  Nothing verified, nothing approved.

  **Increment 127 (2026-11-03): UERC's true-up of FY2024-25 — the distribution loss valued at the
  ABR, and controllable gains and losses shared.**
  - **The record:** `order/figures-trueup-sharing-fy2024-25.json` in the UERC folder holds 49
    figures (Tables 3.44–3.46, 3.48, para 3.3), 49 / 49 quotes verified.
  - **A second UERC rule file, `tariff-2021.v1.json`, for the 2021 Regulations, applying up to
    FY2024-25 (11 draft rules):**
    - the actual loss; sales at the approved loss; the sales lost;
    - the ABR, and the revenue lost at the ABR.  This is the order's method ("the earlier
      approach"), and the rule says it is not a quoted formula.
    - the variation on a controllable factor; the consumers' one-third (Reg. 14, quoted by the
      order); the licensee's balance; three totals.
    The year selection is tested: FY2024-25 picks these rules, FY2026-27 does not.
  - **Binding `trueup-sharing-fy25.json`:**
    - **The Commission's side is exact (20 / 20):**
      - the loss of 16.02% against 13.00%;
      - 14,957.27 MU at target; 518.41 MU lost; ABR 6.98; 361.85 lost;
      - every row of Table 3.48, consumers' and licensee's shares — O&M, distribution loss,
        working capital, the power purchase rebate and the late-payment surcharge.  The
        surcharge and rebate enter as negated income, with the reason.
      The licensee's two-thirds of the loss is Table 3.46's 241.23, the deemed revenue added in
      the true-up.
    - **Table 3.48's totals** differ from its rows by one or two paise (unrounded rows),
      bounded.
    - **UPCL's side**, at its own 13.25%, is within its printed precision.
  - **Finding `U6` (reviewer):** Table 3.46's row "Sales at Approved Loss of 13.00%" carries
    UPCL's sales at 13.25%, as UPCL's Table 3.44 says.  At 13.00% UPCL's own sales would show
    119.05 MU lost, not 76.06.
  - **For R-TU-2:** a second commission's sharing is now in the engine.  UERC 2021 passes
    one-third of a gain or a loss; UPERC 2025 passes two-thirds of a gain and one-third of a
    loss.  UERC values a loss variation at the ABR.  UPERC's valuation stays the reviewer's
    question (increment 122).
  Nothing verified, nothing approved.

  **Increment 126 (2026-11-03): UERC — UPCL's revenue requirement and surplus for FY2026-27,
  end to end.**
  - **The record:** `order/figures-arr-fy2026-27.json` in the UERC folder holds 38 figures
    (Tables 4.52, 4.54), 38 / 38 quotes verified.
  - **Three more draft UERC rules (28 in all):** the aggregate revenue requirement (eleven
    heads), the net requirement (less non-tariff income, plus the true-up gap and past claims),
    and the gap at the existing tariff.
  - **Binding `approval-arr-fy27.json`, the table's arithmetic:**
    - UPCL's claimed column: 3 / 4 exact; its gap is 2,183.93 against 2,183.94 printed.
    - The approved column: the printed heads add to 12,591.08 against 12,591.09 printed.
  - **End to end (the test):** the five heads the other UERC bindings compute — working capital
    interest, RoE, loan interest with finance charges, depreciation, O&M — are taken unrounded,
    with the order's recorded heads.  This gives the order's 12,591.09, net 12,489.54 and
    surplus 100.87 to the paisa.  The order evidently sums unrounded heads.
  - **Where the second commission stands:** UERC's FY2026-27 ARR is reproduced from its own
    figures through 28 draft rules.  The records are power purchase, transmission, smart-meter
    OPEX, bad debts, non-tariff income, the true-up gap and the revenue at existing tariff.  The
    engine needed no change for a second commission; increment 123 confirmed a binding can run
    without a workbook.  Five findings (U1–U5) concern UPCL's claim as the order reports it.
  Nothing verified, nothing approved.

  **Increment 125 (2026-11-03): UERC — O&M for UPCL, FY2026-27 (Reg. 84).**
  - **The record:** `order/figures-om-fy2026-27.json` in the UERC folder holds 50 figures
    (Tables 4.42–4.45, para 4.11.3 (b), Table 4.38's claimed opening GFA), 50 / 50 quotes
    verified.
  - **Eight more draft UERC rules (25 in all):**
    - employee: EMPn-1 × (1 + Gn) × (1 + CPI), its capitalisation, and net;
    - R&M: K × GFAn-1 × (1 + WPI);
    - A&G: A&Gn-1 × (1 + WPI), less capitalisation, plus the data-centre provision and the
      licence fee;
    - the O&M total.
    Capitalisation is the order's practice, which the quoted Regulation does not mention; the
    rule says so.
  - **Binding `approval-om-fy27.json`:**
    - **The approved side:** the total, 967.40, is exact.  Every approved line is within its
      inputs' printed precision: 6 of 11 checks exact, the rest by at most 1.3 paise.  The total
      is the annual O&M the working capital uses (increment 123).
    - **UPCL's claim** reproduces only with the figures its other numbers imply.
  - **Findings `U3`–`U5` (reviewer):**
    - **U3:** the claimed R&M (637.10) follows from UPCL's opening GFA of 11,814.94, not the
      11,682.50 printed in the same row (which gives 629.88).
    - **U4:** the A&G capitalised (11.72) follows from the 13.36% in the text, not the table's
      13.26%.
    - **U5:** UPCL's O&M is 1,237.35 in Table 4.45 but 1,221.50 in Table 4.52 and in its working
      capital, possibly its revised claim of 20.03.2026.
  Nothing verified, nothing approved.

  **Increment 124 (2026-11-03): UERC — GFA, depreciation, normative loan and interest for UPCL,
  FY2026-27.**
  - **The record:** `order/figures-loan-dep-fy2026-27.json` in the UERC folder holds 52 figures
    (Tables 4.38–4.41, 4.52), 52 / 52 quotes verified.
  - **Nine more draft UERC rules (17 in all), quoting Regs. 27 and 28 as the order does:**
    - closing GFA;
    - means of finance;
    - the depreciable base (GFA less grants), depreciation and the closing base;
    - the normative loan, closing (opening + drawal − repayment);
    - interest on the average of the opening loan and the closing loan less the year's drawal
      (no interest on the year's additions: the order's 4.9);
    - loan with finance charges, and total interest.
  - **The method:** depreciation is the order's interim one, FY2024-25's weighted-average rate
    on the depreciable opening GFA, for want of a fixed asset register.  The rule says this is
    not Reg. 28(4)'s class-by-class method.
  - **Binding `approval-loan-dep-fy27.json`: 5 / 17 exact.**  Every other check is within its
    inputs' printed precision, and the test bounds each one.  The order computes with rates
    that print rounded: depreciation implies 3.2208% and interest 10.066%, printed as 3.22%
    and 10.07%.  Three sums are off by a paisa.
  - **Ties checked by the test:**
    - the repayment is the depreciation allowed;
    - the drawal is the debt financed;
    - the equity financed is the RoE's addition (increment 123);
    - Table 4.38's opening GFA is Table 4.41's.
  - **Not checked:** UPCL's claimed interest (217.51).  It follows a method the order does not
    state, near the full average of opening and closing (217.61 at 10.07%).  Only its loan
    balance is checked (exact).
  Nothing verified, nothing approved.

  **Increment 123 (2026-11-03): a second commission — UERC's interest on working capital and
  return on equity for UPCL, FY2026-27.**
  - **Why:** the bindings so far were all UPERC / NPCL.  The second NPCL filing is still blocked
    on the operator.  So the same engine and binding shape is exercised on another commission's
    order from this session: UERC's of 31 March 2026 for UPCL, SHA-256 `1a929917…eb91`, the
    loader's `UERC-UPCL-FY2026-27`.
  - **New folder `packages/order-reproductions/uerc-upcl-fy2026-27/`:**
    - a manifest giving the order's URL and hash;
    - the record `order/figures-iowc-roe-fy2026-27.json`: 41 figures from Tables 4.50–4.52 and
      paras 4.13.1–4.13.4, 41 / 41 quotes verified;
    - the binding `bindings/approval-iowc-roe-fy27.json`, with no workbook (`reproduce_cells`
      runs on records alone);
    - `findings.json`.
  - **Eight draft UERC rules in `packages/arr-rules/uerc/tariff-2024.v1.json`, from FY2025-26:**
    the working capital components, requirement and interest (Reg. 33(2)), and RoE at 16.50% on
    the opening equity with the closing equity (Reg. 26).  The excerpts are the order's own
    quotation of the Regulations, which are not in this session, and say so.  Nothing is
    verified.
  - **14 / 18 match.**  The approved side reproduces:
    - O&M 967.40 / 12 = 80.62; spares 15% = 145.11;
    - two months of 12,590.41 = 2,098.40; the shortfall at 99.15% collection = 107.02;
    - interest 12.38% = 193.58;
    - RoE 16.50% × 784.01 = 129.36; UPCL's claimed 329.19 likewise.
    Two differences are rounding, bounded by the test: the requirement 1,563.67 against 1,563.66,
    and UPCL's closing equity by 0.01.
  - **Findings `U1`, `U2` (reviewer):**
    - **U1:** UPCL's claimed interest (210.62, Tables 4.50 and 4.52) is not its 12.45% on its
      1,678.73, which gives 209.00.
    - **U2:** the one month of power purchase (867.48) matches no printed annual total, so it
      enters as a record.
  - **Seen in passing:** UERC values the distribution-loss variation at the ABR and shares it
    two-thirds / one-third (p.167).  This is one commission's valuation, a reference for the
    question increment 122 left to the reviewer, not UPERC's rule.
  Nothing verified, nothing approved.

  **Increment 122 (2026-11-03): R-TU-2 — sharing of controllable gains and losses under the 2025
  Regulations.**
  - **The clause:** Regulation 11 (p.15 of the committed English text), with 33.3 for O&M.
    - A gain on each O&M component or on distribution loss: two-thirds passed on in the ARR,
      the rest kept by the licensee.
    - A loss: one-third passed on, the rest absorbed.
    The rule file cites the page and quotes the clause; `verified` stays false.
  - **Six new draft rules in `sharing.v1.json`, applying from FY2025-26:**
    - the variation (normative less actual);
    - the part passed on;
    - the component allowed after sharing;
    - the part kept or absorbed;
    - two totals.
    Each per-component rule carries constructed worked examples of both branches (labelled as
    constructed, not a filing); `check_all` runs them.  FY2024-25, under the 2019 Regulations,
    does not select them; it keeps the lower of normative and actual.
  - **Illustration on the APR of FY2025-26 (Table 5-26, recorded in
    `order/figures-apr-om-fy2025-26.json`, 12 / 12 quotes verified):** NPCL's estimate is taken
    as if it were the audited actual, against the Commission's computed norm.  This is the
    arithmetic of the coming true-up, not a figure any order printed.
    - Employee: 11.06 over the norm; 3.69 passed on, 7.37 absorbed; 88.26 allowed.
    - A&G: no variation.
    - R&M: 2.12 over; 98.85 allowed.
    - Total: 215.85 allowed against 224.64 estimated; 8.79 absorbed.
  - **Not built:** the distribution-loss gain.  Regulation 11 shares it the same way but does not
    say how a loss variation is valued in rupees.  That is for the reviewer.
  - **Docs correction:** increments 120 and 121 put the UPERC rule count at 231 and 233.  The
    true counts were 225 and 227; with this increment it is 233.
  Nothing verified, nothing approved.

  **Increment 121 (2026-11-03): the order's wheeling and retail supply ARR (Table 9-4).**
  - **The record:** `order/figures-allocation-fy2026-27.json` holds 62 figures (Table 9-4's
    shares and amounts, four lines of Table 6-81), 62 / 62 quotes verified.
  - **Two new draft rules in `allocation.v1.json`:** the wheeling ARR and the supply ARR, each
    the sum of the items' shares.
  - **Engine:** an order input may be negated (`negate`, with its reason).  The order prints
    non-tariff income as a "Less:" line in one table and in brackets in another.
  - **Binding `approval-allocation-fy27.json`: 27 / 31 match.**  Each approved item comes from
    the record where the order approves it: Tables 6-81, 6-82 and 6-72, the O&M, depreciation,
    RoE and tax tables, and the GNA charges.  Each is split by the 2025 Regulations' matrix.
    - The totals give 451.70 (Table 9-5's wheeling ARR) and 3,059.635 against 3,059.63 (Table
      9-6's supply ARR).
    - R&M (99.936 against 99.93) and other interest (22.347 against 22.34) are within their
      inputs' printed precision; the test bounds each.
  - **Ties checked by the test:**
    - the two printed totals add to the net ARR, 3,511.33;
    - the interest allocated is Table 6-72's 110.43, not Table 6-81's 110.80 — new evidence
      for A61's reading;
    - every line's shares add to 100%.
  Nothing verified, nothing approved.

  **Increment 120 (2026-11-03): open access charges and the cross-subsidy surcharge for FY2026-27.**
  - **The record:** `order/figures-open-access-fy2026-27.json` holds 159 figures (Tables 9-5 to
    9-14, Table 6-82's APPC and ACoS, NPCL's own surcharge table on p.316), 159 / 159 quotes
    verified.
  - **Six new draft rules in `open-access.v1.json`:**
    - D by voltage;
    - the average cost of supply for 66 kV;
    - T − C;
    - the cap at 20% of the cost of supply, and the surcharge capped never negative;
    - the lower of last year's approval and this year's.
    The existing cap-on-tariff rule (NPCL's F33) stays, beside the order's.
  - **Engine:** a binding's order input may now add (`plus`) and take away (`minus`) several
    recorded figures.
  - **Binding `approval-oa-fy27.json`: 69 / 71 match.**
    - DC 0.23, TC 0.51, PC 0.58, WC 1.03.
    - D 1.32 / 2.35.
    - The APPC 4.91 from Table 6-82.  Its fixed part, 1.21, reproduces as DIL's and the
      medium-term sources' fixed charges over the ex-bus energy.  This is an inference; the
      order does not state it.
    - The cost of supply 6.59, 7.65, 7.75; the 66 kV average 7.12.
    - Every surcharge computed, capped and approved, and NPCL's four claims (p.316).
    Two differ, both bounded by the test:
    - the LV cost of supply prints the ACoS 7.98 where the formula gives 8.01 (A80);
    - HV-1 above 11 kV's T − C is 2.54 against 2.55 (within T's printed precision).
  - **Findings:**
    - **A80 (reviewer):** three readings of the 20% cap, and the LV row.  None changes
      FY2026-27's approvals.
    - **A81 (petitioner):** NPCL's claims are uncapped while its F33 proposes 1.21.  F33 types
      last year's HV-1 approval as 1.86 where the order says 1.40.
    - **A51** gains the order's reading.
  Nothing verified, nothing approved.

  **Increment 119 (2026-11-03): the Renewable Consumption Obligation for FY2026-27.**
  - **The record:** `order/figures-rco-fy2026-27.json` holds 25 figures (Tables 6-31, 6-32),
    25 / 25 quotes verified.
  - **Four new draft RCO rules in `rpo.v1.json`:** each component's share of the energy
    supplied, and the renewable total and its share.
  - **Binding `approval-rco-fy27.json`: 7 / 7 exact.**  The renewable total is 1,137.80 MU,
    24.06% against the 35.95% target.
  - **Ties checked by the test:** the energy supplied is the approved requirement at NPCL's bus;
    the source columns add to it within rounding.
  - **Not computed:** a shortfall against the target.  The order states only the 24.06%
    compliance (para 6.5.48).
  Nothing verified, nothing approved.

  **Increment 118 (2026-11-03): the true-up's power purchase by source.**
  - **The record:** `order/figures-trueup-pp-sources-fy2024-25.json` holds 78 figures (Tables
    4-42 to 4-45), 78 / 78 quotes verified.
  - **The rules:** the power-plan rules now apply in every year, not only projections.
  - **Binding `approval-trueup-pp-sources-fy25.json`, with the ARR year's rules and the existing
    billed and rebate rules:**
    - DIL, TPTCL (JITPL), JITPL and the exchange: energy billed through both losses to NPCL's
      bus, and the net cost (fixed and variable less the rebate);
    - nine renewable amounts from units and rate.
    9 / 25 match exactly.  The test bounds every difference by the printed precision of its
    inputs, comparing the printed figure with the unrounded result.  The order's own JITPL net
    (359.30) is a unit below its printed parts.
  - **Ties checked by the test:** each source's energy at the bus and net cost are Table 4-52's
    line.
  Nothing verified, nothing approved.

  **Increment 117 (2026-11-03): NPCL's APR power purchase estimate checked — the line the
  Commission took provisionally.**
  - **Table 5-18 read by word position (pp.179–180):** 49 rows, wrapped labels joined.
  - **Engine:** a source table now names its own sides (`sides`: here the original approval
    against NPCL's estimate) and its row-code pattern.  A decision is computed only where an
    approval is set against a claim.  Panel 06d shows the named sides.
  - **NPCL's estimate holds its own arithmetic throughout (78 / 79 overall):**
    - every MU × rate, every group and the MU total;
    - the additional claims A–H, including the 118.55 supplement;
    - its sub-total is the format's plus that supplement (A72).
  - **A79 (petitioner):** the side restating the order of 22.11.2025 prints power purchase 2.47
    below its own rows (and the format's 2,192.18), and transmission 2.47 above the format's
    440.03.  The total agrees; the table does not say why.
  Nothing verified, nothing approved.

  **Increment 116 (2026-11-03): the true-up's energy balance — where the 1.32 MU disallowed
  comes from.**
  - **The record:** `order/figures-energy-balance-fy2024-25.json` holds 40 figures (Table 4-19,
    three columns; para 4.3.14), 40 / 40 quotes verified.
  - **The rules:** the five energy-balance rules of increment 115 now apply in every year.  They
    are the order's layout, not a 2025-only clause.
  - **Binding `approval-energy-balance-fy25.json`:**
    - the original approval reproduces 7 / 7;
    - the claim and the true-up are within the printed precision of the inter-state loss and of
      the energy delivered at the bus.
  - **Ties checked by the test:** the computed claimed total less the approved total is 1.32 MU.
    That is the excess the order disallows (para 4.3.14) and prices at 2.57 (A70).  The
    power-purchase decision's one computed line now reproduces from its source.
  Nothing verified, nothing approved.

  **Increment 115 (2026-11-03): the ARR year's energy balance, claimed and approved.**
  - **The record:** `order/figures-energy-balance-fy2026-27.json` holds 26 figures (Table 6-9),
    26 / 26 quotes verified.
  - **Five new draft energy-balance rules (from FY2025-26), following the order's layout:**
    - net requirement at NPCL's bus;
    - grossed up for the intra-state loss;
    - less the sources at the STU bus;
    - grossed up for the inter-state loss;
    - the total.
    Two of the order's printed formula labels are slips; its figures follow the arithmetic.
  - **Binding `approval-energy-balance-fy27.json`, both columns:** 9 / 14 match, the rest within
    the printed precision of the losses.  NPCL's unrounded sales and intra-state loss are fed
    from its own Energy Balance sheet.
  - **Ties checked by the test:** the approved requirement at the bus is Table 6-35's import
    (4,729.49).
  - **A78 (reviewer):** the GNA table takes 5,066.34 MU at the ISTS, which is NPCL's claimed
    total; the approved balance gives 5,043.87.  This is a question: T-GNA's derivation is not
    established.
  Nothing verified, nothing approved.

  **Increment 114 (2026-11-03): the ARR year's power purchase reproduced source by source.**
  - **The record:** `order/figures-pp-fy2026-27.json` holds 154 figures (Tables 6-26 to 6-28,
    6-31, 6-33 and 6-34, para 6.5.51), 154 / 154 quotes verified.
  - **Units:** INR per MW-month, and `hour` (energy per power, so MW × hours is energy).
  - **New draft rules `power-plan.v1.json` (22):**
    - energy from contracted capacity × PLF × 8,760 hours;
    - the inter- and intra-state losses to NPCL's periphery;
    - fixed and energy charges at the approved rates;
    - the landed cost per unit, and totals;
    - GNA charges from the base cost.
  - **Binding `approval-pp-fy27.json`: 53 / 77 match.**  JITPL matches to the last place, and
    GNA exactly (215.00).  The test bounds every difference by that output's own input
    precision:
    - the four 25 MW contracts are within the rounding of their printed rates;
    - losses are printed to two places of a percent;
    - GNIDA's small cost is printed to two places.
  - **Ties checked by the test:** the parts against Table 6-35's lines — DIL 580.74, medium term
    780.04, renewables 385.20, exchange 576.59 MU and 288.44, GNA and T-GNA 257.21.
  - **Still read:** the short-term contracts' rates and DIL's charges come from orders not in
    this session.  T-GNA's 42.21 does not follow from the figures printed.
  Nothing verified, nothing approved.

  **Increment 113 (2026-11-02): the APR's depreciation reproduced class by class between two
  printed balances.**
  - **The problem:** Table 5-40 prints only the APR's part totals.  The FY2025-26 per-class
    figures are not printed anywhere.
  - **The approach:** each class opens at the true-up's closing (Tables 4-99, 4-100) and closes
    at the ARR year's opening (Tables 6-62 to 6-64).  The year's deduction is their difference;
    Part C's additions are the ARR year's opening of Part C.  The rates are the ARR year's class
    rates.
  - **Binding `approval-apr-depreciation-fy26.json`: 5 / 5 exact** — Part A 54.05, B 54.09,
    C 9.81, gross 117.95, net 87.01.  This confirms the order applied the 2025 Regulations'
    class rates to FY2025-26.
  - **Engine:**
    - a binding may draw on several records under aliases (`rates: {alias: path}`, keys
      `alias:key`) — `load_binding_rates`, now used by `reproduce_formats.py`;
    - an input may be one recorded figure less another (`{"rate": a, "minus": b}`, same unit
      only), so a derived difference is never typed.
    A synthetic test covers both, including the refusal of mixed units.
  - **The explanations:** the APR's depreciation moves to reproduced; 22 of the 36 changed lines
    are now reproduced.
  Nothing verified, nothing approved.

  **Increment 112 (2026-11-02): the true-up's bad debts and non-tariff income reproduced.**
  - **The record:** `order/figures-trueup-nti-fy2024-25.json` holds 16 figures (Tables 4-113,
    4-114, 4-117, 4-118), 16 / 16 quotes verified.  Allowing whole numbers for the one figure
    printed without decimals first swallowed the next rows' serial numbers; the count checks
    caught all six, and whole numbers are now allowed for that figure only.
  - **New draft rules:**
    - `uperc.nti.*`: the treasury income excluded is the lower of the shareholders' fund at the
      RBI bank rate and the interest earned; non-tariff income is the audited figure less that
      and the other exclusions;
    - `uperc.baddebts.trueup_allowed`: NPCL's own provisioning ratio on the approved revenue net
      of electricity duty.
    Both follow the order's stated method, for the true-up years only.
  - **Binding `approval-trueup-nti-fy25.json`: 4 / 5 match** — bad debts 10.79, treasury
    excluded 37.99, non-tariff income 12.38.  The fund's income is 39.05 against 39.07; the order
    prints the average investment in whole crore.
  - **The test** also proves that the stated other exclusions (0.41) are the record's three rows.
  - **The explanations:** two true-up lines move from read to reproduced, so 21 of the 36
    changed lines are now reproduced.
  Nothing verified, nothing approved.

  **Increment 111 (2026-11-02): the ARR year's working capital reproduced — nil against the
  surplus.**
  - **The record:** `order/figures-wc-fy2026-27.json` holds 17 figures (Table 6-69 and the O&M
    and open-access lines of Table 6-81), 17 / 17 quotes verified.  The checker refused a header
    I had copied from the true-up's summary; Table 6-81 heads its rows "S. No.".
  - **Binding `approval-wc-fy27.json`: 5 / 6 match**, with the same rules as NPCL's F27:
    - net O&M 195.34;
    - one month 16.28;
    - receivables 400.23: 1.5 months of revenue with the open-access charges, NPCL's projection
      unrounded, which the order adopts;
    - total 62.30;
    - interest nil.
    The net is −11.04 against the printed −11.03, consistent with the order's surplus unrounded.
  - **Ties checked by the test:** the surplus set against working capital is the APR's closing
    (73.34).
  - **A62 and the explanations** now point at the binding; the ARR year's interest line is
    reproduced in full.
  Nothing verified, nothing approved.

  **Increment 110 (2026-11-02): fixed charges — why they cannot be reproduced, and a question for
  NPCL.**
  - **The record:** `order/figures-fixed-charges-fy2026-27.json` holds 19 fixed / demand charges
    from the rate schedule (pp.362–387) and General Provision 6's billable-demand floor (p.354),
    20 / 20 quotes verified.
  - **Units:** kVA (apparent power), MVA, and per kW / per kVA per month.  A per-kVA charge times
    kW is a dimension error.
  - **Analysis, not a reproduction.**  NPCL's fixed charges are 80.4% of the schedule's rates at
    full contracted load (485.98 against 604.74).  Every category is at or above the 75% floor of
    billable demand, from 75.3% to 93.8%.  So the charges are billed on a demand ESR-3 does not
    carry, and they cannot be reproduced from the filing.
  - **A77 (petitioner):** LMV-2 is the exception, at 58–66%, which is 4.71 below the floor.
    Whether its consumers have demand-recording meters, or whether column E is connected load,
    the filing does not say.  The query asks for the billable demand by category.
  - **The plan changes:** "fixed and demand charges" leaves the engineering list and waits on
    NPCL's billable demand.
  Nothing verified, nothing approved.

  **Increment 109 (2026-11-02): every line the Commission changed, with its reason, enforced.**
  - **`order/explanations.json`:** for each changed line of the true-up, APR and ARR-year summary
    tables, it records:
    - the order's reason, with its pages;
    - the finding that sets the reason out;
    - the binding that reproduces the line, where one exists;
    - a status: reproduced, read, refused, deferred or provisional;
    - where a line has several causes, its parts.
  - **`decisions.explain`:**
    - joins the reasons to the rows read from the order;
    - lists any changed line without a reason, and any reason for a line that did not change;
    - checks each line's parts;
    - adds the effects (a deduction moves the net the other way) against the net ARR's decision.
  - **Results: 36 lines** — 19 reproduced, 11 read, 5 refused, 1 provisional.  None is
    unexplained and no reason is stale.
    - The effects add to −123.36 against −123.38 and 92.65 against 92.64, within the rounding of
      the printed lines.
    - The ARR year adds to 29.51 exactly, once the summary's misprinted interest is taken as
      approved (A61).
  - **A76 (petitioner):** the ARR year's non-tariff income is the true-up's approved 12.38,
    NPCL's other business within it.  This was the one reason no finding held.
  - **Panel 06d** shows each line's reason, status, pages and finding.
  Nothing verified, nothing approved.

  **Increment 108 (2026-11-02): the regulatory discount computed; NPCL's revenue projection is
  the order's.**
  - **New draft rule `uperc.revenue.regulatory_discount`:** 10% of the fixed / demand and energy
    charges, under General Provision 21 of the rate schedule (p.360).  It takes an exclusion for
    anything in the fixed column that is not a demand charge.
  - **Results:** NPCL's ESR-3 discount for FY2025-26 (−322.6380) and FY2026-27 (−357.0702)
    reproduces exactly at four places.
  - **The one apparent difference was mine, not NPCL's.**  At first the rule took 10% of the
    whole fixed column and missed by 0.0039 and 0.0052.  The difference sat entirely in the
    LMV-11 public charging stations, which have no demand charge ("Demand Charge –", p.381).
    NPCL discounts only their energy charge, as the schedule implies.  What their fixed column
    holds (the excess-demand penalty) is inferred.
  - **Row-table `shared` inputs** may now sum named cells (`cells`).  A reason is required, and
    the test proves the reader refuses a sum without one.
  - **The order's revenue at approved tariff is NPCL's ESR-3:** 3,549.11 without the discount,
    3,192.04 with it (ARR!M13, M15; para 8.1.7).
  Nothing verified, nothing approved.

  **Increment 107 (2026-11-02): the tariff design summary — ABR, ACoS and cross-subsidy levels.**
  - **New draft rules `packages/arr-rules/uperc/tariff-design.v1.json`:**
    - ABR by category and overall;
    - ACoS = ARR ÷ sales;
    - cross-subsidy level = ABR ÷ ACoS − 1.
    These are the definitions as the order's Table 8-6 applies them; unverified.
  - **The record:** `order/figures-tariff-fy2026-27.json` holds 76 figures (Tables 8-4 to 8-7),
    76 / 76 quotes verified.
  - **Binding `approval-tariff-fy27.json`: 31 / 41 match.**  The ACoS (7.98), the overall ABR
    (7.25), its −9.09% and the large categories match.  The ten differences are small
    categories, whose revenue the order prints to two places in crore.  The test bounds each
    difference by its own inputs' precision, not by a blanket tolerance.
  - **A75 (reviewer):** Table 8-7's monthly sales for FPPAS are apportioned by NPCL's monthly
    power purchase units.  That series is in no format of the package: a scan of every row and
    column of twelve figures found none proportional.  The monthly sales cannot be checked here.
    The months do add to 4,399.84.
  Nothing verified, nothing approved.

  **Increment 106 (2026-11-02): the revenue gap (surplus) and its carrying cost, one convention
  across NPCL's format and the order.**
  - **New draft rules `packages/arr-rules/uperc/gap.v1.json`:**
    - carrying cost = (opening + half the year's addition) × rate;
    - closing = opening + addition + carrying.
    The rate is an input because NPCL's format and the order choose it differently.
  - **The record:** `order/figures-gap-fy2026-27.json` holds 34 figures (Tables 7-1, 8-4, 5-32
    and 6-69), 34 / 34 quotes verified.
  - **Binding `approval-gap.json`: 13 / 14** (the other is a rounding unit).
    - NPCL's format: ARR J/L/M rows 62–63, all six cells.
    - The order: five carrying costs.  In the APR and the ARR year the order first sets the
      surplus against that year's working capital, and carries what remains (Tables 5-32, 6-69,
      8-4: "Opening … after WC adjustment").
  - **A74 (reviewer):** the surplus is carried at the working-capital rate in FY2024-25 and
    FY2026-27, but at an unexplained 4.86% in FY2025-26.  At 10.75% the surplus brought into
    FY2026-27 would be 13.52 larger.  This is a question, not an established error.
  - **Ties checked by the test:**
    - the surplus funds the working capital first;
    - the closings add the carrying cost to the unadjusted opening (I = A + E + H);
    - each year opens on the last one's closing.
  Nothing verified, nothing approved.

  **Increment 105 (2026-11-02): the APR of FY2025-26 reproduced; its +92.64 explained line by
  line.**
  - **The record:** `order/figures-apr-fy2025-26.json` holds 57 figures, 57 / 57 quotes verified.
    They come from Tables 5-17 to 5-48 (the Commission's own APR computations) and the true-up
    closings the APR carries.
  - **Binding `approval-apr-fy26.json`: 11 / 13 match, the other two one unit.**  It uses the
    MYT 2025 rules:
    - loan, equity, RoE and tax, opening from the true-up's approved closings;
    - NPCL's loan rate unrounded (F25 H14), which the order allows as claimed and prints rounded;
    - working capital: the revenue surplus NPCL holds at the beginning of the year (470.67, the
      true-up's closing, Table 7-1) is set against the requirement, so interest is nil;
    - R&M at 5% of a base the order does not print.  1,073.20 + 889.53 gives 98.14 exactly.
  - **A72 (petitioner), the +92.64:**
    - +118.55 is NPCL's own supplementary claim for DIL's true-up (29.04.2026), taken
      provisionally.  The order's "claimed" column is the petition as filed.
    - O&M −15.45: no growth factor, R&M on the Commission's GFA, provisions refused.
    - Interest −1.99: the working-capital interest is nil against the surplus.
    - Depreciation −3.08, RoE −2.05 and tax −0.68: the true-up's closings carried forward.
    - Non-tariff income −2.86: the true-up's approved figure.
    - Other business +0.20.
  - **A73 (reviewer):** the inferred R&M base leaves out the 3.92 of non-depreciable land, where
    the ARR year's R&M takes Part A whole.  Table 6-49 also mislabels FY2026-27's opening.  These
    are questions; the base is inferred.
  - **Ties checked by the test:**
    - the APR opens on the true-up's closings;
    - its employee and A&G figures are the FY2025-26 steps of the ARR year's chain;
    - its Part B depreciation is the ARR year's.
  - **All three proceedings' decisions are now explained line by line:** true-up −123.38, APR
    +92.64, ARR year +29.51.
  Nothing verified, nothing approved.

  **Increment 104 (2026-11-02): the true-up's power purchase decision, line by line; every line
  of the true-up now has its reason.**
  - **Table 4-52 read by word position (pp. 88–89).**  Its source names are centred on the lines
    around their figures ("Add. Coal for FY23 (90%" / figures / "Booked in FY23)").
    `rows_by_position` takes a `label_span`: a line with no figures within that many points of a
    figure line joins that row's label; a section heading farther away joins none.  The spec
    names each table's own anchor words (`anchor_words`).  Table 6-35 reads exactly as before.
  - **Results:** 36 rows.  The table's own arithmetic holds on both sides (44 / 44), and the
    claimed side is NPCL's format (ARR!J20:J24).  `source_decisions` lists the lines a decision
    changes; they are shown in panel 06d.
  - **The five lines (A70):**
    - TPTCL incentive −1.02 and change in law FY24 −4.98: billed in FY2025-26, so deferred to
      that year's true-up.
    - Two carrying costs, −3.37 and −2.30: computed on the months from each bill.  The months are
      not printed, so these are read, not reproduced.
    - Excess energy −0.34: 1.32 MU at 2.57.  Reproduced with four new draft rules
      (`uperc.pp.excess.*`, the order's stated method), binding
      `approval-trueup-power-purchase-fy25.json`: rate and amount match; Table 4-51's totals are
      one unit off their rows.
  - **Refused in principle (A70):** the contingency reserve (para 4.18.1) and efficiency gains
    (para 4.3.15).  The 0.04 of "other business" income is within the order's non-tariff income
    (para 4.16.20).
  - **Every line of the true-up's −123.38 now has its reason** (A65, A67, A68, A70).
  - **A71 (reviewer):** the draft contingency rule computes NPCL's claim, which the Commission
    always refuses.  The rule is not changed.
  Nothing verified, nothing approved.

  **Increment 103 (2026-11-02): the true-up's depreciation reproduced class by class.**
  - **The record:** `order/figures-trueup-depreciation-fy2024-25.json` holds 205 figures
    (Tables 4-98 to 4-101, pp. 142–144): every class of Parts A and B with opening, addition,
    deduction, closing, average, rate and allowable; the summary claimed and approved.
    205 / 205 quotes verified.
  - **Binding `approval-trueup-depreciation-fy25.json`: 68 / 76 match.**  All 24 classes'
    depreciation, the gross 95.03 and the net 69.97 match, with the same draft rules as NPCL's
    F24.  Six of the eight differences are averages at a half-paisa and one is Part A's total,
    printed as the sum of rounded classes.
  - **A68 (petitioner), the −4.78 explained against NPCL's own workings (Annexure-21):**
    - Part A −2.89: almost all of it is the opening gross block from the remand order of
      17.06.2026 (−59.52).
    - Part B −0.51: openings −21.74, additions +14.59 (land moved into the year's additions).
    - Depreciation on consumer contribution, taken "from Fixed Asset Register": 25.06 against
      23.67.  Not reproducible; no class table is given.
  - **A69 (reviewer), two questions about the order, not established errors:**
    - Part B Lines & Cables does not add (573.03 against 573.00).
    - Part A sets 3.92 of land apart as non-depreciable while depreciating the Land class on its
      whole 123.84.
  - **Ties checked by the test:** the approved additions are the funding table's 317.18, and the
    net depreciation is the loan repayment.
  - **Still to reproduce in the true-up:** power purchase −11.99, contingency −5.61, efficiency
    gains −2.58.
  Nothing verified, nothing approved.

  **Increment 102 (2026-11-02): the true-up's capital, loan, equity and working capital; two
  draft rules depart from the Commission.**
  - **The record:** `order/figures-trueup-capital-fy2024-25.json` holds 38 figures (Tables 4-71,
    4-94, 4-103, 4-105, 4-108, 4-110, 4-112).
  - **Two extraction errors, caught by reading the values, not by the quote checker.**
    - A pattern for "the row's last figure" took the next paragraph's number ("4.8.") as a
      figure.  Figures now need two decimals.
    - It found NPCL's submitted table before the approved one on the same page.  Searches now
      start at the approved table's title.
    Both wrong quotes really were on the page, so the checker could not catch either; the
    values had to be read.  38 / 38 verified after the fix.
  - **Binding `approval-trueup-capital-fy25.json`: 9 / 16 match.**  Working capital reproduces
    (interest 0.69).  The other differences are one unit of rounding, except one draft rule:
  - **A66 (reviewer), two draft rules follow NPCL where the order does not:**
    - Equity deleted on retired assets: WDV 1.85 against the order's 30 % of the gross retired,
      2.03, with the debt deletion nil (para 4.9.8).  The difference carries into closing
      equity (+0.17) and RoE (+0.01).
    - Working-capital receivables in the true-up: actual receivables against 1.5 months of
      approved revenue, 329.33.  Fed here as the order's figure.
    The drafts are not changed to fit the order: verifying the 2019 clauses is the reviewer's.
  - **A67 (petitioner):** interest −2.07 (loan +1.06, working capital −3.12), RoE −2.36, tax
    −0.79 and bad debts −0.59 explained.  I first attributed non-tariff income's +1.72 to the
    treasury deduction; that was not established, and the finding now says so.
  - **Still to reproduce in the true-up:** power purchase −11.99, depreciation −4.78,
    contingency −5.61, efficiency gains −2.58.
  Nothing verified, nothing approved.

  **Increment 101 (2026-11-02): the true-up's O&M cut reproduced from the monthly indices.**
  The true-up year's decision (−123.38) is mostly O&M (−90.91), under the 2019 Regulations.
  - **The record:** `order/figures-trueup-om-fy2024-25.json` holds 69 figures: the CPI and WPI
    month by month for two years (Tables 4-68, 4-69), the FY2023-24 norms, the FY2024-25
    normative, actual and approved (4-70, 4-71).  69 / 69 quotes and headers verified.
  - **New draft rule `uperc.om.trueup_allowed`:** the lower of normative and actual, citing the
    order's statement of the method (para 4.6.64).  The 2019 Regulations are not in this session.
  - **Engine:** an order figure printed in another unit than the result (3.38 % against a
    fraction) is compared in the order's unit.
  - **Binding `approval-trueup-om-fy25.json`: 8 / 13 match.**
    - The CPI and WPI averages and their increases (3.38 %, 2.27 %) come out exactly from the
      monthly indices.
    - R&M matches exactly.
    - Employee and A&G are one unit off: the order prints its FY2023-24 bases rounded.
    - The lower-of picks the normative value in every component, as the order does.
  - **A65 (petitioner):**
    - employee −57.78: the norm 37.64 against actual 95.42, 2.5 times the norm;
    - A&G −14.81; R&M −9.31;
    - SOP-compliance 9.01 not allowed separately.
    The norm's FY2023-24 base comes from the Commission's order of 17.06.2026 on the APTEL
    remand, which is not in this session.
  Nothing verified, nothing approved.

  **Increment 100 (2026-11-02): the power purchase decision, read by word position.**
  - **Why position:** Table 6-35 (pp.242–243) has blank cells.  A source NPCL claimed but the
    Commission did not approve prints only claimed figures, and the reverse, so the text order
    cannot say which side a lone triple belongs to.  Read that way, it had put C.8–C.21 on the
    claimed side; they are approved-only.
  - **The reader:** `decisions.rows_by_position` reads a page's words with their coordinates.
    It groups them into lines, opens a row with its code (A, B.1, …) and gives each figure to
    the nearest column anchor, taken from the page's own header words.  A dash inside a label
    ("TPTCL - PPGCL") is text; two figures on one anchor is an error.
  - **The checks:** `decisions.check_sources` checks the table's own arithmetic per side:
    amount = MU × rate ÷ 10 within the printed rounding, and every subtotal against its parts.
  - **Result: 51 rows; 81 / 84 arithmetic checks.  The approved side holds throughout.**  The
    three exceptions are claimed-side slips by the order (A63, reviewer):
    - the short-term subtotal is printed 810.23, where the rows add to 810.52 and NPCL's PPC
      FY 27 has 810.53;
    - hence F is 0.30 off its parts;
    - the JITPL claimed rate is printed 5.62 where its amount implies 5.61.
    The claimed power-purchase total is 2,448.32 against the format's 2,448.33; transmission
    446.36 matches.
  - **A64 (petitioner), the decision explained:**
    - DIL +46.35: its trued-up FY2023-24 tariff, landed at 4.89 against 4.50 (para 6.5.38);
    - short-term −79.14: NPCL's trader and exchange blocks replaced by the agreements the
      Commission approved and 617.63 MU from the exchange at 4.67 (para 6.5.51);
    - renewable −0.32;
    - the IEX sale and DSM not allowed: +62.16;
    - UPPTCL +35.38 at its own tariff order.
    The table's 576.59 MU and 5.00 Rs/kWh for the exchange are the same purchase at NPCL's
    periphery: 617.63 × (1 − 3.58 %) × (1 − 3.18 %) = 576.58.  I checked this before calling it
    an inconsistency; it is not one.
  - **Shown in panel 06d.**
  - **The ARR year's +29.51 is now explained line by line** (A60, A62, A64), and the order's
    own errors are recorded (A61, A63).
  Nothing verified, nothing approved.

  **Increment 99 (2026-11-02): the Commission's depreciation reproduced class by class.**
  - **The record:** `order/figures-depreciation-fy2026-27.json` holds 183 figures.  These are
    36 asset classes in three parts (Tables 6-62 to 6-64) with opening, deduction or addition,
    closing, rate and allowable depreciation, plus the net (6-65).  They are read row by row
    with the decisions module's serial-number reader, which now accepts a figure printed with %.
    The totals rows print no rate.  183 / 183 quotes and headers are found on their pages.
  - **Engine:** a record figure of zero may be printed as "-", and only so.
  - **Binding `approval-depreciation-fy27.json`, using the same depreciation rules as NPCL's
    F24: 69 / 77 match, and all 36 classes' depreciation matches.**  The 8 others are closings
    and part totals within two units of the last place: the order prints its GFA rounded and
    computes from unrounded balances (619.92 − 2.27 = 617.65 against the printed 617.64).  The
    net therefore comes to 103.82 against 103.80.
  - **A62 extended:** depreciation −2.95 is Part A −2.91 (the approved opening GFA), Part B
    −0.26 and Part C +0.21 (the full 474.13 of approved additions).
  - **Where this leaves the ARR year's decision (+29.51):**
    - reproduced and explained: O&M −18.37 (A60), capital, interest, tax and depreciation (A62);
    - left: power purchase and transmission (+64.16), the Commission's own procurement plan,
      and non-tariff income (+2.09) and other business (−0.98).
  Nothing verified, nothing approved.

  **Increment 98 (2026-11-02): the capital and interest approval reproduced, and an error found
  in the order.**
  - **The record:** `order/figures-capital-fy2026-27.json` holds 28 figures with page, quote
    and column header (Tables 6-58, 6-67, 6-70, 6-72, 6-74, 6-76): 28 / 28 found on their pages.
  - **Binding `approval-capital-fy27.json`, using the capital, MYT 2025 and income-tax draft
    rules that reproduce NPCL's claim: 13 / 14 match.**
    - funding: to fund 409.84, debt 286.89, equity 122.95, retirement deletions 2.18 and 4.50;
    - normative loan: closing 961.61, interest 85.60;
    - equity: closing 814.43, RoE 113.28;
    - tax 38.10; security-deposit interest 20.51 at the 5.50 % allowed.
    The loan rate is NPCL's own (F25 I14, 9.8262 %), because the order "considered the rate of
    interest as claimed" (para 6.10.5).  At the 9.83 % it prints, the result would be 85.63, not
    85.60.  The one difference is the average equity, 755.21 against 755.20, from the order's
    rounded opening equity.
  - **A62 (petitioner), the decisions explained:**
    - RoE −2.49 = the APR's approved opening equity (−2.05) and 30 % of the 19.56 of capex
      disallowed, metering/AMI and cyber resilience (−0.44);
    - interest −8.88 = loan +1.72 (a higher approved opening loan), security deposit −3.73
      (5.50 % against 6.50 %), working capital −6.88 (the 73.34 opening surplus leaves none to
      fund);
    - tax −0.84 follows RoE.
  - **The order's own arithmetic, now with "ARR = the expense lines" per column: 23 / 24.**  The
    exception is A61 (reviewer).  The ARR year's summary prints approved interest as 110.80;
    Table 6-72 approves 110.43, and the summary's ARR (3,420.27) adds up only with 110.43 (its
    lines with 110.80 add to 3,420.65).  The totals are consistent; the line reads as a misprint.
    An identity is skipped in a column that prints none of its parts.
  Nothing verified, nothing approved.

  **Increment 97 (2026-11-02): the Commission's O&M approval reproduced with the same rules.**
  The ARR year's largest cut is O&M (−18.37).  The order states its method and figures (pp.252–258,
  Tables 6-45, 6-48, 6-49).  `order/figures-om-fy2026-27.json` holds 34 of them, each with its
  page, quote and column header, and `check_order_quotes.py` finds 34 / 34 (the loader now reads
  "1,062.12" in a quote as 1062.12).
  - **Engine:** a `cells` evaluation can take what an earlier evaluation of the same binding
    computed (`{"computed": label, "output": …}`), unrounded.  The order carries its chain
    unrounded: restarting from each printed figure would end at 87.64, not the printed 87.63.
    A check can name a record figure (`"order:<key>"`) instead of a cell.
  - **Binding `approval-om-fy27.json`, using the same draft rules that reproduce NPCL's claim:
    12 / 13 match**, and every final approval matches:
    - employee 87.63: the five-year average, CPI escalation, no growth factor;
    - A&G 28.87: WPI escalation;
    - R&M 111.04: Reg. 33.7's 5 % and 3 % of the approved GFA, nothing for GNIDA.
    One intermediate year is one unit off: employee FY2025-26 computes 84.56 against the printed
    84.57.  The order applies a CPI change slightly above the 4.87 % it prints.
  - **A60 (petitioner): the decision explained, exactly.**
    - employee −12.35 = growth factor refused (−11.62) + three-year CPI average 3.63 % against
      4.48 % (−0.72);
    - A&G −0.38 = the FY2026-27 WPI 0.42 % against 1.73 %;
    - R&M −2.65 = the approved GFA split (A −4.33, B +1.65, C +0.45) and GNIDA (−0.42);
    - the provision of 3.00 refused.
    The finding says what the next petition should do differently.
  - **Significance:** the draft rules now reproduce both the petitioner's claim and the
    regulator's approval of the same lines.  The difference is located in named inputs (growth
    factor, index average, GFA base) rather than in the arithmetic.
  Nothing verified, nothing approved.

  **Increment 96 (2026-11-02): what the Commission decided, line by line (R-TU-5).**  The
  FY2026-27 order (2 July 2026, the golden NPCL document) is the decision on this very petition.
  Its three summary tables are now read row by row from the text layer, each row with its page
  and the text it was read from (`tariff_api.arr.decisions`, `scripts/order_decisions.py` →
  `order-decisions.json`):
  - true-up FY2024-25, pp.166–167: approved earlier, claimed, approved;
  - APR FY2025-26, pp.207–208: approved, claimed, provisionally considered;
  - ARR FY2026-27, p.294: claimed, approved.
  - **Reading:** rows are found by their serial numbers, so a page header inside a table is
    passed over.  A row printing fewer figures than columns is read only where the spec names
    its columns: three rows of the true-up and one of the APR, assigned from the layout text.
  - **Mapping:** rows are mapped to the ARR format with the narrative's row map plus the order's
    groupings (gross O&M = rows 26 + 27 + 31; ARR before RoE = row 46 − row 43).  One table may
    override a column: the true-up's earlier approval prints revenue gross (row 13) with the
    regulatory discount on its own row (−row 14).  My first map had that as a 302.86 "difference".
  - **The order read the petition as filed.**  Every claimed and earlier-approved figure agrees
    with the ARR format to the last printed place: 37 + 38 + 21 match; the 11 others are 1–2
    units of rounding.
  - **The order's own arithmetic holds:** 16 / 16 column identities (net ARR, gap).
  - **The decisions** (approved − claimed, Rs crore):
    - **true-up FY2024-25: −123.38.**  Employee cost 95.42 → 37.64; A&G −14.81; R&M −9.31; the
      contingency reserve, efficiency gains and the additional O&M disallowed; power purchase
      −11.99.
    - **APR FY2025-26: +92.64.**  Power purchase +118.55; employee −11.06.
    - **ARR FY2026-27: +29.51.**  Power purchase +29.03 and transmission +35.13; employee
      −12.35; interest −8.51; depreciation −2.95; provisions disallowed.
    These are the Commission's figures, with the reasons in the order's chapters.  The petition
    engine's later task is to anticipate them, not to restate them.
  - **Shown on the page** as panel 06d, with the API's `decisions` block.
  Nothing verified, nothing approved.

  **Increment 95 (2026-11-02): the regulatory asset rolled forward, end to end.**  Each year's
  "gap / surplus from preceding years" (ARR row 59) was a record in every column, taken on
  trust.
  - **Ties along the petition's chain: 7 / 7 match** (new binding `arr-gap-roll-forward.json`,
    rule `uperc.carried.gap_opening`).  Each opening is the cumulative closing (row 63) of the
    column it continues: C→D, D→F, D→G, G→I, G→J, J→L, L→M.  Coverage now shows row 59 as tied
    in those columns.
  - **Approved columns not tied.**  E, H and K are each a different order's approval, and later
    orders revise earlier years, so they are not one chain.  An observation for the reviewer:
    K59 (1,242.59) equals H63 (1,254.43) less I62's carrying cost (11.84).  It is not bound.
  - **The end-to-end pipeline carries the asset.**  A pipeline column can now be fed from an
    earlier column's computed output (`{"column": …, "output": …, "why": …}`).  Columns are
    evaluated in dependency order, a cycle or an unexplained or unknown feed is an error, and
    `OutputCheck` keeps the unrounded value to feed with.  The APR year opens with the true-up
    year's computed closing, and the ARR year with the APR year's.
  - **Result:** each year's net ARR and gap still match.  A40's 0.19 (the March security-deposit
    interest) now travels down with carrying cost:
    - the true-up closes at (267.94) against the filed (267.74);
    - the APR at (629.59) against (629.37);
    - the ARR at (1,002.64) against (1,002.39).
    The ARR and APR columns are therefore 10 / 12, the two differing rows being the carried gap.
    The previous 12 / 12 had reset each year's opening to the filed figure.  A40 now states
    this effect.
  - **Tests changed with the design:** the pipeline unit and integration tests now expect
    10 / 12 and the 0.22 / 0.25 carried.
  Nothing verified, nothing approved.

  **Increment 94 (2026-11-02): the regulations' filing requirements as a checklist (R-PKG-1).**
  I read the 2025 Distribution Regulations for a list of mandatory formats (item 5a): **they
  have none.**  Regs. 4.2, 5.1 and 6.1 refer to "guidelines and formats as may be prescribed by
  the Commission", which is a separate prescription.  So 5a is still blocked, now correctly
  described.  What the Regulations do set out (Regs. 3–8) is what a petition must contain and
  how it is filed.
  - **The checklist** (`packages/filing-checklists/uperc/myt-2025.json`, version 1, draft) has
    17 requirements.  Each has its clause, page and a verbatim quote; a test finds every quote
    on its page of the committed PDF, named by hash.  Each also says what would evidence it: a
    package document, a formats sheet, or DOCX text weighted as a *statement* (a dated or sworn
    fact) or only a *mention*.  Requirements no document can show (portal filing, signature,
    fees, public notice) are *outside*.
  - **`tariff_api.arr.checklist`** grades each requirement:
    - evidenced (all found, none a mere mention);
    - partly (something missing, or a part only mentioned);
    - mentioned;
    - not found;
    - outside the package.
    Evidence found is not compliance.
  - **NPCL FY2026-27: 11 evidenced, 2 partly, 1 mentioned, 3 outside.**
    - The filing date: the affidavit was verified on 14.12.2025, under the extension to
      15.12.2025 that the cover letter cites.  The Commission's letter itself is not among the
      documents.
    - **Partly:** the Board's resolution is cited, but Form-1's Appendix I is not in the package.
      Load factor is only mentioned (no format carries it).
    - **Mentioned:** the metering status and diversity factors (Reg. 8.4(a)).
    - **A59 (reviewer):** Reg. 6.4 wants the true-up's accounts under the Accounts and
      Additional Disclosure Rules 2024 and amendments.  NPCL answers "being complied" for the
      named disclosures and will comply with the Rules from FY2026-27.
  - **Two grading bugs, found by reading the first run:**
    - "Appendix-I" matched "Appendix-II".  It now needs a boundary.
    - A requirement with a mention-only part was graded evidenced.  It is now partly.
    The 6.4 evidence had first matched the Commission's directive quoted in Appendix VII; it
    now matches NPCL's own statement.
  - **Output:** `scripts/filing_checklist.py` writes `checklist.json`; the page shows it as
    panel 06c.
  Nothing verified, nothing approved.

  **Increment 93 (2026-11-02): the narrative reconciled to the formats (R-ACC-5).**  A petition
  restates its figures in prose: the true-up, APR and ARR texts, the executive summary, Form-1,
  the cost allocation and the compliance note.  These are 310 tables in seven DOCX files.
  `tariff_api.arr.narrative` reads them as untrusted text, keeping each merged cell once and
  taking each table's title.  It parses every printed figure with its printed precision
  (brackets are negative, % is kept as a unit).
  - **The trace (every figure).**  Each figure is looked for among the 31,778 numeric cells of the
    formats workbook and the three record workbooks, at its printed precision:
    - **1736 traced;**
    - **218 near** (one unit of the last place away);
    - **77 opposite sign** (a gap printed positive where the format holds a
      negative shortfall);
    - **1538 untraced;**
    - **5339 uninformative:** fewer than 4 significant digits, which would match
      some cell by chance, so they are counted but never called traced.
    The untraced figures cluster in tables whose source is not the formats: project-wise capex,
    vehicles in rupees, month-wise availability, approved figures quoted from earlier orders.
    The page lists the 25 tables with the most untraced figures as the reviewer's reading list.
    A trace says where a figure also appears; it does not say it is the same quantity.
  - **The bindings (summary tables, row by row).**  Nine summary tables are bound to the ARR
    format: true-up, APR and ARR in Appendices III–V, the executive summary and Form-1.  Each
    table is found by its title and each column must carry its header word (Approved / Actual /
    Estimated / Projected).  Each row is matched in full by its label, sums the format rows it
    names (power purchase with its arrears, interest with its four parts) and takes the gap
    with the sign reversed.  A missing table, a wrong header or a row matching twice is an
    error, never a guess.
  - **Result: 253 figures — 232 match, 21 differ.**  Every claimed, estimated and projected
    figure matches; all 21 differences are in the approved columns:
    - **A56 (petitioner):** Form-1's Table-II prints an approved ARR of 2,718.46, against 2,728.76
      in Appendix III and the executive summary and 2,728.77 in the format.  It also prints
      approved open-access revenue of 53.01, which repeats the non-tariff income figure.
    - **A57 (petitioner):** the APR's approved opening surplus is printed (1,202.28), against
      1,242.59 in the format (K59).  The format rebuilds its own total; the narrative's opening
      does not.
    - **A58 (reviewer):** the true-up's approved carried-forward (1,163.25) deducts 91.19 of
      power purchase provisions that the format does not carry.  The other approved differences
      are 1–2 units in the last place: the order's printed roundings against unrounded arithmetic.
  - **Output and page.**  `scripts/reconcile_narrative.py` writes `narrative.json`.  The reference
    page shows it as panel 06b: counts per document, the differing figures with their cells,
    and the reading list.
  Nothing verified, nothing approved.

  **Increment 92 (2026-11-02): the existing tariff checked against the order, and HV in kVAh.**
  - **The rate record now holds 58 rates.** Added: HV-1 to HV-4 per kVAh by supply voltage, the
    HV-2 rural rebate, LMV-3 by local body, LMV-7 and its rural rebate, LMV-9, and LMV-5's
    energy-efficient pumps.  Where several rates share one printed row (LMV-3, HV-2), each also
    quotes the column header it sits under.  `scripts/check_order_quotes.py` now checks headers
    too: **58 / 58 quotes and headers found** on their pages.
  - **New units `kVAh` and `INR_per_kVAh`,** with their own dimension.  A kVAh rate times kWh sold
    is now a dimension error: the rule blocks with the reason and never returns a revenue.
  - **ESR4A (NPCL's own rate schedule, column C "Existing Tariff", the rates ESR-3 is at) against
    the order's rates: 47 / 47 match.**  This covers every energy rate it states, LT per kWh and
    HV per kVAh.  So the FY2025-26 rates ESR-3 uses are the rates the order kept for FY2026-27,
    which settles the caveat in increment 91.  The format moves from "present" to "reproduced":
    formats accounting is now 40 reproduced, 9 read, 22 present, 2 blank, 1 missing.
  - **A55 (for the petitioner):** HV energy charges (1,740.21 crore, ESR-3 K92:K135) are billed
    per kVAh, but ESR-3 states only kWh sold, so they cannot be recomputed.  Dividing the charges
    by the kVAh rates implies 1.012–1.046 kVAh per kWh, which is plausible but derived from the
    answer.  The petitioner should state the kVAh sold.
  - **Corrected before commit:** I first wrote that HV total from memory as 1,670.27.  The
    computed sum is 1,740.21, and that is what A55 carries.
  - **Not checked:** the time-of-day percentages in ESR4A (printed as text), and fixed, demand
    and minimum charges.
  Nothing verified, nothing approved.

  **Increment 91 (2026-11-02): revenue from the tariff order's rates.**  ESR-3's energy
  charges were summed as filed; now each slab's charges are also computed from its units sold and
  the energy rate of the UPERC order's Annexure-I rate schedule.  The order (NPCL's FY2026-27 order
  of 2 July 2026, the golden manifest's NPCL document, SHA-256 `ff36813e…4b1a`) is read for **36
  rates and percentages** (pp.362–381: LMV-1 rural and urban slabs and bulk supply, LMV-2, LMV-4,
  LMV-5, the LMV-6 base rate with its summer and winter time-of-day percentages and the rural
  rebate, LMV-11).  Each rate is a quote taken from the page's text by a pattern, never typed, in
  `packages/reference-filings/uperc-npcl-fy2026-27/rate-schedule-fy2026-27.json`.
  - **Engine:** `load_rate_record` refuses a rate whose figure is not in its quote, a rate with no
    page, and a record that does not name its document by hash.  `reproduce_cells` takes an input
    `{"rate": key}` from the record the binding names, and a key the record lacks is an error.
    Rules may use an `order:<name>` source.  New draft rule `uperc.revenue.energy_from_rate`:
    units × rate × (1 + adjustment), with a worked example from ESR-3 row 15.
  - **`scripts/check_order_quotes.py`** re-finds every quote on its page in the PDF named by
    hash: **36 / 36 found** on the order.  That shows the figures are printed where the record
    says; it does not show each is the right rate for its row, which the reviewer checks.
  - **Result (binding `esr3-energy-from-rates-fy27.json`): 40 of 45 slab rows match to four
    places**, the 20 LMV-6 time-of-day slots and the rural rebate included.  The order's schedule
    is FY2026-27's, while ESR-3 is at the FY2025-26 tariff, whose order is not in this session.
    So a match shows the slab's rate did not change; it does not prove the petition's source.
  - **Five rows differ, both findings for the petitioner:**
    - **A53:** the four urban domestic slabs are filed 1.8–1.9 % below rate × units (9.87
      crore).  This is consistent with the 2 % prepaid-meter discount (p.357) on most of the
      sales.
    - **A54:** the registered societies (bulk) are filed at 6.3465 Rs/kWh against 7.00 (40.21
      crore less).  This is consistent with kVAh billing at 0.90 × the kWh rate (p.353).
    Both are readings, not facts; the petitioner states the basis.
  - **Not bound, with the reason in the binding:**
    - LMV-3: one rate per local-body type, one ESR-3 row; choosing a column would fit the answer.
    - LMV-7 and LMV-9: the implied rates exceed the schedule's.
    - The HV categories: one row per voltage band, rates not yet read.
    - Fixed, minimum and other charges.
  Nothing verified, nothing approved.

  **Increment 90 (2026-11-02): the notified MYT Distribution Regulations 2025, read for
  clause candidates.**  The operator uploaded `NotifiedMYTDistribution2025.rar` (SHA-256
  `547d1e17…062c`).  It is a RAR5 archive: Debian's 7-Zip lacks the codec, so it was extracted
  with bsdtar into its own folder as untrusted data, text only.  It holds the English text (58
  pages, text layer), the Gazette notification (Hindi), the Hindi text and the Statement of
  Reasons (66 pages, scanned, no text).  The English text is committed as
  `packages/regulations/uperc/myt-distribution-2025-english.pdf` with a manifest (hash,
  provenance, what was not committed).  The candidates tool gained `--applies-in` (only the rules
  in force that year — a 2019-only rule is not offered the 2025 text) and was run for
  FY2025-26: **108 of 151 rules have candidate pages from the regulation itself.**  RoE 15 %
  post-tax → p.31 (Reg. 19 equity base); R&M 5 % / 3 % of opening GFA → p.43; the five-year
  base for employee cost → p.42; bad debts → p.45; the cross-subsidy surcharge → p.48.  The
  regulation has no contingency-reserve provision (the word does not occur), consistent with NPCL
  claiming it only in the 2019-regime true-up years.  **Reading the candidates beside the draft
  rules found two departures, for the reviewer:**
  - **A51:** the 2025 Regulations cap the surcharge at 20 % of the *average cost of supply*;
    F33, and the draft that follows it, cap at 20 % of the category's ABR, though F33's own
    header says ACoS.  No numerical effect this year.
  - **A52:** bad debts are capped at 2 % of *revenue from the sale of electricity in the
    audited accounts*; P3 and the draft take 2 % of receivables.  No effect this year.

  The drafts are not changed, only annotated: amending a rule to its clause comes with
  verifying the clause, a person's act.  Still to obtain: the 2019 MYT Regulations, for the
  true-up years' rules.  Nothing verified, nothing approved.

  **Increment 89 (2026-11-02): clause candidates — proposals for the reviewer, never
  verification.**  The 160 draft rules wait on a person verifying each clause against the
  regulation.  `tariff_api.arr.clauses` ranks a document's pages for a rule: each distinct
  significant title word counts 1; each of the rule's regulation values printed on the page counts
  5 ("20 %", "20%", "20 per cent").  A page needs a title word, and without a value it needs
  three of them (all, for a shorter title): no proposal is better than noise.
  `scripts/clause_candidates.py` reads a PDF's text (PyMuPDF; untrusted data, text only) and
  writes `packages/arr-rules/<commission>/candidates/<label>.json`, recording the PDF's SHA-256
  and what kind of document it is.  The subfolder is never read as rules.  The rules API and
  page list up to three candidate pages per unverified rule, with snippets, marked "proposed, not
  verified"; nothing sets `verified`.  **The official regulations could not be fetched from this
  session:** uperc.org refuses the menu postback (403, its bot protection — not pursued) and India
  Code timed out; third-party copies are no basis for verification.  So the tool was run on
  **UPERC's FY2026-27 order for NPCL** (SHA-256 `ff36813e…`, as registered in increment 37),
  labelled as an order that quotes the regulations.  **It finds the known answers: both RoE
  rules → pp.151 and 204** (the pages identified by hand earlier; p.151 quotes "Regulation 22 of
  the MYT Regulations, 2019" and 15 %).  Also the surcharge → p.320 (20 %), the bad-debt cap →
  pp.102 / 157 (2 %), the 2025 R&M → pp.187–188 (5 %, 3 %), deposit interest → pp.147–149 and the
  base-year O&M → p.184.  137 of 160 rules have candidates; 23 have none rather than noise.
  **Next, for the operator:** download the official UPERC MYT Distribution Regulations 2025 and
  the MYT Regulations 2019 and run
  `uv run python scripts/clause_candidates.py --commission UPERC --pdf <file> --cites 2025 --label myt-2025`
  (and `--cites 2019 --label myt-2019`); the reviewer then verifies with the pages in hand.

  **Increment 88 (2026-11-02): the true-up years' capitalisation by scheme.**  F16 for the years
  up to FY25 is bound with the capex rules: the schemes of FY2023-24 and FY2024-25, the latter
  each carried from F13.  **NPCL: 4 / 4 — 162.06 and 302.59, F14's capitalisation (row 11).**
  The end-to-end pipeline now feeds the true-up year's capitalisation from its schemes (13 inputs
  fed; still 7 + 5, A40's 0.19).

  *Docs defect found and fixed in increment 87:* the narrative entries of increments 76–86 had
  not been written.  Increment 76's script anchored on increment 75's heading with a wrong word,
  the replacement silently did nothing, and each later entry anchored on the one before it.  The
  test-result lines had landed.  They are restored above from the same text, and the docs
  scripts now assert their anchors.

  **Increment 87 (2026-11-01): draft queries to the petitioner.**  `GET
  /arr/reference-filings/{id}/queries` (analyst and above) returns a Markdown draft of the
  queries to the petitioner (the deficiency note the Commission's staff issue).  It is built from
  the findings addressed to the petitioner, each numbered with its id, detail and where it is in
  the filing.  The findings addressed to the reviewer are listed apart, as matters for the
  Commission rather than questions.  It is labelled "DRAFT for the reviewer to edit and issue …
  not reviewed, not issued"; nothing issues it.  The reference page links it from the findings
  panel, through a web route carrying the caller's identity.  **NPCL: 11 questions to the
  petitioner, 7 points for the Commission.**  Checked through the web route on the local stack.

  **Increment 86 (2026-11-01): the distribution loss across formats.**  One draft identity: a
  share carried from one format to another is the same (R-SCH-16).  It checks the Energy
  Balance's loss against P1_DL's claimed column and the ARR's row 10 for the four petition
  years.  **NPCL: the Energy Balance and the ARR agree every year.  P1_DL claims 7.45 %
  (FY2025-26) and 7.42 % (FY2026-27), where the petition is computed at the Commission's 7.23 %
  and 6.97 %; FY2024-25 differs in the sixth decimal** (A50, for the petitioner: which loss is
  claimed).

  **Increment 85 (2026-11-01): revenue at the proposed tariff.**  ESR4 is bound with the
  revenue rules (236 match; slabs with no units have no rate).  One more draft rule: the tariff
  revision impact (proposed less current), which is the ARR's row 55.  **NPCL proposes no
  revision: ESR4 repeats ESR-3 FY27 row for row (3,192.04), and the impact is 0, as filed.**

  **Increment 84 (2026-11-01): FY2023-24 power purchase.**  PPC FY 24, the earlier billed
  layout without transmission columns, is bound as four row tables: sources, transmission,
  earlier years' claims, and transmission of earlier years.  One more draft rule: net charges
  total.  Row tables can declare an unlabelled row with its reason; it was otherwise skipped,
  which would have dropped an amount NPCL's total includes.  **NPCL: every check matches —
  power purchase 1,740.92, transmission 197.01, arrears 8.97, transmission arrears 0.35 and
  energy at the bus 3,383.96 MU are the ARR's FY2023-24 rows 20, 23, 22, 24 and 8.**  Power
  purchase is now reproduced in all four years.  **A49** (for the petitioner): hand adjustments
  inside the claims' formulas (a −0.05; a computed carrying cost zeroed and replaced by 0.89;
  amounts multiplied by 0) and an unlabelled 0.0743.

  **Increment 83 (2026-11-01): the renewable purchase obligation.**  8 draft rules
  (`rpo.v1.json`):
  - consumption grossed up to the distribution periphery, less hydro;
  - energy at the state and the distribution periphery through the transmission losses;
  - the obligation (base × share) and each category's balance;
  - the year's obligation, netted across categories, and the closing obligation after RECs.

  **NPCL F6: 54 / 54 over FY2024-25 to FY2026-27.**  The losses NPCL types into its formulas
  are declared as stated constants.  **A48** (for the reviewer): those losses are not the Energy
  Balance's (FY2026-27 3.58 % / 3.18 % against 3.41 % / 3.35 %), and F6's sales differ from
  ESR-3 by about 0.004 MU.  The categories are netted: a solar and non-solar surplus offsets a
  hydro shortfall, and a net surplus is carried forward as a credit.  FY2025-26's REC purchase is
  typed equal to its obligation.

  **Increment 82 (2026-11-01): the wheeling / supply allocation and the cross-subsidy
  surcharge.**  6 draft rules (`open-access.v1.json`, `allocation.v1.json`, R-SCH-15):
  - a per-unit charge (a cost in Rs crore over energy in MU, in Rs/kWh by the units);
  - the cost of supply at a voltage, C / ((1 − L1)(1 − L2)(1 − L3)) + D + R;
  - the surcharge, T − cost of supply, capped at 20 % of T and never negative;
  - the petitioner's proposal (the lower of the computed and its own figure);
  - each ARR item's wheeling and supply allocation.

  Row tables can skip named subtotal rows, with the reason.  **NPCL FY2026-27:**
  - **F32: 34 / 34**;
  - **F33: 48 / 48** — the distribution, transmission and wheeling charges per unit; the
    average power-purchase cost; the cost of supply at five voltages; 14 category ABRs; the
    capped surcharge (HV-1 at 11 kV 1.21 Rs/kWh; HV-2 below its cost of supply, so 0); and the
    proposal.

  One category with no sales has no ABR (blocked).  **A47** (for the reviewer): F32's summary
  column double-counts interest (119.31).  Its allocation base adds the carrying cost (83.23),
  omits provisions (3.00) and does not deduct other income (10.82) — the base the surcharge rests
  on is the reviewer's call.

  **Increment 81 (2026-11-01): revenue of FY2023-24, in the earlier layout.**  ESR-3 FY2023-24
  bills in seven columns: fixed, energy, minimum, other charges, regulatory surcharge, total
  minimum charges and regulatory discount.  Its eleven category subtotals subtract rows that are
  blank in every column.  Two draft rules and one row table.  **NPCL: 194 match; revenue
  2,320.97 and units 3,130.40 MU are the ARR's rows 15 and 9 (FY2023-24).**  44 rates of slabs
  with no units are blocked, never 0.  Revenue is now reproduced in all four years.

  **Increment 80 (2026-11-01): R&M and A&G of the true-up reconciled to the books.**  The
  ledger binding takes a list of groupings, or several condition sets (an account in any counts
  once).  **NPCL: the true-up's R&M (F22: 72.36) is five sub-groupings of Note 33** (R&M of the
  T&D system and others, security, insurance, power and fuel; 25 accounts).  **Its A&G (F23:
  40.91) is seven sub-groupings of Note 33 and the finance charges of Note 31** (44 accounts).
  CSR expenditure (4.23) is in the books and not claimed.  The trial balance now agrees with
  **11 of 13** true-up claims; employee benefits and net employee expenses differ, by exactly
  0.0105 crore (A46).  My first R&M binding named a sub-grouping from a truncated printout and
  found 11 accounts instead of 25; corrected from the ledger's own text before commit.

  **Increment 79 (2026-11-01): the true-up reconciled to the books.**  Two of NPCL's own records,
  hashed and checked against the manifest, are committed beside Annexure-21: **Annexure-14**
  (power purchase reconciled with the audited accounts) and **Annexure-41** (the trial balance,
  474 accounts).  The `cells` binding reads other workbooks of the filing (`name::Sheet!A1`).  A
  new **`ledger`** binding sums trial-balance accounts by their own financial-statement grouping
  (note, sub-grouping) through two draft identities (per account in rupees, the total in Rs crore
  by the units) and compares the total with the claimed cell at its filed precision; it never
  moves an account by resemblance.  **NPCL:**
  - **Annexure-14:** its own bridge reproduces (2,471.54); against the claim (2,470.04) it differs
    by 1.50 — the FY2023-24 carrying cost, 12.88 against 11.37 (**A44**).
  - **Trial balance: 9 of 11 agree to the paisa of a crore**; employee benefits differ by exactly
    0.0105 crore (**A46**).

  **BS1, the format's "profit and loss account", is formulas over the ARR format, not the audited
  accounts (A45):** it is circular as evidence.

  **Increment 78 (2026-11-01): average cost of supply and billing rate.**  Two draft rules
  (R-SCH-14): ACoS (net ARR / sales) and ABR (revenue / sales), in Rs/kWh by the units.  Checked
  on the three snapshots.  **NPCL: 8 / 8 — FY2026-27 ACoS 7.9135 against ABR 7.2549 Rs/kWh.**
  The snapshots' "Approved in Tariff Order" column is blank for the ARR year and typed 0 for the
  true-up year's ABR and ACoS.

  **Increment 77 (2026-11-01): every format accounted for (R-ACC-3), against the filing's own
  index.**  Each of the 74 formats the workbook's `Index` lists is reproduced, read, present,
  blank or missing; sheets not in the index are listed.  Names match exactly or through declared
  aliases with reasons (`formats-index.json`), never by resemblance.  Served by the API; panel
  06 of the reference page.  **NPCL at the time: 27 reproduced, 10 read, 34 present, 2 blank (ESR6,
  F10), 1 missing (ESR7); F19A filed but not indexed** (A43).  A proxy until the Commission's
  mandatory list is provided.  Also **A42**: revenue at the current tariff cannot be computed from
  the rate schedule in force (rural slabs match it exactly, urban domestic imply 1.8–1.9 % less).

  **Increment 76 (2026-11-01): independent sign-off (R-ACC-2), the mechanism — nobody has
  signed.**  Migration **0021** adds `acceptance_records`, an append-only record of a named
  checker's sign-off.  Each record holds:
  - a scope: the whole filing, one petition column, or the treatment of one finding;
  - a decision: accepted, accepted with reservations or rejected — a reason is required for
    anything short of acceptance, enforced in the API and by a database constraint;
  - the checker's attestation that they did not build the reproduction (a constraint);
  - the SHA-256 of the `reproduction.json` they were shown.

  The POST (reviewer or above, audited) refuses a stale hash (409); the GET lists every record,
  current or stale, the latest per scope and the scopes still open.  A changed reproduction makes
  earlier sign-offs stale; they are never carried forward.  The reference page's sign-off panel
  (now 07) shows the records and, for a reviewer, the form (scope, note, attestation; buttons
  disabled until it is ticked; the hash being signed shown).  **NPCL: nothing signed.**  The build
  signed nothing on any stack; only the integration test's synthetic reviewer signs, in the
  throwaway test database.

  **Increment 75 (2026-11-01): capitalisation of the APR and ARR years from the capital plan.**
  4 draft rules (`capex.v1.json`):
  - each scheme's capitalisation (per scheme) and their total;
  - the movement in capital work in progress (opening less closing);
  - the year's planned capitalisation, the schemes plus that movement.

  A `cells` binding reads F16 after FY25 (26 schemes, each carried from F13) and F15's CWIP.
  **NPCL: 8 / 8 — capitalisation 448.49 (FY2025-26) and 493.69 (FY2026-27), as F14's row 11
  carries them.**  The pipeline now feeds it, so the capital chain of the APR and ARR years
  (equity and loan additions, RoE, interest on loan, tax) starts from the capital plan, not
  from F14's row.  Still 12 / 12 in both years, with 15 and 14 inputs fed.  Consumer-contribution
  additions (F12) and retirements (F11, F14 row 13) are typed by NPCL and stay records.  No rule
  is approved.

  **Increment 74 (2026-11-01): the rates fed from their reproduction.**  The pipeline now feeds
  two rates from the MCLR revisions' reproduction (F27):
  - the APR year's normative-loan rate (the weighted MCLR + 1 %), carried to the ARR year as
    NPCL's F25 does (I14 = H14);
  - the true-up year's working-capital rate (the weighted MCLR + 2.5 %).

  A feed may take another year's value only with the binding's stated reason; without one it is
  refused.  The APR and ARR years' working-capital rate is one MCLR NPCL picks from the list
  (+ 2 %), a choice rather than a computation, so it stays a record.  **NPCL: unchanged results
  with more of the inputs computed — ARR year 12 / 12 (13 fed), APR year 12 / 12 (14 fed),
  true-up year 7 + 5 (A40's 0.19).**  No rule is approved.

  **Increment 73 (2026-11-01): the petition computed end to end from its schedules.**  A
  `pipeline` binding (`pipeline-petition.json`) evaluates the chain for the petition's columns
  with its record inputs **replaced by what each schedule's reproduction computes**: power
  purchase, transmission and arrears (PPC), R&M (F22) and employee / A&G (F19 base) of the APR and
  ARR years, depreciation (F24), interest on security deposit (F30), bad debts and other items
  (P3), revenue (ESR-3) and the contingency fund.  A fed value is the schedule rule's unrounded
  result in its unit (`BlockCheck.exact`), never the rounded display.  `reproduce()` takes the
  fed values per column; `reproduce_pipeline()` lists, per column, what was fed (binding and
  output), what was not, and every input that stays a record.  Served by the API; shown on the
  reference page (panel 02).  **NPCL:**
  - **FY2026-27 (ARR): 12 / 12**, 12 inputs fed — net ARR 3,481.83, gap −289.79.
  - **FY2025-26 (APR): 12 / 12**, 13 inputs fed — net ARR 3,200.63, gap −315.87.
  - **FY2024-25 (true-up): 7 match, 5 differ** — total expenditure, net ARR, gap, carrying cost
    and cumulative gap, each by exactly 0.19.  That is the security-deposit interest NPCL types
    for March (A40), carried through.  The computation shows the finding's effect instead of
    hiding it.

  **Inputs still records in the ARR year:**
  - capital additions and retirements (F14's inputs), prior-year closings and the rates
    (assumptions);
  - employee capitalisation, finance charges, provisions, additional O&M;
  - non-tariff and other-business income, open-access revenue;
  - the accumulated gap brought forward.

  No rule is approved; every clause is unverified.

  **Increment 72 (2026-11-01): the ARR format's revenue identities.**  Two draft rules: gross
  revenue at the current tariff (net less the regulatory discount, row 13) and total receipts
  (net + captive consumption, row 17; captive is blank in NPCL's format and its formula reads it
  as zero, declared).  **NPCL: the ARR summary's checks 106 → 128 match, none new differs; the
  projected column's coverage: 17 computed, 13 tied, 16 records.**  No rule is approved.

  **Increment 71 (2026-11-01): how each ARR figure is established.**  The reproduction now
  writes a **coverage map** of the ARR format: for every line and column, whether the figure is
  - **computed** — by the chain from base records, or as the format's own identity;
  - **tied** — a schedule's reproduction gives the figure the ARR carries;
  - **given** — a filed figure standing in for its computation;
  - **differs** — computed or tied, and not equal to the filed figure;
  - **record** — an input nobody reproduces yet, taken on trust.

  Each status names its source binding and output.  `GET /arr/reference-filings/{id}` serves it.
  The desk page `/arr/reference/<id>` opens with it (panel 01): the petition's columns line by
  line, with a legend and per-column counts.  Bindings that reproduced a figure without naming
  the ARR cell now do: PPC FY 26 / 27 (rows 8, 20, 23), ESR-3 (row 14), the contingency fund.
  FY2025-26's power purchase includes three claims of earlier years (incentives for FY2022-23
  and FY2023-24, an O&M reimbursement; PPC FY 26 rows 54–56) and its arrears line is rows
  57–60.  Three draft rules (per-claim, total, cost with claims) reproduce both (2 / 2); which
  claims belong with power purchase is the petitioner's presentation, for the reviewer.
  **NPCL coverage, petition columns:**
  - FY2024-25 claimed: 15 computed, 10 tied, 2 differ (A40, A41), 14 records.
  - FY2025-26 estimated: 15 computed, 14 tied, 17 records.
  - FY2026-27 projected: 15 computed, 13 tied, 18 records.

  The records are named on the page.  The fix in the manifest is a document name (a mis-decoded
  apostrophe).  Checked by screenshots at 1440 and 390 px; the page does not scroll
  horizontally.  No rule is approved; every clause is unverified.

  **Increment 70 (2026-11-01): the true-up year's power purchase, as billed.**  14 draft rules
  for the billed format, per source:
  - billed (fixed + energy + other charges), net of the rebate, and with transmission;
  - the rate on the energy billed and the cost per unit at the licensee's bus;
  - the inter-state, intra-state and total losses;
  - the totals.

  PPC FY 25 is bound as three row tables, because the ARR carries three of its parts on separate
  lines: the sources (rows 11–58), the transmission charges (61–64) and earlier years' claims
  paid in the year (additional coal and change in law for FY2022-23 and FY2023-24, with carrying
  cost; 69–77).  The last two print only the bill, which is taken as given.  **NPCL: every check
  matches — power purchase 2,047.91 (the ARR's row 20), transmission 294.40 (row 23), arrears
  127.73 (row 22), energy at the bus 3,888.46 (row 8), bills 2,064.12, rebate 16.21.**  The REC
  purchase has no energy, so it has no rate or loss (blocked, never 0).  A charges-only incentive
  row is declared blank-as-zero with its reason.  One more draft rule: the contribution to the
  contingency fund, 0.25 % of the opening gross block (the ARR's row 42, true-up years only: 5.23
  and 5.61, 2 / 2).

  **Coverage of the ARR's three petition columns after increments 65–70.**
  - **Reproduced from their schedules or tied to them:** power purchase, transmission and
    arrears; depreciation; the APR and ARR years' O&M; interest on loan and on security
    deposit; bad debts and other items; the contingency fund; RoE and tax (the chain); and
    revenue from the current tariff.
  - **Still records:**
    - the true-up year's actual employee, R&M and A&G expenses, which are audited ledger sums;
    - the additional O&M items;
    - finance charges (typed in F23);
    - non-tariff income, whose projections are typed;
    - open-access revenue (ESR1);
    - employee capitalisation from the capital plan (F13).

  No rule is approved; every clause is unverified.

  **Increment 69 (2026-11-01): revenue from the current tariff, by category.**  8 draft rules
  (`revenue.v1.json`, R-SCH-12), evaluated per consumer category, slab or time-of-day block of
  ESR-3:
  - the row's revenue (fixed + energy + minimum + other charges + regulatory discount);
  - the energy and fixed charge per unit it implies, which is not a regulation;
  - the totals: revenue (R.REV.EXISTING), units sold and the discount.

  The rate schedule of the tariff order is not read yet, so the implied rates are shown for the
  reviewer to compare; NPCL's revenues are its own billing figures.  **NPCL: FY2024-25 231
  match, FY2025-26 104, FY2026-27 238.  Revenue 2,634.60, 2,884.76 and 3,192.04 and units sold
  3,597.63, 3,951.43 and 4,399.84 are the ARR's rows 15 and 9 in the true-up, APR and ARR years.**
  The one difference is FY2024-25's regulatory-discount total, whose formula subtracts a typed 0.04
  (finding A41, for the petitioner).  Slabs with no units have no implied rate (blocked, never 0).
  FY2023-24's ESR-3 has subtotal rows that subtract their own sub-rows, so it is not yet bound.
  No rule is approved; every clause is unverified.

  **Increment 68 (2026-11-01): interest on security deposit, receivables, bad debts and other
  items.**  14 draft rules:
  - **Security deposit:** each month's closing balance and interest (the average balance at the
    bank rate / 12, per month, summed), and the year's interest on the average balance.
  - **Receivables (F31):** revenue billed as receipts × NPCL's gross-up, the year-end balance at
    20 days of billing, and the collection.
  - **Bad and doubtful debts (P3):** the share of receivables; the APR / ARR provision from the
    previous year's share; the claim (provision + write-off); the 2 % cap; the closing provision.
  - **The value of beating the loss target:** energy × (approved − actual loss) × receipts ÷ sales.
  - **Other items:** loss on retired assets, the loan-swap gain and the loss-reduction revenue.

  The `cells` binding gained categories (the months of a year, summed by the aggregate rule) and
  two input forms, each requiring its reason: a stated constant (a literal inside the utility's
  formula, such as NPCL's 6.5 % deposit rate, 1.0532 gross-up and 20 days) and a cell declared
  blank-as-zero.  **NPCL: P3 / F31 38 / 38 — bad debts 12.44 (APR) and 13.76 (ARR) as the ARR's row
  41, other items 5.43 (true-up) as row 45, revenue from loss reduction 2.58.  Security deposit:
  the APR and ARR interest (23.26, 24.24) as F25 and the ARR's row 38; the true-up year's months
  match except March, which NPCL types (1.8901 against its formula's 2.0802).**  So the year's
  24.79 is 0.19 below what the balances give (24.98), reproduced as *differs* and never forced.
  It is finding A40, addressed to the reviewer: allow the amount disbursed.  Non-tariff income
  (F28) remains a record: its projections are typed (some items exactly +2 % a year, others not)
  and the format's totals are sums.  No rule is approved; every clause is unverified.

  **Increment 67 (2026-11-01): depreciation by class, five years, to the ARR's row 36.**  F24
  read as five row tables (one per year block), with 2 new draft rules: the implied rate (the
  format's identity, depreciation over the average gross block; not a regulation) and the net of
  consumer-contribution depreciation (C.DEP).  The engine can now take a **given figure for one
  category** (labelled `given`, feeding sums like a computed one).  Row tables gained shared
  inputs (a deduction printed below the total, or a stated constant, each with its reason), and a
  total can be checked against several cells.  **NPCL: FY2022-23 prints each class's rate, so its
  depreciation is computed (17 / 17, 54 / 54 in all).  For the later years the class figures are
  given and every roll-forward, implied rate, total and net matches.  The net equals the ARR's row
  36 in all five years: 62.09, 66.33, 74.75, 90.09 (APR), 106.75 (ARR).**  Two findings for the
  petitioner (`findings.json`):
  - **A38:** FY2023-24's rate column divides by the net block, unlike the other years.
  - **A39:** the projection years' class depreciation cannot be derived from what was filed.
    Annexure-21 rolls only the existing assets forward (111.39 against F24's 121.04 for
    FY2025-26).  The excess fits half a year on the additions for some classes (0.50) but not
    others (about 0.40), and no single fraction in FY2026-27.
  So the APR and ARR depreciation reproduces from F24's class figures but not yet from the
  capital plan.  No rule is approved; every clause is unverified.

  **Increment 66 (2026-11-01): O&M of the APR and ARR years under the 2025 regime.**  12 draft
  rules: R&M as a share of the opening gross block by vintage (5 % on Part A, assets to
  31.03.2020, and Part B, 01.04.2020–31.03.2025; 3 % on Part C, new assets, and on the GNIDA
  hand-over — as NPCL's F22 applies them, the clauses to be confirmed); and employee and A&G
  expenses from a **base year**.  The base year is the average of five years' actuals
  (FY2020-21 to FY2024-25) as the middle year (FY2022-23), escalated year by year by the CPI
  (employee) or WPI (A&G and captive consumption) increase.  Employee expenses then grow by the
  average growth of sales, consumers and employees; A&G excludes finance charges and includes
  captive consumption.  NPCL computes this on a sheet the reference reader does not cover
  (`F19_O&M_EE n AG base`), so a new **`cells` binding** reads workings by cell address.  Each
  evaluation names its year, its input cells and every cell its result is checked against, on
  the sheet and wherever the figure is carried.  A blank input is absent and blocks; it is never 0.
  **NPCL: F19 base 40 / 40 — employee 95.63 (FY2025-26) and 99.98 (FY2026-27), A&G 28.75 and
  29.25, each equal to F21, F23 and the ARR's rows 27 and 31; F22 R&M 100.26 and 113.69, equal to
  ARR row 26 (4 / 4); F22's parts 2 / 2 each.**  The chain still takes these lines as records;
  the ties show that the records equal what the draft rules compute.  The true-up year's F21 and
  F23 totals are sums of audited ledger lines — records by nature, not normative computations.
  Employee capitalisation of the APR and ARR years comes from the capital plan (F13, rows 97 and
  125), still a record.  No rule is approved; every clause is unverified.

  **Increment 65 (2026-11-01): power purchase by source.**  9 draft rules evaluated per source
  (amount = fixed + energy charges, transmission = PGCIL + UPPTCL, total, the rate at the bus bar
  and the cost per unit at NPCL's bus — Rs crore over MU in Rs/kWh by the units, no hand-written
  factor) and their totals, which are the ARR's power purchase (C.PP) and transmission (C.TX) lines.
  A `row_table` binding reads a table whose rows are categories (one per source) by cell address,
  declaring with its reason the blanks of charges-only rows.  The engine now **blocks** an output
  whose formula divides by zero (a REC purchase has no energy, so no rate) instead of failing —
  never a 0.  **NPCL: PPC FY 27 129 / 129 — cost of power procurement 2,448.33, transmission
  446.36, energy 5,066.34 MU (the Energy Balance's purchase); PPC FY 26 156 / 157.**  The true-up
  year's summary (PPC FY 25) is a billed format with other charges and a rebate — next.

  **Increment 64 (2026-11-01): the reproduction in the product, for the reviewer.**  API (read-only,
  analyst and above): `GET /arr/rules/{commission}` (every calculation rule with its status, clause,
  verification, years and examples — UPERC: 68 rules, **0 approved, 0 clauses verified**),
  `GET /arr/reference-filings` and `GET /arr/reference-filings/{id}` (documents and hashes, each
  format's reproduction with what does not match, the chain by column with FY2026-27 computed
  against filed, the utility's workings and their ties, and the findings — `findings.json`, five,
  each addressed to the petitioner or the reviewer).  Desk pages `/arr/reference`,
  `/arr/reference/<id>`, `/arr/rules/<commission>` (a warning banner while nothing is approved);
  "Reference filings" in the Desk menu.  Both Dockerfiles now ship `packages/arr-rules` and
  `packages/reference-filings` (the sandbox one had been missed — found by the screenshot).
  Checked by screenshots at 1440 and 390 px (no horizontal scroll).  2 integration tests.

  **Increment 63 (2026-11-01): the chain — NPCL's petition computed end to end.**  One binding
  (`chain-arr.json`) evaluates, for every column of the ARR format, the whole rule set from base
  records only: capital (F14) → normative equity and return (F26) and normative loan and interest
  (F25); O&M → working capital and its interest (F27); RoE → income tax (F29); everything → the
  ARR summary, the gap and its carrying cost.  The engine gained **given outputs** (a filed figure
  standing in for a schedule, labelled `given`, never counted as reproduced), so the per-format
  bindings keep working beside the chain; the ARR summary (v2), income tax (v2) and working capital
  (v2) take their components from the schedule rules.  **Result: the petition's three columns —
  FY2024-25 claimed (true-up), FY2025-26 estimated (APR), FY2026-27 projected (ARR) — reproduce in
  full, 36 of 36, net ARR 3,481.83 and gap 289.79 included.**  FY2023-24 carries the filing's own
  F14 / F25 / F26 inconsistency (A29); the Commission's columns are blocked for want of their own
  inputs.  The chain found a defect of mine: matching another format by the year alone had fed the
  Commission's FY2025-26 approval with NPCL's estimate — now opt-in for data-series formats only
  (A36).  **Still inputs, not yet computed:** power purchase and transmission (F1–F10, PPC), the
  O&M components of the APR / ARR years (F20–F23), depreciation of the projected years (F16 → F24),
  revenue (ESR), bad debts, interest on security deposit.  No rule is approved; every clause is
  unverified.

  **Increment 62 (2026-11-01): income tax (F29).**  4 draft rules: the return on equity grossed
  up for tax, the tax on the net taxable income, the tax on the grossed-up RoE, and the tax
  recoverable as the lesser of the two.  **NPCL's F29: 24 of 24**, every column.

  **Increment 61 (2026-11-01): the ARR summary itself.**  11 draft rules for UPERC's ARR format:
  net employee expenses, net O&M, total expenditure, deductions, **net ARR**, the gap before and
  after the tariff revision and the subsidy, the unrecovered gap, its **carrying cost** (half-year
  convention: accumulated gap + half the year's; a shortfall carries the working-capital rate, a
  surplus 75 % of a deposit rate — the rule language gained one conditional, `ifneg(test, then,
  otherwise)`, both branches of one dimension) and the cumulative gap.  Bindings can declare
  per-year constants with their source (rates typed inside the petitioner's formulas) and states
  that add nothing to a sum ("Incl. in A&G", "NA"), each with its reason.  **NPCL's ARR format: 106
  of 121 figures reproduced from its component lines; the petition's own columns — FY2025-26
  estimated and FY2026-27 projected, net ARR 3,481.83 and gap 289.79 — in full.**  What differs:
  the Commission's restated approvals carry a **surplus at the full carrying rate** (FY2024-25:
  × 11.05 %, Rs 122.34 crore) where NPCL's columns use 75 % of a deposit rate (Rs 56.05 crore) —
  a regulatory-treatment question for the reviewer (ledger A35); NPCL's audited FY2023-24 carrying
  cost copied from the claimed column; typed restated figures 0.01 off; one sum on a half.

  **Increment 60 (2026-11-01): normative O&M — the CPI / WPI escalation chain.**  9 draft rules:
  the annual price index (average of twelve months), its increase, the escalation factor (average
  of the three preceding increases), each O&M component escalated from the previous year (employee
  on CPI; A&G, finance charges, DPS carrying cost, GST and R&M on WPI), the A&G total, gross and net
  O&M, the additional R&M for standards of performance (50 %) and the total.  Bindings can reach
  earlier columns (`"22@-1"`: the same row a year before) and, across formats, match a year printed
  in another voice when that format has one column for it.  **NPCL: F17 CPI 15 / 15 and F18 WPI 15 /
  15 of what the sheets can compute; F19A's six components 24 / 24 escalations and its totals 25 /
  25 — nothing differs.**  Blocked only where the sheet lacks the inputs.  Two findings: NPCL's F18
  prints its ARR column as "FY 2025-26" (A33, kept as printed, never guessed); and the reader's
  displayed value rounded half-to-even where spreadsheets show half-up (A34, fixed — found by this
  reproduction).  The reader also tells a serial by its shape, not its length ("May" is a label).

  **Increment 59 (2026-11-01): the reference rates from the SBI MCLR revisions.**  5 draft rules:
  per MCLR period (a category) its days and rate × days; the year's day-weighted MCLR; the true-up
  working-capital rate (+2.5 %, to FY2024-25) and the normative-loan rate (+1 %, from FY2025-26).
  A `period_table` binding reads a table of periods by cell address from the filed workbook and
  checks the derived rates against the cells the formats print them in.  **NPCL: the weighted MCLR
  of FY2024-25 (0.088822) and FY2025-26 (0.088262), the true-up rate (0.113822, F27 E35) and the
  loan rate F25 applies (0.098262, F25 H14) — 4 of 4 to six decimals.**  Margins are as NPCL
  applies them; the clauses are to be confirmed.

  **Increment 58 (2026-11-01): interest on working capital (F27) — where the conventions part.**
  6 draft rules: O&M for a month; receivables of 1.5 months (NPCL's projection basis, tariff +
  open-access revenue, from FY2025-26; in a true-up year the receivables are the petitioner's
  record, an input); normative working capital floored at zero; net of an opening surplus; interest
  floored at zero.  The harness now reports `given` when a year's rule takes the very row it would
  check as its input (nothing reproduced, nothing counted), and a binding can declare a deduction
  printed negative.  **NPCL's F27: 34 match, 7 given, 7 differ, 2 blocked** — the ARR and APR years
  in full; the differences are explained: the restated FY2022-23 true-up uses a monthly O&M (13.46)
  the ARR format's trued-up O&M does not give (159.88 / 12 = 13.32); **the Commission's FY2025-26
  approval takes receivables on tariff revenue alone, NPCL adds open-access revenue** (370.25 ×
  12 / 1.5 = 2,962.0, the approved net revenue); the FY2024-25 audited surplus is blank in the
  filing.  Ledger A32.  The reference rate (SBI MCLR weighted by days for a true-up + 2.5 %; the
  MCLR on a date + 2 % for the ARR; + 1 % for the loan) is the next rule.

  **Increment 57 (2026-11-01): depreciation by asset class and vintage, tied to the filed ARR.**
  The rule engine evaluates rules **per category** (`per: "asset_class"`) on each category's own
  values and sums them with `sum:<output>`; one category missing an input blocks the sum and names
  the category.  `arr/blocks.py` reads year-block workings (one block per year side by side;
  columns named by their header words; blanks absent).  5 draft depreciation rules (closing and
  average gross block, depreciation = average × class rate, accumulated depreciation, total).  On
  NPCL's own depreciation workings (Annexure-21, added to the reference folder; its hash is the
  one recorded for the package): **assets after 1 April 2020 — 686 of 686 figures; before 2020 —
  672 of 686** (land: NPCL depreciates on a base excluding non-depreciable land rights, a class
  exception the draft lacks; one office-equipment year unexplained; two classes with no rate);
  and **the net — own assets less consumer-contribution assets, both vintages — equals the
  depreciation in NPCL's filed ARR format and the loan repayment in F25 for every true-up year**
  (FY2021-22 56.37, FY2022-23 62.09, FY2023-24 66.33, FY2024-25 74.75).  The workings' FY2025-26
  and FY2026-27 blocks carry the existing assets only; the projections (90.09, 106.75) add the
  planned capitalisation — the next link.  Ledger A30, A31.

  **Increment 56 (2026-11-01): the capital schedule (F14) and cross-format reconciliation.**
  The reference reader takes the label wherever the format puts it (F14 has sub-letters in column
  B and labels in C; 2,085 values now).  11 draft capital rules: gross block roll-forward,
  capitalisation net of consumer contribution, the normative **70:30** debt and equity, and the
  retirement chain (written-down value, its share, equity retired up to 30 % and the rest from the
  loan from FY2025-26; for FY2023-24/24-25 NPCL retires the whole WDV from equity — two regimes,
  as the filing applies them).  The equity and loan roll-forwards (v2) now take their additions and
  reductions from these rules.  Bindings can name a row of **another format** (`"F14_CAP_Cap
  Cost!27"`, matched by year and voice) and can declare, with a reason, a blank the petitioner's
  formula reads as zero (never assumed).  **Results:** F14 reproduced in full (60 of 60); the
  Energy Balance still 55 of 55; F25/F26 computed from F14's inputs match in every column F14
  covers **except FY2023-24 "Claimed", where NPCL's own formats disagree** — F26 adds equity of
  21.21 and F25 a loan of 49.49 where F14 gives 30 % / 70 % of its net capitalisation (22.73 /
  53.04), and F26 retires no equity where F14 retires 1.53 (ledger A29; a question for the
  petitioner and the reviewer, not resolved by the build).  Columns F14 does not have (FY2022-23,
  the Commission's approval) are blocked.  From the openings and the year's F14 records alone the
  chain reproduces NPCL's FY2026-27 RoE (115.77) and interest on loan (83.88).

  **Increment 55 (2026-11-01): reproducing filed formats through the rules — the energy balance
  and the capital chain.**  `arr/reproduce.py` + `scripts/reproduce_formats.py`: a **binding**
  per filed format (`packages/reference-filings/<filing>/bindings/`) names its input rows and its
  output rows; every column (year × voice) is computed from the input rows through that year's
  rules and each output compared with the filed figure at its printed precision — `match`,
  `differs`, `blocked` (with the reason), or `not_a_value`.  The reference reader now uses a
  sheet's own **Units column** (the Energy Balance prints MU / % per row).  5 draft energy-balance
  rules (definitions: loss quanta, requirement at the distribution and state periphery, implied
  inter-state loss).  **Result on NPCL's FY2026-27 filing: 97 of 97 bound figures match** — the
  Energy Balance in all 11 columns (FY2021-22 to FY2026-27, the Commission's restated approvals
  and NPCL's claims alike), F25 interest on the normative loan and F26 return on equity in all 7.
  What this proves and what it does not: the draft rules compute what the petitioner computed
  from the format's own input rows; the inputs' derivation from NPCL's records (billing
  determinants, PPC, F14 capitalisation, F24 depreciation) is the next stage, and no rule is
  approved.  A unit test reproduces the real formats as a regression (no database: the reference
  and the rules are files).

  **Increment 54 (2026-11-01): the rule engine — regulations as executable, versioned rules.**
  `arr/rules.py` + `packages/arr-rules/` (R-RULE-1..4, R-NUM-1..4).  A rule is data: one output,
  typed inputs (fact / record / assumption / another rule / last year / a regulation parameter
  with its value), a formula in a restricted language (parsed with `ast`; only numbers, names,
  `+ - * /`, `avg min max sum`), rounding policy, clause (regulation, clause, page, excerpt,
  `verified`), applicability by year, worked examples, approver.  Evaluation is in Decimal with
  units and dimensions (Rs crore / MU gives Rs/kWh with no hand-written factor; money + energy is
  refused at load), in dependency order (cycles refused), choosing rules **per year** (two
  regimes in one petition), and a missing input **blocks with its reason** — never a default.
  `filing_ready` only when every rule used is approved on a verified clause.  **First UPERC
  drafts** (12 rules: normative equity, return on equity, normative loan, interest on it) for
  the two regimes UPERC's FY2026-27 NPCL order names (p.12): the 2019 MYT Regulations (to
  FY2024-25; RoE 15 % cited from the order's quotation of Regulation 22, p.151) and the 2025 MYT
  Regulations (from FY2025-26, applicability a draft assumption; 15 % as applied in the order,
  p.204).  Worked examples are NPCL's exact stored values; **from openings and the year's
  records the chain reproduces NPCL's filed FY2026-27 RoE (115.77) and interest on loan (83.88)**.
  Every rule is a draft, every clause unverified.  Also: the float defect in the XLSX exports
  (R-NUM-1) is fixed — Decimals written as exact numbers.  19 unit tests.

  **Increment 53 (2026-11-01): milestone 13 begins — the NPCL FY2026-27 reference filing, and
  the first measurement of an order reading against a filed petition.**  After the operator's
  review of the master prompt: the binding `docs/arr-filing-requirements.md` (proposed),
  `docs/requirements-matrix.md` and ADR-0021 (proposed).  The operator supplied NPCL's
  FY2026-27 petition package (zip in `gs://npcltariffpetition`, 405 MB; read through a
  2-hour signed link they generated): **69 documents hashed** into
  `packages/reference-filings/uperc-npcl-fy2026-27.json` (Annexure-34, -40 absent; Annexure B,
  power-purchase bills, ~2.5 GB, held by the operator); the repository keeps the filed formats
  workbook and the Word narratives (5 MB).  The FY2025-26 petition is listed too (87
  documents, not downloaded: served on port 8032, unreachable from the cloud session).
  - **Reference reader** (`arr/reference.py`): a filed format sheet → rows with proposed
    taxonomy placements; per column the year and voice (a year printed once carries over its
    group; "Trued-Up" / "Approved (in TO)" are the petitioner's **restatement**, never commission
    facts from this source); per cell the stored value, the displayed value (its number
    format; a percentage stored as a fraction converted and said so), or a state ("Incl. in
    A&G" → included, "NA" → not applicable — never zero).  Several rows proposed for one code
    are flagged.  `scripts/build_reference.py` wrote `reference.json` (24 of 74 forms read by
    the generic reader, 2,012 values; the other 50 — station-wise power purchase, tariff
    schedules, snapshots, depreciation — need their own readers, in the pipeline sequence) and
    `formats-inventory.json` (the 74 forms as observed in this filing).
  - **Measurement** (`tests/evals/reference_vs_order.py`, read-only, inside the worker): the
    UPERC FY2026-27 order's reading against NPCL's filed ARR format, the three years the order
    decides — **129 figures: 57 exact (44 %); 18 explained** (6 combined totals: the order's
    power purchase = NPCL's procurement + arrears; 6 opposite signs on the gap; 1 voice; 5 where
    the *reference* placement was wrong — "Sale of Power" proposed as surplus sale, the order
    reading had it right as retail sales); **21 differ** (revised claims or misplaced rows, to
    investigate); **33 not read** (net ARR, total expenditure and NTI in some years — a recall
    gap or lines the order does not print).  Placements are unreviewed on both sides: an
    indicator, not an accuracy figure.  Ledger rows A25–A28.
  - 3 unit tests (synthetic rows in the format's shape).

  **Increment 52 (2026-11-01): the atlas — from the map of India to a petition — and day mode**
  (operator request: start with a map of India, then clickable states, then discoms, then the
  discom's tariff norms, then the steps to draft a petition; add a day mode).  The journey is
  written down in [`docs/user-journey.md`](user-journey.md).
  - **API** (read-only, analyst and above): `GET /atlas` (every state and union territory: its
    commissions, licensees, library documents located of those expected, real orders whose ARR is
    being read, reviewed ARR facts, and whether it is fixture data); `GET /atlas/states/{code}`
    (its commissions and each licensee with the same counts and the latest reviewed year);
    `GET /atlas/licensees/{code}` (where a licensee sits, for the way back up); `GET
    /arr/norms/{commission}` — the regulations the commission's ARR mapping names and those in
    the library with their reading level; the conventions (return basis, gap convention, loss
    basis, inclusive totals) as the mapping states them **and** as a reviewer has decided them;
    the method of every ARR line of the formulation plan in words, with the parameters the
    petitioner supplies (named, never valued); and **the norms as the orders applied them** —
    per licensee, the latest reviewed approved / trued-up figure of the distribution loss, O&M,
    RoE, interest on working capital, depreciation and loan interest, each with its order and
    page.  Only published reviewed facts; nothing is derived or invented.  A plan or mapping a
    reviewer has not confirmed is reported as such (`plan_confirmed`, `mapping_confirmed`), and
    a commission without its own plan shows the generic plan by its id.
  - **Web:** `/client/atlas` — India as a **tile map** (one equal tile per state/UT in its
    approximate place, coloured: reviewed facts / orders being read / documents located /
    nothing yet; deliberately not a boundary map — official boundaries need the Survey of
    India's) beside a list of states; the headline counts are of real records only and the
    synthetic jurisdiction is listed last, labelled fixture.  `/client/states/<code>` — the
    licensees as cards, a norms summary per commission, the five drafting steps with "Start for
    <discom>".  `/client/norms/<commission>` — the full norms with a **working estimate**
    banner while unconfirmed.  The licensee page gains the journey trail and a **Tariff norms**
    panel (the applied norms of that licensee).  Every atlas page shows the trail India → state
    → discom → norms.  The studio home links to the atlas and its state grid opens the state.
  - **Day mode:** a light token set (`:root[data-theme="light"]`, and the system's preference
    when no choice is made); the accent stays a fill and turns deep olive where it is text
    (`--accent-text`), all tones re-tinted for white.  A Day/Night toggle in the top bar sets a
    `theme` cookie that the server reads, so the first paint is in the chosen theme.  The last
    hard-coded colours (header glass, menu shadow, benchmark highlight) became tokens.
  Checked by screenshots of the atlas, two states, a licensee, a norms page and the home at
  1440 px and 390 px in both themes; no horizontal scroll measured at 390 px.  **What it shows
  today is honest and thin:** in the build session's stack all 605 library slots are
  `expected` (no URL located), the ten real orders are being read (none reviewed, a human
  boundary), so every real state shows 0 reviewed facts and every norm is a working estimate;
  the 44 reviewed facts are the synthetic fixture's.
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
- `local` in Docker, 2026-10-13, cloud build session: `make dev-sandbox` (sandbox Dockerfiles: Ubuntu
  24.04 base, CPython 3.11.14 via uv, tesseract 5.3.4 — bookworm images cannot be built there:
  Debian mirrors and the ghcr.io blob CDN are blocked, Docker Hub rate-limits).  postgres, migrate
  (head `0014_order_type_licensee_kind`), api (`/readyz` ready), worker and web all up; one
  SYNTHETIC fixture (`SYNTHETIC_mixed_text_and_image.pdf`, dataset `fixture`) went inventory →
  triage → parse → localise and waits at the reviewer checkpoint (left for a human).  The
  operator's VM data (DB and object store) is not in this stack.
  Postgres comes from `mirror.gcr.io/pgvector/pgvector:pg16` (Docker Hub answers 429 there),
  which reported pgvector 0.8.7 on 2026-10-13 where the VM reports 0.8.6.
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
                                  # `make dev` host ports: WEB_PORT/API_PORT/POSTGRES_PORT (default 3000/8000/5432)
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
- Migration `0022_petition_workbooks` (increment 151): a case's formats workbooks, inputs and
  filled; routes `/cases/{id}/petition/…`; job type `petition_fill`.
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
- **Real orders read in the build session's local stack (dataset `real`, read-only to
  `chapters_proposed`; the local stack is ephemeral):** NPCL FY2026-27 (UPERC) `ff36813e…`, 423
  pp.; NBPDCL + SBPDCL FY2026-27 (BERC) `a247053b…`, 612 pp.; HPSEBL FY2026-27 (HPERC)
  `0f3d9e9d…ec74`, 525 pp.; JBVNL MYT/true-up/APR 2026 (JSERC)
  `0391dd2701c7bbb7a962923212ef5a8ed6c9cdfbfea601df692d7ce4aa119108`, 372 pp.
- **Increment 47 adds:** TP DISCOMs FY2026-27 (OERC)
  `d58d281787d4dd34e7b895add2e7cb37dbf3b9e8d5f1a1ea208dc57ceffde0ab`, 246 pp.; MP State DISCOMs
  FY2026-27 (MPERC) `77ffe9d2e48277354348b32ab3a90d74639a4b406757ae8e658197bd79f91afb`, 255 pp.;
  UPCL FY2026-27 (UERC) `1a9299178035d9e9460733256419710b2c3d5d7cc98b3703be60130aea99eb91`, 414 pp.
- **Increment 50 adds:** TP DISCOMs FY2025-26 (OERC)
  `de53fe6fc5afb70f9f45e2eb94a977bcbd2c791fe63eb9f713f8b9ab2fc069fb`, 169 pp.; MP State DISCOMs
  FY2025-26 (MPERC) `66254f461e5d360d42d6216aaf824e0baa8bdab943248aeb241c34940b2693c2`, 259 pp.;
  UPCL business plan and MYT order FY2025-26 (UERC)
  `5fc2d18f3b19793e67ecba4fe5bfc60b3e6b9401e20c418dc89255eb273bc41e`, 412 pp.
- Synthetic fixtures only (dataset `fixture`): `mixed_text_and_image_pdf` (6 pages), `text_only_pdf` variants, `not_a_pdf`.

## Reading reliability ledger changes

Increment 50 (A22–A24): a second year for three states; parts whose numbered headings are the
petition's; a one-page chapter list is no structure; a one-word cell over figures is no
heading; a merged-cell table read from the second table reader.  Ten real orders measured.

Increment 48 (sub-rows, A21): a value-less heading row gives its sub-rows their subject; a
previous year's gap is not this year's.  Uncovered by dropping blank candidates: a heading row
had hidden UERC's revenue.

Increment 47 (three more states, A16–A20): lettered parts, a licensee per row, three-level
sections in a long chapter, and two wrong readings found in MPERC's preview (a licensee
column's voice; a label's qualifier) fixed; a mixed-case registry code.  Seven real orders
measured; precision still needs reviewer decisions.

Increment 45 (loss basis, A15): BERC's within-state loss basis posed; a generic "inter-state
sales" alias was tried, found wrong on HPERC and NPCL by measurement, and narrowed to
cross-border sales.

Increment 44 (ARR conventions): A8 and A14 now pose their questions to the reviewer in the
mapping workbench, with the failing values as evidence; ARR-I1 honours a stated
`total_includes`.  JSERC's power purchase convention explains 4 of its 5 failures; the fifth is
unexplained.  No answer has been given: the conventions stay open until a reviewer decides.

Increment 43 (ARR, fourth real order): JSERC's paragraph-numbered layout (A12) — 74 chapters by
its "Chapter N" parts; running headers as captions, contained aliases naming another thing and
a unit-dependent alias (A13) — found by ARR-I4, which now passes on JSERC's energy balance; a
total that includes transmission (A14, open, a reviewer's mapping convention).  Measured:
128 of 292 tables, 470 values; four real orders measured; precision still needs reviewer
decisions.

Increment 39 (ARR, second real order): BERC's 612-page combined order — 36 chapters matching its
sections on first contact with rules v2; the reader took paragraphs above tables for captions
(years and voices from prose) — now only a table's own title counts.  Measured: 177 of 548
tables, 573 values attributed per licensee.  Two real orders measured; precision still needs
reviewer decisions.

Increment 38 (ARR, real order): the structure channel read 30 of 384 tables of the real order
(year in captions, voice by part, reference/unit columns, two-row headers, footnote marks);
rules arr-rules-2 read 188 with spot checks matching the printed summaries.  Not measured:
precision over all 657 values (needs the reviewer's decisions), any second real order.

Increment 37 (ARR, real order): chapter localisation over-fragmented a real 423-page order
(229 proposals for about 30 sections) — running headers, contents entries, captions, rows and
numbered prose read as headings.  Chapter rules v2 handle each; measured on that order: 30
proposals matching its numbered sections.  Not yet measured: any second real order.

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

- **Increment 155 (2026-11-10):** ARR 101 only. `node --test` passes 7 of 7 (calc, plus 64 formats: count, agreement, cross-consistency), and `tests/unit/test_arr101_uperc.py` passes 2 of 2 (43 quotes found on their pages).  The live site was checked in the browser: 64 formats, the workbook (65 sheets) downloads, no page errors.  The full Python suite was not rerun.  This increment changed no package source; it only deleted a script and changed the ARR 101 test file.
- **Increment 154 (2026-11-07): 547 passed** (+6 unit: every map cell labelled; hand-label quotes checked against the workbook; an order word in every order-quoted column's own header; the kept counts and named cells; a row range over its column; unprinted voices not kept.  The integration test checks the new counts).  Ruff and format clean; contracts regenerated; web `tsc --noEmit` clean.
- **Increment 153 (2026-11-05): 541 passed** (+15 unit: `render` in twelve printed styles; NPCL's nine tables refilled from the filing — 20 cells changed, the merged A56 cell left, 252 / 253 read back; a changed figure reaching all three tables; a missing document or table refused.  The integration test now also checks the kept cells, the narrative summary and its ZIP).  Ruff and format clean; contracts regenerated; web `tsc --noEmit` clean.
- **Increment 152 (2026-11-05):** web only — `tsc --noEmit` clean; checked in the browser against the running stack (template, upload, fill through the worker, results) at 1440 px and 390 px.  Python suite unchanged at 526.
- **Increment 151 (2026-11-05): 526 passed.**  The new integration tests, 2 / 2 (`test_petition_workbooks.py`, about 105 s), and the fill unit tests, 3 / 3.  Ruff and format clean; contracts regenerated.  **Full suite: 526 passed** (+2 integration), 8 min 41 s, local PostgreSQL 16 with pgvector.
- **Increment 150 (2026-11-05): 524 passed** (+3 unit: the fill's rules on a synthetic workbook, the fill map's limit, NPCL's round trip live).  Ruff and format clean.
- **Increment 149 (2026-11-03): 521 passed** (+1 unit: NPCL BS1, BS2, BS3; A93, A94; the accounting's `no_arithmetic`).  Ruff and format clean; web `tsc --noEmit` clean.
- **Increment 148 (2026-11-03): 520 passed** (+1 unit: NPCL P1A, P4, P5, P7, P8, P9, P11; A90–A92).  Ruff and format clean.
- **Increment 147 (2026-11-03): 519 passed** (+1 unit: NPCL F4, F5, F7, F8, F9, 106 checks exact).  Ruff and format clean.
- **Increment 146 (2026-11-03): 518 passed** (+1 unit: NPCL F1 and F3, 1,375 checks exact; A89).  Ruff and format clean.
- **Increment 145 (2026-11-03): 517 passed** (+2 unit: `root()` and its refusals; NPCL ESR1, ESR2, ESR5).  Ruff and format clean.
- **Increment 144 (2026-11-03): 515 passed** (+1 unit: NPCL F11, F12, F13, all exact).  Ruff and format clean.
- **Increment 143 (2026-11-03): 514 passed** (+1 unit: NPCL F28 and F20; one integration assertion now expects non-tariff income tied, not a record).  Ruff and format clean.
- **Increment 142 (2026-11-03): 513 passed** (+2 unit: JSERC capital chain with J1, J2; JSERC ARR end to end).  `check_order_quotes.py`: 207 / 207.  Ruff and format clean.
- **Increment 141 (2026-11-03): 511 passed** (+1 unit: HPERC's O&M from its parts; H3, H4).  `check_order_quotes.py`: 55 / 55.  Ruff and format clean.
- **Increment 140 (2026-11-03): 510 passed** (+1 unit: an amended rule by effective year, synthetic).  Ruff and format clean.
- **Increment 139 (2026-11-03): 509 passed** (+1 integration: the rules compared across commissions).  Ruff, format, contracts (regenerated, no drift) and `tsc` clean; screenshots at 1440 / 390 px.
- **Increment 138 (2026-11-03): 508 passed** (+1 unit: OERC's bad debts, RoE and depreciation for four DISCOMs; O1, O2).  `check_order_quotes.py`: 76 / 76.  Ruff and format clean.
- **Increment 137 (2026-11-03): 507 passed** (+1 unit: BERC's working capital per DISCOM).  The first full run failed this test on the claimed interest's bound; it now bounds by the printed rate.  `check_order_quotes.py`: 43 / 43.  Ruff and format clean.
- **Increment 136 (2026-11-03): 506 passed** (+1 unit: JSERC's MYT working capital, nil for negative years).  `check_order_quotes.py`: 40 / 40.  Ruff and format clean.
- **Increment 135 (2026-11-03): 505 passed** (+1 unit: HPERC's working capital and ARR arithmetic, H1, H2).  `check_order_quotes.py`: 85 / 85.  Ruff and format clean.
- **Increment 134 (2026-11-03): 504 passed** (+1 integration: the reproduced orders' API — counts, gaps, findings, 404s, authentication).  Ruff, format, contracts (regenerated, no drift) and `tsc` clean.
- **Increment 133 (2026-11-03): 503 passed** (+1 unit: MPERC's wheeling / supply split per DISCOM, M4).  `check_order_quotes.py`: 96 / 96.  Ruff and format clean.
- **Increment 132 (2026-11-03): 502 passed** (+1 unit: MPERC's escalation, O&M and inventory base).  `check_order_quotes.py`: 83 / 83.  Ruff and format clean.
- **Increment 131 (2026-11-03): 501 passed** (+1 unit: MPERC's ARR per DISCOM, the table and end to end).  `check_order_quotes.py`: 144 / 144.  Ruff and format clean.
- **Increment 130 (2026-11-03): 500 passed** (+1 unit: MPERC's depreciation, loan and equity chain per DISCOM, bounded by printed precision; M3).  `check_order_quotes.py`: 138 / 138.  Ruff and format clean.
- **Increment 129 (2026-11-03): 499 passed** (+1 unit: MPERC's working capital per DISCOM, M1–M2; two earlier tests updated for half-up checks).  `check_order_quotes.py`: 72 / 72.  Ruff and format clean.
- **Increment 128 (2026-11-03): 498 passed** (+1 unit: UERC's true-up gap carried into the ARR year — exact from the printed gap, bounded end to end).  `check_order_quotes.py`: 62 / 62.  Ruff and format clean.
- **Increment 127 (2026-11-03): 497 passed** (+1 unit: UERC's true-up loss valuation and sharing; the 2021 / 2024 year selection; U6).  `check_order_quotes.py`: 49 / 49.  Ruff and format clean.
- **Increment 126 (2026-11-03): 496 passed** (+1 unit: UERC's revenue requirement and surplus end to end, to the paisa).  `check_order_quotes.py`: 38 / 38.  Ruff and format clean.
- **Increment 125 (2026-11-03): 495 passed** (+1 unit: UERC O&M, the approved side within printed precision, UPCL's claim against U3–U5).  `check_order_quotes.py`: 50 / 50.  Ruff and format clean.
- **Increment 124 (2026-11-03): 494 passed** (+1 unit: UERC depreciation, loan and interest, differences bounded by printed precision; the chain's ties).  `check_order_quotes.py`: 52 / 52.  Ruff and format clean.
- **Increment 123 (2026-11-03): 493 passed** (+1 unit: UERC's working capital and RoE for UPCL — a second commission, no workbook; U1).  `check_order_quotes.py`: 41 / 41.  Ruff and format clean.
- **Increment 122 (2026-11-03): 492 passed** (+1 unit: gain / loss sharing — the examples, the year selection, the illustration).  `check_order_quotes.py`: 12 / 12.  Ruff and format clean.
- **Increment 121 (2026-11-03): 491 passed** (+1 unit: the wheeling / supply allocation).  `check_order_quotes.py`: 62 / 62.  Ruff and format clean.
- **Increment 120 (2026-11-03): 490 passed** (+1 unit: the open access charges and surcharge).  `check_order_quotes.py`: 159 / 159.  Ruff and format clean.
- **Increment 119 (2026-11-03): 489 passed** (+1 unit: the RCO).  `check_order_quotes.py`: 25 / 25.  Ruff and format clean.
- **Increment 118 (2026-11-03): 488 passed** (+1 unit: the true-up's power purchase by source).  `check_order_quotes.py`: 78 / 78.  Ruff and format clean.
- **Increment 117 (2026-11-03): 487 passed** (+1 unit: NPCL's APR estimate table, its arithmetic and the 2.47 moved).  Ruff, format and `tsc` clean.
- **Increment 116 (2026-11-03): 486 passed** (+1 unit: the true-up's energy balance and the 1.32 MU).  `check_order_quotes.py`: 40 / 40.  Ruff and format clean.
- **Increment 115 (2026-11-03): 485 passed** (+1 unit: the energy balance, both columns).  `check_order_quotes.py`: 26 / 26.  Ruff and format clean.
- **Increment 114 (2026-11-03): 484 passed** (+1 unit: the ARR year's power purchase by source, differences bounded by input precision, tied to Table 6-35).  `check_order_quotes.py`: 154 / 154.  Ruff and format clean.
- **Increment 113 (2026-11-02): 483 passed** (+2 unit: aliased records and one figure less another, synthetic; the APR's depreciation exactly).  Ruff and format clean.
- **Increment 112 (2026-11-02): 481 passed** (+1 unit: the true-up's bad debts and non-tariff income).  `check_order_quotes.py`: 16 / 16.  Ruff and format clean.
- **Increment 111 (2026-11-02): 480 passed** (+1 unit: the ARR year's working capital).  `check_order_quotes.py`: 17 / 17.  Ruff and format clean.
- **Increment 110 (2026-11-02): 479 passed** (+1 unit: the fixed charges against the billable-demand floor).  `check_order_quotes.py`: 20 / 20.  Ruff and format clean.
- **Increment 109 (2026-11-02): 478 passed** (+2 unit: unexplained and stale lines listed, deductions, blank approvals and misprints, synthetic; the three real decisions fully explained).  Ruff, format and `tsc` clean.
- **Increment 108 (2026-11-02): 476 passed** (+2 unit: summed shared cells with their reason, synthetic; the real regulatory discount in two years).  Ruff and format clean.
- **Increment 107 (2026-11-02): 474 passed** (+1 unit: the tariff design summary, differences bounded by the inputs' precision).  `check_order_quotes.py`: 76 / 76.  Ruff and format clean.
- **Increment 106 (2026-11-02): 473 passed** (+1 unit: the gap and its carrying cost — NPCL's format and the order on one rule; the working-capital offset and the closings tied).  `check_order_quotes.py`: 34 / 34.  Ruff and format clean.
- **Increment 105 (2026-11-02): 472 passed** (+1 unit: the real APR — 11 / 13, ties to the true-up and the ARR year).  `check_order_quotes.py`: 57 / 57.  Ruff and format clean.
- **Increment 104 (2026-11-02): 471 passed** (+3 unit: wrapped labels joined and the decision per line, synthetic; Table 4-52 real; the excess energy reproduced).  `check_order_quotes.py`: 15 / 15.  Ruff, format and `tsc` clean.
- **Increment 103 (2026-11-02): 468 passed** (+1 unit: the real true-up depreciation — 24 classes, gross and net match; the order's non-adding row pinned).  `check_order_quotes.py`: 205 / 205.  Ruff and format clean.
- **Increment 102 (2026-11-02): 467 passed** (+1 unit: the real true-up capital and working capital — working capital exact, the equity-deletion rule's departure shown, the rest within a unit).  `check_order_quotes.py`: 38 / 38.  Ruff and format clean.
- **Increment 101 (2026-11-02): 466 passed** (+1 unit: the real true-up O&M — indices and their increases exact, R&M exact, every figure within one unit).  `check_order_quotes.py`: 69 / 69.  Ruff and format clean.
- **Increment 100 (2026-11-02): 465 passed** (+3 unit: a table with blank cells read by word position, a dash in a label kept as text; a source table's arithmetic per side; the real Table 6-35 — 51 rows, approved side 100 %, the order's three claimed-side slips).  Ruff, format and web typecheck clean.
- **Increment 99 (2026-11-02): 462 passed** (+2 unit: the real depreciation by class — 36 / 36 classes, the rest within two last-place units; a zero printed as "-" accepted, and only so).  `check_order_quotes.py`: 183 / 183.  Ruff and format clean.
- **Increment 98 (2026-11-02): 460 passed** (+1 unit: the real capital and interest approval, 13 / 14 with RoE 113.28, loan interest 85.60, tax 38.10, security deposit 20.51.  Changed: the decisions tests expect the new ARR identity, skipped where a column prints none of its parts, and the one column where the order's lines do not add up, −0.38, A61).  `check_order_quotes.py`: 28 / 28.  Ruff and format clean.
- **Increment 97 (2026-11-02): 459 passed** (+2 unit: a chain of years carried unrounded between evaluations and checked against an order figure, a computed input naming no evaluation refused; the real O&M approval — employee 87.63, A&G 28.87, R&M 111.04, one intermediate year one unit off).  `check_order_quotes.py`: 34 / 34 order figures, 58 / 58 rates.  Ruff and format clean.
- **Increment 96 (2026-11-02): 457 passed** (+4 unit: rows read by serial number across a page header, with their quotes; a short row read only where the spec names its columns; a column override; the claimed column against the format, the decision, the order's own arithmetic; the real three tables — claimed within two last-place units, arithmetic 16 / 16, ARR decision +29.51; the integration test checks the API's decisions block).  Ruff, format and web typecheck clean.
- **Increment 95 (2026-11-02): 453 passed** (+2 unit: a pipeline column fed from another only with a reason, never in a cycle or from a column the pipeline lacks; the real roll-forward 7 / 7.  Changed with the design: the pipeline tests expect the ARR and APR years at 10 / 12 with A40's effect carried, 0.22 and 0.25).  Ruff, format and web typecheck clean.
- **Increment 94 (2026-11-02): 451 passed** (+4 unit: every checklist quote on its page of the committed regulation; a checklist without a hash, evidence without a reason or a text without its weight refused; grading — a mention never enough, "Appendix-I" not "Appendix-II", a document without its bytes not present; NPCL's result; the integration test checks the API's checklist block).  Ruff, format and web typecheck clean.
- **Increment 93 (2026-11-02): 447 passed** (+6 unit: figures parsed as printed; traced / near / opposite sign / untraced, a two-digit figure never traced; a DOCX's merged cell kept once with its title; a summary table bound with sums, signs and dashes; a binding refuses an unknown table, a wrong header, a row matched twice; the real nine tables 232 / 21; the integration test checks the API's narrative block).  Ruff, format, contracts and web typecheck clean.
- **Increment 92 (2026-11-02): 441 passed** (+2 unit: a kVAh rate fed to the per-kWh energy rule blocks, never a revenue; the quote checker on a PDF made in the test finds quotes and column headers, and reports a wrong page, a missing header and another document; the real-data test adds ESR4A 47 / 47 and the 58-rate record).  `scripts/check_order_quotes.py` on the real order: 58 / 58.  Ruff, format and contracts clean.
- **Increment 91 (2026-11-02): 439 passed** (+3 unit: a rate record refuses a figure not in its quote, a rate with no page and a record with no hash; a cell takes the order's rate with its time-of-day percentage, and a rate the record lacks is an error; the real ESR-3 from the order's schedule — 40 / 45 match, the five differing rows are A53 and A54).  `scripts/check_order_quotes.py` on the real order: 36 / 36 quotes on their pages.  Ruff, format and contracts clean.
- **Increment 90 (2026-11-02): 436 passed** (+1 unit: the real 2025 Regulations — hash as in the manifest; RoE → p.31 with 15 %, R&M → p.43, bad debts → p.45, surcharge → p.48; a 2019-only rule not offered the 2025 text; nothing verified).  Ruff and format clean.
- **Increment 89 (2026-11-02): 435 passed** (+1 unit: pages ranked for a rule, the value-and-words page first, words alone or a bare number not proposed; the CLI on a PDF made in the test writes proposals with the hash and verifies nothing; the integration test checks the rules carry their candidates).  Ruff, format and web typecheck clean.
- **Increment 88 (2026-11-02): 434 passed** (the end-to-end test checks the true-up capitalisation from its schemes, 4 / 4).  Ruff and format clean.
- **Increment 87 (2026-11-01): 434 passed** (+1 integration: the draft queries are Markdown, labelled a draft, with the petitioner's questions by id and the Commission's points apart; unknown filing 404).  Ruff, format, contracts (regenerated) and web typecheck clean.
- **Increment 86 (2026-11-01): 433 passed** (+1 unit: the distribution loss carried across formats, P1_DL differing in three years).  Ruff and format clean.
- **Increment 85 (2026-11-01): 432 passed** (+1 unit: ESR4 and the revision impact).  Ruff and format clean.
- **Increment 84 (2026-11-01): 431 passed** (+1 unit: PPC FY 24 in four parts tied to the ARR's FY2023-24 rows 8, 20, 22, 23, 24).  Ruff and format clean.
- **Increment 83 (2026-11-01): 430 passed** (+1 unit: F6 renewable purchase obligation, 54 / 54).  Ruff and format clean.
- **Increment 82 (2026-11-01): 429 passed** (+1 unit: F32 allocation 34 / 34 and F33 cross-subsidy surcharge 48 / 48).  Ruff and format clean.
- **Increment 81 (2026-11-01): 428 passed** (+1 unit: ESR-3 FY2023-24 in the seven-column layout, tied to the ARR's rows 15 and 9).  Ruff and format clean.
- **Increment 80 (2026-11-01): 427 passed** (the trial-balance test now pins R&M and A&G agreeing with the books, 13 comparisons).  Ruff and format clean.
- **Increment 79 (2026-11-01): 427 passed** (+2 unit: power purchase reconciled to the audited accounts across two workbooks, differing by A44's 1.50; the trial balance against the true-up claims, 9 of 11 agreeing and employee benefits off by exactly 0.0105 crore).  Ruff and format clean.
- **Increment 78 (2026-11-01): 425 passed** (+1 unit: ACoS and ABR on the three snapshots, 8 / 8).  Ruff and format clean.
- **Increment 77 (2026-11-01): 424 passed** (the integration test checks the formats accounting: 74 accounted, the missing ESR7 named, F19A not indexed).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 76 (2026-11-01): 424 passed** (+1 integration: a sign-off needs the attestation, a reason for a reservation, a scope the filing has and the current reproduction's hash — 409 on a stale one; an analyst cannot sign; every scope starts open).  Ruff, format, contracts (regenerated) and web typecheck clean; migration 0021 applied on the local stack.
- **Increment 75 (2026-11-01): 423 passed** (the end-to-end test checks the capitalisation fed from the capital plan, 8 / 8).  Ruff and format clean.
- **Increment 74 (2026-11-01): 423 passed** (the end-to-end test checks the loan rate fed from the MCLR revisions, the ARR year's taken from the APR year with its reason).  Ruff and format clean.
- **Increment 73 (2026-11-01): 423 passed** (+1 unit: the petition computed end to end from its schedules — ARR and APR years 12 / 12, the true-up year differing by exactly A40's 0.19; the integration test checks the projected column's end-to-end net ARR).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 72 (2026-11-01): 422 passed** (the regression pins the ARR summary at 128 matches).  Ruff and format clean.
- **Increment 71 (2026-11-01): 422 passed** (the integration test now checks the coverage map: the projected column's power purchase tied, the net ARR computed, non-tariff income a record, nothing differing; findings A39–A41 served).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 70 (2026-11-01): 422 passed** (+1 unit: NPCL's true-up power purchase as billed, per source and in three parts, tied to the ARR's rows 20, 22, 23 and 8).  Ruff and format clean.
- **Increment 69 (2026-11-01): 421 passed** (+1 unit: NPCL's revenue from the current tariff by category, three years, tied to the ARR's rows 15 and 9, the one typed adjustment pinned).  Ruff and format clean.
- **Increment 68 (2026-11-01): 420 passed** (+2 unit: NPCL's security-deposit interest, receivables, bad debts and other items reproduced with the one typed March figure pinned as differs; stated constants need a reason and declared blanks are zero).  Ruff and format clean.
- **Increment 67 (2026-11-01): 418 passed** (+1 unit: F24 by class, five years, net tied to the ARR's row 36; +1 unit: a category given in place of its computation, labelled and summed).  Ruff and format clean.
- **Increment 66 (2026-11-01): 416 passed** (+2 unit: NPCL's 2025-regime employee, A&G and R&M of the APR and ARR years reproduced from the base-year sheet and tied to F21, F23 and the ARR; the cell reader never reads a blank as 0).  Ruff and format clean.
- **Increment 65 (2026-11-01): 414 passed** (+2 unit: power purchase by source reproduced with its totals; division by zero blocks).  Ruff and format clean.
- **Increment 64 (2026-11-01): 412 passed** (+2 integration: rules listed with their status and nothing approved; the NPCL reference filing with its chain and findings; unknown ids 404; unauthenticated refused).  Ruff, format, contracts (regenerated) and web typecheck clean.
- **Increment 63 (2026-11-01): 410 passed** (the regression pins the chain: the petition's three columns, 36 of 36; no Commission column fed a petitioner's figure).  Ruff and format clean.
- **Increment 62 (2026-11-01): 410 passed** (the regression pins F29, 24 of 24).  Ruff and format clean.
- **Increment 61 (2026-11-01): 410 passed** (the reproduction regression pins the ARR summary: the petition's own columns match in full).  Ruff and format clean.
- **Increment 60 (2026-11-01): 410 passed** (the reproduction regression pins F17, F18 and F19A).  Ruff and format clean.
- **Increment 59 (2026-11-01): 410 passed** (+1 unit: the reference rates from NPCL's MCLR revisions).  Ruff and format clean.
- **Increment 58 (2026-11-01): 409 passed** (the reproduction regression now pins F27's results column by column).  Ruff and format clean.
- **Increment 57 (2026-11-01): 409 passed** (+3 unit: year-block reading; per-category rules, sums and their guards; NPCL's depreciation workings reproduced and tied to the filed ARR).  Ruff and format clean.
- **Increment 56 (2026-11-01): 406 passed** (the reproduction regression now covers F14 and the cross-format checks, pinning the one inconsistent column; the chain test starts from F14 records).  Ruff and format clean.
- **Increment 55 (2026-11-01): 406 passed** (+3 unit: match / differs / blocked / not-a-value per column; Units-column words; NPCL's filed Energy Balance, F25 and F26 reproduced by the draft rules, 97 of 97).  Ruff and format clean.
- **Increment 54 (2026-11-01): 403 passed** (+19 unit: units and dimensions, the arithmetic-only language, Decimal literals, dependency order, cycles, blocking, per-year selection, rounding feeds, filing readiness, the UPERC drafts' examples, the NPCL FY2026-27 chain from records).  Ruff and format clean.
- **Increment 53 (2026-11-01): 384 passed** (+3 unit: a format header carries a year over its group and maps column words to voices; stored vs displayed values, percentages from fractions, states never zero, a rate in a label is not a unit, restated columns marked).  Evaluation run on real data: the order-vs-petition comparison above.
- **Increment 52 (2026-11-01): 381 passed** (+4 integration: the atlas lists states with commissions and counts and refuses an unauthenticated caller; a state lists its licensees, a licensee finds its state, unknown codes are 404; the norms describe methods and name parameters without values, a skeleton plan is never confirmed, a commission without a plan falls back to the generic plan; reviewed facts are counted per licensee and the applied norms are reviewed approved/trued-up figures with order and source, fixture-labelled).  Ruff, format, contracts-check (regenerated) and web typecheck clean.
- **Increment 51 (2026-11-01): web only** — `pnpm --filter @tariff/web typecheck` clean; no API change (the 377 Python tests of increment 50 stand); screenshots of six pages at desktop and phone width.
- **Increment 50 (2026-11-01): 377 passed** (+3 unit: a one-page list of chapters is no structure and proposal headings stay flagged; a one-word cell over a table row is no heading; a collapsed grid is recognised and a second-reader cell says so).  Ruff, format and contracts-check clean.
- **Increment 49 (2026-11-01): 374 passed** (+2 integration: the readings board lists a reading with its dataset, review counts and next step, and refuses an unauthenticated caller; the next step names the human decision).  Ruff, format, contracts-check (regenerated) and web typecheck clean.
- **Increment 48 (2026-11-01): 372 passed** (+1 unit: sub-rows read with their heading row and the total reconciles; the previous year's gap is not this year's).
- **Increment 47 (2026-11-01): 371 passed** (+4 unit: lettered parts; licensee per row; a long chapter split at its three-level sections; a licensee's column keeps its own voice and a label names what precedes its qualifier; +1 integration: a mixed-case registry code resolves).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 46 (2026-11-01): 366 passed** (+2 unit: short-year listing titles; icon links titled by their column group, a listing for a group of licensees, encoded URLs, an MYT order known by its file name, procedural documents set aside).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 45 (2026-11-01): 364 passed** (+1 unit: cross-border sales placed apart, a bare inter-state sale not; ARR-I4's hint and its pass under `loss_basis`; the integration conventions test now also answers the loss basis and drafts it).  Ruff, format, contracts-check and web typecheck clean.
- **Increment 44 (2026-11-01): 363 passed** (+1 unit: a total printed inclusive of other lines — the hint when unstated, the pass when the mapping states it, no hint when no known convention explains; +1 integration: a convention question posed from a preview, answered by a reviewer only, validated, drafted into a valid mapping, withdrawn).  Ruff, format, contracts-check and web typecheck clean; migration 0020 applied on the local stack.
- **Increment 43 (2026-11-01): 361 passed** (+3 unit: a paragraph-numbered order is read by its headings inside its "Chapter N" parts, wrapped chapter titles joined, the hearing part flagged; a label naming what a line is for is not that line (`not_when`); a cost row named like a quantity follows the table's unit, and singular/plural aliases).  Ruff, format and contracts-check clean; no web change.
- **Increment 42 (2026-11-01): 358 passed** (+2 unit: short-form years and the Amount column; a row whose unit contradicts the line is not placed; +1 integration: a commission without a mapping drafts its first version from the generic skeleton).
- **Increment 41 (2026-11-01): 355 passed** (the end-to-end ARR test now checks the preview: one table read per chapter, the identity failure flagged before reading, and the preview's value count equal to the candidates read).
- **Increment 40 (2026-11-01): 355 passed** (+1 unit: a power source's "Total Cost" is not placed on total expenditure outside a summary; in a table titled as the ARR summary it is).
- **Increment 39 (2026-11-01): 354 passed** (+1 integration: the workbench lists a commission's unplaced labels; a reviewer's alias and "not a line" decisions, refused for an analyst and for an unknown code; the drafted next mapping version keeps v1's aliases, adds the decisions, says draft and not confirmed; a withdrawn decision leaves the draft).
- **Increment 38 (2026-11-01): 353 passed** (+1 unit: the real order's table layouts in synthetic figures — year in the caption, voice from the part, an earlier order's approval, reference and unit columns, a two-row header, footnote marks, a percentage inside a label).
- **Increment 37 (2026-11-01): 352 passed** (+1 unit: the real order's heading patterns reproduced in synthetic page text — contents page, running headers, captions, rows, numbered prose, an out-of-sequence list item, an uncued part heading — and the exact chapters and part notes expected).
- **Increment 36 (2026-11-01): 351 passed** (the true-up test now checks the case activity and its isolation; the benchmarks test downloads the history workbook and checks one row per fact with order, page and fact id, and the derived disallowance).  The run took 8 min 46 s because the local stack was parsing a 423-page real order at the same time.
- **Increment 35 (2026-11-01): 351 passed** (+1 integration: a synthetic combined order, licensees set by an administrator, values attributed per column and per caption, the total column skipped, identities per licensee, facts published per licensee, benchmarks per licensee; the library test also checks that acquiring one document for a second licensee records a combined order).
- **Increment 34 (2026-11-01): 350 passed** (+1 integration: two synthetic licensees read and published; the six ratios and their inputs; fixtures only on request; a rejected petition total gives a reason, not a value).
- **Increment 33 (2026-11-01): 349 passed** (+3 unit: a static listing with rows_only, the listing's licensee, aliases, the year floor and the title rules; following order pages to an embedded PDF; every packaged profile loads).
- **Increment 32 (2026-11-01): 346 passed** (+4 unit: the WebForms engine against a local server that refuses what a browser would not post, proposals from its listing, a refused post reported, the UPERC profile loads; the library integration test also links a twin entry without fetching and checks the profile endpoints).
- **Increment 31 (2026-11-01): 342 passed** (+2 integration: a true-up case from actuals to draft — grounding refusals, isolation, identity block, stale and frozen statements, trace; an APR case with an estimate).
- **Increment 30 (2026-11-01): 340 passed** (+1 unit: generic fallbacks; the end-to-end test asserts chapter assignment).
- **Increment 29 (2026-11-01): 339 passed** (+2 unit: the live ARR channel with mocked HTTP; discovery).
- **Increment 28 (2026-11-01): 337 passed** (+2: organisations/cases/isolation end to end,
  library seed/locate/acquire through a local HTTP server/coverage); web typecheck and build
  green; contracts no drift.
- **Increment 27 (2026-11-01): 335 passed** (323 + 12 ARR: the end-to-end gate and 11 unit
  tests; PostgreSQL 16.15 in Docker on :5432, tesseract 5.3.4; ruff and format clean; web
  typecheck and build green; contracts no drift).  All ARR numbers are SYNTHETIC fixtures.
- **Increment 25 (2026-09-25): 323 passed** (ruff and format clean; web typecheck and build green).
- **Increment 24 (2026-09-25): 322 passed** (ruff and format clean; web typecheck and build green).
- **Increment 23 (2026-09-21): 313 passed** (increment 22 suite plus the four taxonomy checks).
- **Increment 22 (2026-09-20): 309 passed, 0 failed, 0 skipped** (133 s, full suite with
  the ephemeral PostgreSQL; `ruff check` and `ruff format --check` clean; web typecheck
  and `next build` green).  Increment 21 baseline was 300 passed.
- Increment 11 baseline: **244 passed, 0 failed, 0 skipped** (~80 s): 196 unit (13 adapters/profile/fixtures, 32
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
- **ARR (increment 27):** the ARR image channel is fixture-only (the live provider refuses
  rather than fall back); chapter localisation reads the text layer only (no OCR text);
  identities I5, I6, I9, I10, I11 are not evaluated; no ARR batch approval; the review
  screen of spec section 7 is Increment C; the UPERC plan and petition template are
  skeletons; reasoning quotes and reason categories are not extracted yet.  Real ARR
  approvals are gated on the confirmed UPERC mapping (operator decision).

## Architecture decisions and rationale

ADR-0001 service boundaries · ADR-0002 migration owner + OpenAPI contract · ADR-0003
PostgreSQL queue with fenced leases · ADR-0004 platform adapters, filesystem local store ·
ADR-0005 PyMuPDF inventory tooling · ADR-0006 asia-south1, per-env projects, Cloud Run Job
worker (revisit in M8) · ADR-0007 fixture/real isolation via datasets · ADR-0008 no domain
yet, internal ingress, admin Cloud Run Job · ADR-0009 PyMuPDF primary + pdfplumber secondary
readers, tesseract OCR by subprocess, agreement classes, no grids from OCR yet.

## Next smallest actionable task

**Where things stand (2026-11-03, after increment 150) — `/arr/readings` shows the same, live — read this entry first; the numbered
entries below are the per-increment history.**

- *Human decisions that now gate real data* (nothing below can be done by engineering):
  1. **Reviewer, chapters:** the seven real orders read in the build session (NPCL / UPERC,
     NBPDCL+SBPDCL / BERC, HPSEBL / HPERC, JBVNL / JSERC, the four TP DISCOMs / OERC, the three
     MP DISCOMs / MPERC, UPCL / UERC; all FY2026-27) sit at `chapters_proposed` with a
     per-chapter preview.  Re-register them on the deployed stack (the build session's local
     stack is ephemeral; URLs and hashes are in increments 37, 39, 42, 43, 47), exclude the non-ARR chapters (public hearing, brief facts of the petition,
     directives, open-access annexes — flagged in the chapter notes), set the capped last
     chapter's end, confirm.
  2. **Reviewer, mappings:** decide the unplaced labels in `/arr/mappings/UPERC`, `/BERC`,
     `/HPERC`, `/JSERC`; answer each workbench's **Conventions** questions (UPERC's gap
     convention; JSERC's power purchase inclusive of transmission; BERC's loss basis), look at
     the three failures no convention explains (BERC FY2025-26 ×2, JSERC FY2025-26 APR) (identities ARR-I3 on
     UPERC and ARR-I4 on BERC fail on convention, increment 40; ARR-I1 on JSERC because its
     power purchase total includes transmission, increment 43); draft with `tariff-api
     mapping-draft`, commit, confirm.  Until a mapping is confirmed, real lines of that
     commission can be read and reviewed but not approved.
  3. **Operator, documents:** run the discovery profiles (UPERC, BERC, HPERC, JSERC, JERC Goa &
     UTs, MPERC, OERC, UERC) on the VM for FY2024-25 to FY2026-27, tick proposals in `/library`, acquire; name the
     next commissions for profiles (most other commission sites did not answer from the build
     session).
  4. **Operator, model channel:** an `ANTHROPIC_API_KEY` in the secrets adapter to run the
     live ARR image channel (written and mock-tested, increment 29; never run on a real order).
- *Loading the real orders on another stack* (the VM, after `make dev`):
  `docker compose -f infra/local/docker-compose.yml exec api tariff-api seed` (licensee aliases),
  then `uv run python scripts/load_real_orders.py` — downloads the ten orders from the commission
  websites, checks each SHA-256 against the hashes above (a different file is skipped), registers
  each as a real source with its licensees, waits for parsing and starts its ARR reading; it is
  idempotent and skips a website that does not answer.  Tested on this session's stack (HPERC,
  MPERC ×2: found by hash, readings already proposed).
- *Milestone 13 (proposed, ADR-0021) — where it stands after increment 87:* one commission,
  one licensee, one historical filing reproduced and independently signed off — **UPERC / NPCL,
  ARR petition FY2026-27** — under the binding `docs/arr-filing-requirements.md`, tracked in
  `docs/requirements-matrix.md` (every row `proposed`; nothing approved by the build).  The
  operator's zip is hashed (69 of 72 documents; Annexure-34 and -40 absent; Annexure B, 2.5 GB,
  held by the operator).  **280 draft UPERC rules** in 30 files reproduce the filed formats.
  `/arr/reference/uperc-npcl-fy2026-27` shows the following:
  - **End to end from the schedules:** the regulatory asset is carried from year to year as
    computed (increment 95).  The net ARR and gap of the ARR and APR years match (3,481.83 and
    3,200.63).  The true-up differs by exactly A40's 0.19, which reaches the ARR year's carried
    gap as 0.25 (10 / 12 there).
  - **How each ARR figure is established:** FY2026-27 is 17 computed, 19 tied, 10 records, none
    differing.
  - **Formats accounted, against the filing's index:** 67 reproduced, 4 with no
    arithmetic (text or typed figures, each with its reason), 2 blank, 1 missing — every format
    with figures to compute is checked (increments 143–149, the operator's direction).
  - **The true-up reconciled to the trial balance:** 11 of 13 claims agree.
  - **What the Commission decided** (the FY2026-27 order, read row by row with pages): the order
    read the petition as filed (claimed figures to the last place), and its arithmetic holds.
    The decisions are true-up −123.38, APR +92.64 and ARR +29.51 (net ARR).  The ARR year's O&M
    approval reproduces with the same rules as the claim, and its cut is explained exactly (A60);
    so do capital, loan, RoE, tax, security deposit and depreciation by class (A62); the power
    purchase decision is read by source and explained (A64) — the ARR year's +29.51 accounted
    for line by line.  The true-up's O&M cut (−90.91 of −123.38) is reproduced from the monthly
    price indices: the 2019 norm against NPCL's actual cost (A65); its capital, loan, equity,
    tax and working capital likewise (A67), showing two draft rules that depart from the
    Commission's practice (A66); its depreciation class by class (A68, A69); its power purchase
    line by line, so every line of the true-up's −123.38 has its reason (A70, A71); and the
    APR's +92.64 likewise, reproduced from the Commission's computations (A72, A73); and the
    revenue gap (surplus) carried to FY2026-27 with its carrying cost (A74); the tariff design
    summary — ABR, ACoS, cross-subsidy levels (A75 for the FPPAS monthly sales); the ARR split
    between wheeling and supply, and the open access charges and cross-subsidy surcharge by voltage,
    computed, capped and approved (A80, A81).  The order misprints one line of
    its own summary (A61).
  - **The narrative against the formats:** the nine summary tables are 232 / 253 figures matching
    (all differences in approved columns: A56–A58).  Every text-table figure is traced by value
    (1736 traced, 1538 untraced).
  - **62 findings (A29–A94):** 40 for the petitioner, collected in the draft queries; 22 for the
    reviewer.
  - **The sign-off panel:** nothing signed.

  **Blocked on people:**
  1. **Operator:** approve or amend the requirements and scope decision S-1.
  2. **Operator:** name the independent checker, who signs off in panel 07 of the reference page
     (increment 76) with a reviewer account.
  3. **Operator:** provide Annexure-34 and -40.
  4. **Reviewer:** verify the rules' clauses against the UPERC MYT Regulations 2019 and 2025, and
     approve or amend each rule.  No rule can be approved by the build; until then nothing is
     `filing_ready`.
  5. **Operator:** the 2025 Distribution Regulations are in (increment 90); still to provide: the
     2019 MYT Regulations.  For each, run
     `scripts/clause_candidates.py` on each (increment 89) — the reviewer verifies with the pages in hand.
  5a. **Operator:** provide the Commission's prescribed formats and guidelines.  The 2025
     Regulations have no list: Regs. 4.2, 5.1 and 6.1 refer to formats "as may be prescribed by
     the Commission" (increment 94).  Until then, completeness is measured against the
     petitioner's own index, plus the Regulations' 17 filing requirements (panel 06c).
  6. **Petitioner (through the operator):** answer the findings.  A39 asks for the working of
     the projection years' depreciation by class.

  **Engineering next, smallest first:**
  - **Filling NPCL's petition in the application (operator's direction, 2026-11-05;
    `docs/arr-petition-flow.md`):**
    - done: the engine fills NPCL's formats workbook (increment 150), and a case does so
      through the API as a job (increment 151);
    - next, smallest first:
      1. the client case page — done (increment 152);
      2. the narrative tables from the filled formats — done (increment 153);
      3. column labels for every fill-map column — done (increment 154); the template keeps
         717 cells (182 Commission figures, 504 tariff rates, 31 the petitioner's own
         methods); 25 columns (86 map cells) whose voice the sheet does not print are left
         to the reviewer;
      4. the narrative's prose: the figures it restates (increment 93's trace) listed per
         paragraph for the petitioner to update;
      5. the year shift for a FY2027-28 layout, if the operator chooses that petition;
      6. `readiness` counting the fill (inputs still as filed, blank cells) so the case's next
         step names it.
  - **NPCL, after the whole suite (increments 143–149):** the formats are all checked; what is
    left is depth, not breadth:
    - ESR7 (not filed), on which the month-on-month sales projection (A88) and FPPAS wait;
    - F13's financing columns (A84), on which a plan-level loan / equity check waits;
    - the reviewer's verification of Reg. 30.2 and the formats' rules.
  - the rest of revenue from the rate schedule.  Increment 91 computed energy charges for 45 LT
    slabs from the order's rates (40 match).  Increment 92 checked the existing tariff NPCL states
    in ESR4A against the order: 47 / 47 energy rates, HV per kVAh.  Still to do:
    - minimum charges (fixed and demand charges wait on NPCL's billable demand by category —
      A77, increment 110);
    - LMV-3's local-body column, for the reviewer;
    - HV energy, which waits on the kVAh sold (A55);
  - more of a second commission's order (increment 123 began with UERC / UPCL: working capital
    and RoE, 14 / 18; increment 124 its depreciation, loan and interest, 5 / 17 exact and the rest
    within printed precision; increment 125 its O&M, 967.40 exact; findings U1–U5; increment 126 its ARR end to end — 12,591.09, net 12,489.54, surplus 100.87 to
    the paisa; increment 127 its true-up's loss valuation and sharing under the 2021 Regulations,
    exact; increment 128 its gap carried into FY2026-27's ARR, 343.07 — exact from the printed gap,
    1.7 paise end to end); increment 129 a third commission, MPERC's working capital for three
    DISCOMs in one order (29 / 30); increment 130 its depreciation, loans and equity chained per
    DISCOM across two years (equity and RoE exact, M3); increment 131 its ARR per DISCOM end to
    end, within the printed rates' precision; increment 132 its O&M and the inventory base (M2
    reproduced); increment 133 its wheeling / supply split, M4; increment 134 both orders on the desk,
    `/arr/orders/<id>`); increment 135 a fourth commission, HPERC / HPSEBL (working capital, ARR,
    H1); increment 136 a fifth, JSERC / JBVNL's MYT working capital (negative → nil, against
    MPERC's netting); increment 137 a sixth, BERC's working capital for two DISCOMs; increment 138 a seventh, OERC's
    four DISCOMs — every order in this session; increment 139 the rules compared across the
    seven at `/arr/rules/compare`) — next deeper in any of the seven;
  - the same end-to-end computation for the second reference filing (FY2025-26), to show the
    bindings are not fitted to one petition — **blocked on the operator**: its documents
    (87, listed in `packages/reference-filings/uperc-npcl-fy2025-26.json`) are not in this
    session; the FY2026-27 zip was the only copy provided.
- *The way in (increment 52):* `/client/atlas` (map of India → state → discom → norms →
  petition; see `docs/user-journey.md`).  The atlas fills as the decisions above are taken:
  documents located → orders read → values reviewed → norms applied.  On the VM it needs the
  same rebuild as any web change (`git pull && make dev` or the sandbox compose `up -d --build`).
- *Engineering next:* the extraction over confirmed real chapters (measure precision against
  the reviewer's decisions — the first real precision figure); per-commission true-up formats;
  organisation-owned sources for private documents; normative checks of actuals against
  regulation parameters; more real orders (the profiles list
  JSERC's FY2024-25 and FY2025-26 orders and JERC Goa & UTs).

000000000000000. **Reviewer (increment 39):** open `/arr/mappings/UPERC` (and `/arr/mappings/BERC`
   once a BERC mapping file exists — today BERC reads with the generic skeleton) and decide the
   unplaced labels; then `tariff-api mapping-draft --commission UPERC --out
   packages/arr-taxonomy/mappings/uperc-arr.v2.json`, review the diff, commit, and confirm the
   file's status when it is right.  **Engineering next:** a BERC mapping skeleton from the
   generic one; the extraction over confirmed chapters once a reviewer confirms them.
00000000000000. **Reviewer (increment 37):** in the local stack (or after `git pull && make
   deploy-dev` on the VM, re-registering the NPCL FY2026-27 order), open `/sources/<id>/arr`,
   exclude chapters 1–2 (public hearing) and set chapter 30's end, confirm the rest, and take the
   scan's unplaced list to the UPERC mapping (`packages/arr-taxonomy/mappings/uperc-arr.v1.json`);
   until a reviewer confirms that mapping, real NPCL lines can be read and reviewed but not
   approved.  **Engineering next:** run the extraction over the confirmed chapters and measure
   the structure channel on the real tables (column headings like "Approved in T.O." / "Claimed
   in Petition" / "Approved in True-up" must map to voices).
0000000000000. **Operator (increment 33):** run `tariff-api library-discover --commission <BERC |
   HPERC | JSERC | JERC-GOA-UT | UPERC> --years FY2024-25 FY2025-26 FY2026-27` on the VM and
   tick proposals in `/library`; tell engineering which commissions come next (MERC, TNERC,
   KERC, GERC and others did not answer from the build session, so their listings need the
   VM or a pasted page).
000000000000. **Operator (increment 32):** on the VM, `uv run tariff-api library-discover
   --commission UPERC --years FY2024-25 FY2025-26 FY2026-27 --out uperc.json` (or `/library` →
   Find documents → UPERC), tick the proposals (prefer the digitally signed copy; choose one
   of two for the FY2024-25 slots), record and acquire.  **Engineering next:** discovery
   profiles for the next commissions the operator names (each needs its site's listing
   checked live); sources with several licensees for combined orders.
00000000000. **Engineering next (increment 31):** commission true-up formats as data (like the
   petition templates); organisation-owned sources so a client's private accounts can be
   grounded rather than stated; normative checks of actuals against regulation parameters with
   the clause cited; per-commission document discovery (UPERC's list is a postback form).
   **Operator:** a true-up needs the year's approval read and reviewed first — read the order
   that approved the year (`/sources/<id>/arr`) before starting the case.
0000000000. **Operator (increment 28, the library):** on the VM (open egress), seed the library
   (`/library` → Seed, or `POST /library/seed`), then record the official URL of each order and
   petition you want first (`/library` → Record a document, or `POST /library/entries/bulk`
   with a list) and acquire them; failures say why.  Create the client organisations
   (`/admin/organisations`).  Engineering next: per-commission discovery of document URLs
   (UPERC's list is a postback search form), the live ARR image channel, the ARR review
   screen, true-up/APR case kinds.
000000000. **Operator (increment 27, ARR Increment B inputs):** on the deployed or local
   stack, set the NPCL orders' `order_type` and `decides`; upload NPCL's last ARR petition
   (`order_type=arr_petition`) if you have it and the UPERC distribution tariff regulations
   with amendments (`order_type=regulation`); then `POST /sources/<NPCL id>/arr/read` (or
   `tariff-api arr-scan` on its export) and hand the scan's `unplaced` list to a reviewer.
   Until a reviewer confirms `uperc-arr.v1.json`, real ARR lines can be read and reviewed
   but not approved.  Engineering then writes the Anthropic ARR image channel (Increment B)
   against the real NPCL pages.
00000000. **Engineering (Milestone 12, ARR):** Increment A done (increment 27).

0000000. **Operator (increment 24):** `git pull && make deploy-dev` (migration 0014) and
   `make admin-dev ARGS=seed` (adds UPPTCL, KPTCL, GETCO).  On each existing order's page
   set "what the instrument is" and the years it decides.  Export NPCL again (export 2
   carries the page text), unzip into `exchange/UPERC/`, then
   `uv run tariff-api arr-scan --exchange exchange/UPERC/<folder>` on the VM (or leave it
   to the engineering session after the push): `arr-scan.json` is the first hand-mapping
   report and its `unplaced` list the first reviewer task.
000000. **Operator (increment 23, ARR):** upload to the bucket, under each commission's
   folder, the distribution and transmission ARR/tariff orders for the three years, the
   MYT orders and mid-term reviews, and the tariff regulations with amendments, for UPERC,
   KERC and GERC (see `docs/arr-spec.md` section 5 for the order types).  Then export the
   NPCL order and one KERC and one GERC order (`parsed` or later) into
   `exchange/<COMMISSION>/` and push: the hand-mapping starts from those files.  Name one
   reviewer with ARR literacy for a day per commission.
00000. **Operator, on the `tariff-order` VM (increment 22):** `git pull && make deploy-dev`,
   then open the NPCL source page and click "Re-run extraction" (or
   `make admin-dev ARGS=rerun,5f900540-a863-4f43-a570-7640114a190e,extract_source,--actor,bootstrap`),
   wait for the scheduler (or `make drain-dev`), and open the tariff table: expect the
   ToD rows once each, HV-3 traction once, LMV-9 once, LMV-5 rows paired, and the
   applicability paragraphs folded under "Conditions and notes".  Then "Download
   everything as JSON" from the source page, unzip into `exchange/UPERC/`, commit and
   push: the LMV-3 and LMV-5 pages (369, 372, 373) are diagnosed from those files, not
   from pasted screens.
0000. **Operator, on the `tariff-order` VM (increment 21):** after the deploy below,
   `make admin-dev ARGS=seed` once to load every commission and distribution company;
   then the Commissions page is the place to upload from.
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
