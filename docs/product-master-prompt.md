# Master build prompt — Tariff Order Studio (the whole product, as built)

> **Consolidated edition, 2026-11-01, through increment 52.**  This document describes the
> entire product in one place: what it is for, who uses it, the rules it never breaks, how it
> is built, what each part does, what is real today and what is still gated on people.  It is
> written as a build prompt, so that an engineer or a coding agent can understand the product
> end to end and continue it, and so that a non-engineer can read Parts A1–A4 and A10 alone
> to understand the product.
>
> **How it relates to the other specifications.**  The original supplied specification,
> [`docs/spec/master-build-prompt.md`](spec/master-build-prompt.md) ("Reliable Tariff Order
> Intelligence", Parts A–F), is kept verbatim and is never edited: it is the baseline the
> tariff-reading build is audited against, and it wins on anything about reading retail
> tariff schedules.  The product has since grown, by decisions recorded in
> [`docs/decisions/`](decisions/) (ADR-0017 to ADR-0020) and by
> [`docs/prompts/arr-build-prompt.md`](prompts/arr-build-prompt.md), into an ARR petition
> product with a client application.  This document consolidates all of it.  Where it
> disagrees with an ADR or with the code, the ADR and the code are the record; correct this
> file.  Where the build stands today is always [`docs/BUILD_STATE.md`](BUILD_STATE.md).

---

# Part A — The product

## A1. Mission in one paragraph

Indian electricity distribution companies (discoms) and the State Electricity Regulatory
Commissions that regulate them produce, every year, hundreds of pages of tariff orders,
true-up orders, multi-year tariff (MYT) orders and Aggregate Revenue Requirement (ARR)
petitions.  The numbers that matter — what a consumer category pays, what the commission
allowed for power purchase, O&M, return on equity, losses, the revenue gap — are buried in
those PDFs, in tables that are sometimes scanned, sometimes vector-drawn without a text
layer, sometimes written as prose.  **Tariff Order Studio reads those orders, has a person
review every number against its page, publishes only reviewed numbers as facts, and uses
that verified regulatory history to prepare the next ARR petition** — a draft a person edits
and files.  Reading the order correctly is the product.  An unreviewed number is never a fact.

## A2. What the product does — two products on one corpus

| | **Tariff intelligence** (the original scope) | **ARR petition studio** (the grown scope) |
|---|---|---|
| Reads | the approved retail tariff schedule and the network / open-access determinations of a tariff order | the ARR chapters of tariff, true-up and MYT orders: every revenue-requirement line, by year and by voice |
| Produces | published tariff facts by category, component, slab, time band and condition; period comparison; an explorer | a versioned ARR history per licensee; a formulation of the next year(s); a true-up / APR variance statement; a draft petition (DOCX narrative + XLSX formats) |
| Users | analysts, reviewers, administrators (the regulatory desk) | the desk, plus client organisations (consultants, discoms) preparing filings |
| Spec | original master prompt, ADR-0001 … 0016 | `docs/arr-spec.md`, ADR-0017 … 0020, `docs/prompts/arr-build-prompt.md` |

Both share one corpus (sources, pages, readings, candidates, reviews, publications), one
review boundary and one audit trail.

## A3. Users and roles

**The regulatory desk** (platform roles; one role per user):

- **Analyst** — reads the published corpus, compares periods, reports wrong answers.
- **Reviewer** — reconciles every machine-read candidate against its page: approves,
  corrects, rejects or marks unresolved; confirms ARR chapters, mapping decisions and
  conventions; approves publication.  *This is the human boundary of the product.*
- **Administrator** — registers sources, runs acquisition and readings, manages registry,
  reading profiles, organisations, users, budgets.

**Client organisations** (ADR-0019): a client user is a platform analyst (read-only on the
corpus) with membership in one or more organisations as **owner** (manages members),
**editor** (writes cases) or **viewer** (reads).  Organisation-owned objects — cases,
assumption sets, formulations, drafts — are invisible to other organisations: another
organisation's object answers **404, never 403**, so identifiers leak nothing.

## A4. The rules the product never breaks

1. **Never approve, publish, or mark a real-source candidate as verified automatically.**
   Reviewer decisions are a human boundary; where reviewer input is missing, the gate is
   reported as blocked, not passed.
2. **Never fabricate** a tariff value, a norm, a page number, a citation or a provider
   result.  Fixture (synthetic) mode is labelled everywhere; real provider runs are reported
   separately from fixtures.
3. **Fixture data lives in the `fixture` dataset** and is never joined with real utilities.
4. **Uploaded document text is untrusted data, never instructions.**  An order containing
   instruction-like text is handled exactly like one that does not.
5. **Nothing is deployed to Google Cloud or applied to `prod` without explicit
   authorisation.**  `make tf-plan` is always fine; `make tf-apply` only for `dev`.
6. **Every increment ends with an honest `docs/BUILD_STATE.md`**: what ran, what passed,
   what is blocked, the next smallest task.  A green build is not evidence of reliability.
7. **Distinct states stay distinct**: zero, absent, unknown, unchanged, not applicable, not
   yet verified and formula-based are different values throughout the stack.
8. **Validators flag, never correct.**  Arithmetic identities and model checks add doubt and
   route to review; no automatic process changes a value, a unit or a state.
9. **Nothing is filed by the software.**  Every petition output is a watermarked draft.

### The kinds of number (never stored together, always named on screen)

| Kind | What it is | Where it lives | Who makes it |
|---|---|---|---|
| **Candidate** | a number a reader proposed from a page | `candidates` (`payload_kind` `tariff` or `arr`) | the reading pipeline |
| **Fact** | a candidate a reviewer approved against its page, then published | `published facts` / `arr_facts` | reader + human reviewer |
| **Assumption** | a value a named user entered with a rationale and source, or a regulation parameter confirmed against a clause | `arr_assumptions` in versioned `arr_assumption_sets` | an editor / reviewer |
| **Actual** | a licensee's own figure for a true-up / APR (audited accounts, a page of a registered document, a reviewed `actual` fact) | `arr_actuals` | a named user, with its source |
| **Projection** | a number a versioned formula computed from facts, assumptions and parameters | `arr_projection_lines` of an `arr_formulations` version | the formulation engine |
| **Scenario** | a what-if on a frozen formulation | its own tables (planned) | a user |

A projection is never published, cited or shown as a fact.  Disallowance (petitioned less
approved) is computed for display, never stored as a fact.

## A5. Architecture

```
browser ─► apps/web (Next.js 16, server components) ─► services/api (FastAPI) ─► PostgreSQL 16 + pgvector
                                                            │                      ▲
                                                            └─► object store       │ FOR UPDATE SKIP LOCKED
                                                                (sources/<sha>.pdf)│
                                               services/worker (durable job runner)┘
```

| Component | Technology | Role |
|---|---|---|
| Web | Next.js App Router, TypeScript, server-side fetch, same-origin proxies for upload / file bytes | never touches the database; forwards identity |
| API | Python 3.11, FastAPI, SQLAlchemy 2 typed models, Alembic (hand-written migrations) | **the only schema owner**; typed errors (`errors.py`); OpenAPI exported to `packages/contracts` (CI fails on drift) |
| Worker | Python job runner over a PostgreSQL queue (lease, heartbeat, checkpoint, fenced writes, bounded attempts, cancellation) | runs every reading stage and the library acquisition |
| Readers | PyMuPDF (primary) and pdfplumber (secondary) table readers with an agreement class per grid; tesseract OCR; a heading inventory | ADR-0009 |
| Model channel | provider adapter: `fixture` (default) or Anthropic (configurable model, per-order cost and token caps); image channel for tables without a text layer; Haystack BM25 retrieval for the model's feedback pass | ADR-0016; never a source of facts on its own |
| Adapters | object store (filesystem / GCS), secrets (env / Secret Manager), identity (local allow-list / IAP) selected by `DEPLOYMENT_PROFILE` | local and cloud behave identically except these |
| Data as code | `packages/reading-profiles`, `packages/arr-taxonomy` (taxonomy, mappings, formulation plans), `packages/discovery-profiles`, `packages/filing-templates` | versioned JSON, reviewer-confirmed before use |

Repository layout and commands: [`AGENTS.md`](../AGENTS.md).  Conventions: ruff (line 120),
`make contracts` after any API change, one ADR per deviation, one reliability-ledger row per
new reading failure mode, no second ORM / queue, no cloud SDK outside `adapters/`.

## A6. Data model (migrations 0001–0020)

| Migration | Adds |
|---|---|
| 0001 foundation | datasets (`real`, `fixture`), users, jurisdictions → commissions → utilities, source_documents (content hash, immutable object key, state machine), source_pages, jobs, job_events, audit_events (append-only), idempotency_records |
| 0002–0005 | triage artefacts; parse (table grids, headings, OCR); localisation (regions, reading profiles); gridded structure (cells, clauses) |
| 0006–0007 | candidates, findings, runs, dispositions; condition records (verbatim provisions, footnotes) |
| 0008–0009 | review decisions (second review, undo), publication releases and facts |
| 0010–0013 | region annotations, category summaries, review assignment, utility on sources |
| 0014 | `order_type`, `licensee_kind` (distribution / transmission) |
| 0015 ARR | `payload_kind` on candidates, `arr_state` and chapters on sources, `arr_facts`, `arr_assumption_sets` / `arr_assumptions`, `arr_formulations` / `arr_projection_lines`, `filing_drafts` |
| 0016 client | organisations, organisation_members, `arr_cases`, `library_entries` (expected / located / acquired / failed), org ownership |
| 0017 | true-up / APR cases, `arr_actuals`, variance statements |
| 0018 | source ↔ licensees (one combined order binds several licensees) |
| 0019–0020 | `mapping_decisions` (aliases, not-a-line, conventions) for the mapping workbench |

Field-level definitions: [`docs/data-dictionary.md`](data-dictionary.md).

## A7. Pipelines

### A7.1 Tariff reading (original scope)

`uploaded → inventoried → triaged → parsed → localised → gridded → extracted → validated →
awaiting_review → published` (and `failed`, `cancelled`, `rejected`, `superseded`,
`needs_reprocessing`).  Each stage writes an immutable artefact and is resumable and
re-runnable (audited).

1. **Register** (`POST /sources` or the GCS inbox → `POST /sources/ingest`): size and header
   checks, SHA-256 (the object name is never identity), dedup, immutable storage, audit.
2. **Inventory and triage**: per-page class (text, scanned, vector-without-text, image),
   text-layer quality, printed page-label rules.
3. **Parse**: OCR where triage routed it; two table readers with an agreement class; a
   document-wide heading inventory.
4. **Localise the binding schedule** with a per-commission reading profile: the approved
   schedule is a small region of a 400-page order and must be told apart from proposals,
   existing tariffs, illustrative and ARR tables — with the reason recorded.
5. **Structure integrity**: tables and clause outlines checked (header carry, merged cells,
   continuation across pages).
6. **Dual-channel extraction**: a deterministic rule channel and a model channel (text or
   image), compared; units normalised (Rs/kWh vs paise/kWh).
7. **Deterministic validators** and a model feedback pass (ADR-0016) that can only add doubt.
8. **Review** (`/review`, `/sources/<id>/review`): queue by risk, evidence on the page,
   approve / correct / reject / unresolved, second review, undo, batch.
9. **Publish** a schedule or a declared subset → explorer (`/explorer`), network
   determinations (`/explorer/<id>/network`), conditions, period comparison.

Verified reading hazards of the three founding orders (UPERC/NPCL, KERC combined, GERC/MGVCL)
are Parts D–F of the original spec and the golden manifest `tests/golden/manifest.json`.

### A7.2 ARR reading (beside the tariff state machine, not in it)

`source_documents.arr_state`: `chapters_proposed → chapters_confirmed → extracted →
awaiting_review → published`.  A tariff order is both a schedule and an ARR order; the two
tracks never touch each other's rows.

1. **Read** (`POST /sources/<id>/arr/read`) → **chapter proposal** (`arr/chapters.py`): the
   order's chapters from its headings — numbered chapters, lettered parts, paragraph-numbered
   orders, long chapters split at their sections — each with a note (ARR or not: public
   hearing, directives, open-access annexes are flagged) and a **reading preview** (how many
   values each chapter would yield, how many identity checks pass, labels not placed).
2. **Reviewer confirms chapters** (`/sources/<id>/arr`): exclude, set ends, confirm.
3. **Extract** (`arr/extract.py`): every table of the confirmed chapters is read row by row;
   each row label is placed on a taxonomy line by the commission's **mapping** (aliases,
   cues, qualifier clauses such as "including", "net of"); each column header gives the
   fiscal year and the **voice** (petitioned, approved, provisional or final true-up, actual,
   control period); combined orders attribute values per licensee (a licensee column or a
   licensee row); a second table reader's cells are used when the primary merged them, and
   say so.
4. **Validate** with the ARR identities (A8) — flag, never correct.
5. **Review and publish** → `arr_facts`, identified by `(utility, line, fiscal year, voice,
   as-of order)`; a later order adds facts, never overwrites.
6. **The mapping workbench** (`/arr/mappings/<commission>`): unplaced labels with their
   evidence → a reviewer's alias / not-a-line decision; **convention questions** derived from
   failing identities (is the gap before or after subsidy? is power purchase printed
   inclusive of transmission? does the loss apply to sales within the state?) → a reviewer's
   answer.  Decisions are written into the next mapping version by `tariff-api mapping-draft`
   and confirmed by a person.  Until a mapping is confirmed, real lines can be read and
   reviewed but not approved.
7. **The readings board** (`/arr/readings`): every order being read, by state and
   commission, with its preview and **the next human step**.

### A7.3 The regulatory library and acquisition

`library_entries` are the **expected** documents per commission / licensee / year / kind
(tariff order, true-up order, MYT order, ARR / MYT petition, regulation), seeded for every
state.  Levels: **missing → located** (official URL known) **→ acquired** (bytes registered as
a source) **→ read → reviewed → published**, plus **failed**.  Discovery profiles
(`packages/discovery-profiles/*.v1.json`: UPERC, BERC, HPERC, JSERC, JERC Goa & UTs, MPERC,
OERC, UERC) read a commission's own listing pages and *propose* entries; an administrator
ticks proposals; the `acquire_library_entry` job downloads, hashes and registers.  It runs
wherever the network allows (most commission sites do not answer from the cloud build
session; the VM has open egress).  The library never claims coverage it does not have.

## A8. The ARR model (data, versioned, in `packages/arr-taxonomy/`)

- **Taxonomy** (`taxonomy.json`): 125 stable line codes in seven families — `E` energy
  (sales, losses, energy input; 25), `C` costs (power purchase, transmission, O&M,
  depreciation, interest, return; 49), `L` less-items (non-tariff income …; 8), `R` revenue
  (ARR, revenue at existing tariff, gap, ACoS; 13), `T` transmission (8), `K` capital
  (17), `X` other (5).  A wrong item is deprecated, never renamed.
- **Canonical units**: money INR crore, energy MU, power MW, rate INR/kWh, share percent; the
  printed unit stays on the fact.
- **Voices**: petitioned, approved, provisional_true_up, final_true_up, actual,
  control_period.  **Reason categories**: normative, prudence check, audited accounts,
  carried forward, disallowed, deferred, not stated.
- **Identities ARR-I1 … I12** (each with a tolerance): I1 total expenditure = sum of its
  printed components; I2 net ARR = total expenditure − less-items; I3 revenue gap = ARR −
  revenue at existing tariff (− subsidy, per the gap convention); I4 energy input = sales ÷
  (1 − loss) (per the loss basis); I5 power purchase rolls up from stations; I6 the energy
  balance closes; I7 ACoS = ARR ÷ sales; I8 power purchase = fixed + variable; I9 loan
  roll-forward; I10 intra-state transmission matches the transmission order's sharing table;
  I11 the true-up chain refers to the same year across orders; I12 sales roll up from
  categories.  Hints tell the reviewer which convention would reconcile a failure.
- **Mappings** (`mappings/<commission>-arr.v1.json`; UPERC, BERC, GERC, KERC, synthetic, and
  a *generic* fallback for every other commission): licensees and aliases, regulations with
  control periods, return basis (RoE / RoCE), gap convention, loss basis, inclusive totals,
  unit convention, chapter cues.  Status `skeleton` until a reviewer confirms.
- **Formulation plans** (`formulation/<commission>-plan.v1.json`; UPERC, synthetic, generic):
  per line a method — `assumption` (entered by the petitioner), `carry_forward`, `escalate`
  (by a rate), `quantity_x_rate`, `energy_input`, `sum`, `net`, `acos` — with named
  parameters (power purchase rate, transmission growth, O&M escalation, IoWC growth, average
  realisation) and a base-year rule (prefer final true-up › provisional › approved ›
  control period).  Parameters are named, never valued, in the plan.
- **Filing templates** (`packages/filing-templates/`: generic, UPERC, synthetic): the
  petition narrative (DOCX) and the formats (XLSX).

## A9. Petitions — the case workflows

A **case** belongs to an organisation and one licensee.  Four kinds:

| Kind | Steps | Output |
|---|---|---|
| **Annual ARR** (next year) / **MYT** (a control period) | Setup → Data & assumptions → Formulate → Freeze → Draft | projection of every ARR line per target year; a draft petition |
| **True-up** (a past year, audited) / **APR** (the running year) | Setup → Actuals → Statement → Freeze → Draft | variance statement: each line's actual (with its source) against the reviewed approved figure, the difference and the reason the petitioner gives |

- **Readiness** lists which base-year facts are reviewed and which are missing; a case can
  start regardless and says what it lacks.
- **Formulate** runs the plan; a line without its inputs is **blocked with the reason**,
  never filled in.  Formulations are versioned and reproducible (`/reproduce`).
- **Freeze** locks the assumption set; **revise** starts a new version and keeps the frozen
  one and its drafts on record.
- **Draft** renders the template: every number traced to an order and page, an assumption
  with its source, or a formula — with a trace annex; DOCX and XLSX downloads; watermarked
  "Draft · not filed".  An actual from a document is grounded mechanically: the excerpt must
  be on the page and the value printed in the excerpt.

## A10. The client application and the user journey

Full journey: [`docs/user-journey.md`](user-journey.md).

**Drafting a petition:** **India** (`/client/atlas` — a tile map, one tile per state / UT in
its approximate place, coloured by what is on record; not a boundary map) → **State**
(`/client/states/<code>` — commission, licensees as cards, norms summary, "Start for
<discom>") → **Discom** (`/client/licensees/<code>` — reviewed ARR history, the norms the
commission applied to it, petitions, documents) → **Norms** (`/client/norms/<commission>` —
regulations, conventions, how each line is formed, the applied norms with order and page;
"working estimate" until a reviewer confirms) → **Petition** (`/client/cases/new` →
`/client/cases/<id>`).

**Checking old orders:** India → State → Discom → Documents (official link and reading
level per year and kind) → the registered order (`/sources/<id>`, its ARR reading) → full
history (`/arr/<discom>`) → benchmarks (`/client/benchmarks`).

| Area | Pages |
|---|---|
| Petition studio (clients) | `/client` home (petitions, five steps, record by state), `/client/atlas`, `/client/states/[code]`, `/client/licensees/[code]`, `/client/norms/[commission]`, `/client/cases`, `/client/cases/new`, `/client/cases/[id]`, `/client/library`, `/client/benchmarks` |
| ARR (desk) | `/arr`, `/arr/[utility]` history, `/arr/[utility]/formulations/[id]`, `/arr/[utility]/drafts/[id]`, `/arr/readings`, `/arr/mappings/[commission]` workbench, `/sources/[id]/arr` chapters |
| Tariff (desk) | `/` status, `/sources` inbox, `/sources/[id]` (+ `/review`, `/review/table`, `/publish`), `/review`, `/explorer`, `/explorer/[id]` (+ `/network`), `/commissions`, `/jobs`, `/registry` |
| Admin | `/library` (seed, discover, acquire), `/admin/organisations`, `/admin/users` |

**Design system** (`apps/web/app/globals.css`): every colour is a token; a dark,
high-contrast default (near-black surfaces, hairline rules, one signal accent, condensed
uppercase display type, monospace labels, square controls) and a **day mode** (light tokens;
the accent stays a fill and becomes deep olive where it is text).  The Day / Night toggle sets
a `theme` cookie the server reads; without a choice the system preference applies.  Phone
width (390 px) has no horizontal scroll.  Visual language inspired by modern defence-tech
sites; no third-party brand, name or asset is used.

## A11. API surface (grouped; exact contract in `packages/contracts/openapi.json`)

- **Platform**: `/healthz`, `/readyz`, `/me`, `/status`, `/audit`, `/users`, `/registry`,
  `/utilities`, `/commissions` (+ assignment), `/jobs/{id}` (+ cancel).
- **Sources**: `/sources` (upload, list, inbox, ingest), `/sources/{id}` (file, pages,
  headings, tables, structure, localisation and its decisions, profile, licensees,
  classification, reprocess, stage re-run, assignment).
- **Tariff reading and review**: `/sources/{id}/candidates|findings|conditions|network|tariff|
  decisions|dispositions`, `/candidates/{id}` (+ evidence, decision), `/review/queue|batch|
  telemetry`, undo, `/sources/{id}/publish` (+ preview), releases, `/facts/{id}`,
  `/explorer/*`.
- **ARR reading**: `/sources/{id}/arr` (+ read, chapters, chapter decision, publish),
  `/arr/readings`, `/arr/taxonomy`, `/arr/mappings/{c}` (+ workbench, decisions,
  conventions), `/arr/utilities/{code}/history`, `/arr/benchmarks`.
- **Formulation and drafts**: `/arr/utilities/{code}/assumption-sets|formulations`,
  `/arr/assumption-sets/{id}`, `/arr/formulations/{id}` (+ freeze, reproduce, drafts),
  `/arr/drafts/{id}`.
- **Client**: `/organisations` (+ members), `/cases` (+ formulate, freeze, revise, draft,
  assumptions, actuals, statement, activity), `/library/*` (coverage, entries, seed,
  discover, discovery profiles, acquire, reconcile).
- **Atlas**: `/atlas`, `/atlas/states/{code}`, `/atlas/licensees/{code}`,
  `/arr/norms/{commission}`.

## A12. Deployment and operations

- **Google Cloud project** `tariff-order-parsing`; data region `asia-south1`; source PDFs in
  `gs://tarifforderstudio_sources`; Terraform state in `gs://tarifforderstudio_tfstate`;
  Terraform in `infra/gcp/` (Cloud Run services for web and API, a Cloud Run Job for the
  worker on a 5-minute schedule, Cloud SQL PostgreSQL 16 with private IP and PITR, buckets,
  Secret Manager, monitoring).  No domain, therefore no public load balancer or IAP yet
  (ADR-0008, ADR-0015).  `dev` was applied and smoke-tested on 2026-09-14; **`prod` is
  never touched without explicit authorisation.**
- **Build VM** `tariff-order` (e2-standard-4) runs the same containers with Docker
  (`make dev`, or the sandbox compose); the web port is published publicly by the operator's
  firewall rule for demonstration, with the local identity profile (every visitor is the
  configured local user — not for confidential data).
- **Local**: `make install`, `make ephemeral-postgres` or Docker, `make migrate seed`, `make
  api`, `make worker`, `make web`.  Real orders are loaded with
  `scripts/load_real_orders.py` (downloads from the commission's site, verifies SHA-256,
  registers, starts the ARR reading; idempotent).
- Full runbook: [`docs/deployment.md`](deployment.md).

## A13. Quality gates

Every increment: `uv run ruff check services tests`, `ruff format --check`, `uv run pytest`
against a real PostgreSQL (381 tests at increment 52; unit + integration, synthetic fixtures,
golden manifests), `make contracts-check`, `pnpm --filter @tariff/web typecheck`, and
screenshots of changed pages at 1440 px and 390 px.  Reading reliability is measured, not
asserted: [`docs/reading-reliability.md`](reading-reliability.md) is the ledger of failure
modes (detection, handling, fixture, test); [`docs/evaluation-plan.md`](evaluation-plan.md)
defines the gates.  Per real order the build reports values read and identity failures,
with each failure either explained (a convention question) or recorded as unexplained.

## A14. Where it stands (honest, 2026-11-01)

- **Built and tested**: the full tariff pipeline through publication and the explorer
  (Milestones 0–5, local profile; `dev` deployed at M1); the ARR track end to end (read,
  chapter proposal, extraction, identities, review, publication, history, mapping
  workbench, conventions, readings board); formulation, true-up / APR statements and draft
  petitions; organisations, the library with discovery and acquisition; the Petition Studio
  UI, the atlas and day mode.
- **Real orders read**: ten orders from seven commissions (UPERC/NPCL, BERC, HPERC, JSERC,
  OERC ×2 years, MPERC ×2, UERC ×2), 163–643 values each, most with zero unexplained identity
  failures.  **None is reviewed yet** — that is a reviewer's work, not the software's — so
  every real state shows zero reviewed ARR facts, and every commission's norms are a
  working estimate.  The reviewed facts in the demo stack are the synthetic fixture's,
  labelled.
- **Human gates open now**: confirm chapters of the ten orders; decide unplaced labels and
  convention questions per commission and confirm the mappings; locate and acquire library
  documents (discovery profiles, on the VM); supply a model API key to run the live image
  channel (written and mock-tested, never run on a real order); confirm per-commission
  formulation plans against their regulations.
- **Not yet**: text / voice Q&A over published facts (original M7, M10), scenario
  (what-if) engine, prod promotion, KERC ARR reading (needs grids from OCR word boxes),
  regional-language documents, bill computation (out of scope).

## A15. Roadmap (the next increments, smallest first)

1. Normative checks: compare a case's actuals and projections against the commission's
   norms (loss trajectory, O&M escalation, RoE rate) once those are confirmed parameters.
2. Extraction precision over reviewer-confirmed real chapters — the first measured real
   precision figure.
3. Per-commission true-up formats; per-commission formulation plans confirmed against the
   regulations (clauses as sources, parameters with their clause).
4. Organisation-owned private sources (a client's own audited accounts).
5. More discovery profiles and real orders, three years per state.
6. Q&A over published facts with the answer contract (original §8), then voice.
7. Scenario engine (power purchase mix only; ADR-0017), prod promotion with authorisation.

---

# Part B — Continuation prompts

Paste one of these into a coding agent in the repository.  Each assumes the agent reads
`AGENTS.md`, `docs/BUILD_STATE.md` and this file first, and ends with an honest BUILD_STATE.

**Continue the build.**  "Read `docs/BUILD_STATE.md` → *Next smallest actionable task*.
Implement the next increment only.  Keep facts, assumptions, actuals and projections apart;
never approve or publish; label fixtures.  Add tests (unit and, for API changes,
integration against PostgreSQL), run all gates, update contracts, screenshot changed pages
at 1440 / 390 px in both themes, write the BUILD_STATE entry, commit and push."

**Onboard a commission.**  "Add `<COMMISSION>`: a discovery profile from its official
listing pages (proposals only, with the page they came from); a mapping skeleton copied from
the generic one with the commission's licensees and aliases (status `skeleton`); register one
real order with its SHA-256; run the ARR reading; report values read, identity failures
explained / unexplained, unplaced labels — and stop at the reviewer gate."

**Onboard a real order.**  "Download `<URL>`, record its SHA-256, size and page count,
register it as a real source with its licensees, run triage → parse → ARR read.  Report the
chapter proposal and preview.  Record any new reading failure as a ledger row with a
synthetic fixture and a test.  Do not confirm chapters."

**Triage a reading failure.**  "Reproduce on the order and page given, minimise to a
synthetic fixture, add the ledger row and the failing test, fix the reader generally (not
for this order), re-measure every real order and report before / after per order."

**Add a petition feature.**  "Extend the case workflow for `<need>`.  Every number on the
output must trace to a fact (order, page), an assumption (user, source) or a formula; a
missing input blocks with a reason; the draft stays watermarked."

**Prepare a production promotion.**  "Do not apply.  Produce the `tf-plan` for `prod`, the
measured differences between local and `dev`, the open reviewer gates, and a checklist for
the operator's authorisation."

# Part C — Glossary

- **ARR (Aggregate Revenue Requirement)** — the total cost a licensee may recover through
  tariffs in a year: power purchase, transmission, O&M, depreciation, interest, return on
  equity, less non-tariff income.
- **Tariff order** — the commission's decision on a petition: the approved ARR, the revenue
  gap and the retail tariff schedule.
- **True-up** — the re-determination of a past year on audited actuals; **APR** (annual
  performance review) — the running year on actuals-so-far and estimates.
- **MYT / control period** — a multi-year tariff framework (typically five years) with
  regulations fixing norms for the period.
- **Voice** — whose number it is: petitioned, approved, provisional or final true-up,
  actual, control period.
- **Revenue gap** — ARR minus revenue at existing tariff; before or after the state
  government's subsidy depending on the commission (the *gap convention*).
- **Distribution loss** — energy lost in the network; energy input = sales ÷ (1 − loss).
- **RoE / RoCE** — return on equity / on capital employed (the *return basis*).
- **IoWC** — interest on working capital.  **ACoS** — average cost of supply (ARR ÷ sales).
- **MU** — million units (GWh).  **Rs crore** — ten million rupees.
- **Discom / licensee** — a distribution (or transmission) licensee regulated by a state
  commission (SERC) or a joint commission (JERC).
- **Fixture** — synthetic test data, always labelled, never joined with real data.
