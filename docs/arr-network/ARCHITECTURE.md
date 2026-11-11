# ARR Network — architecture

Status: proposed on 2026-11-11, for the direction the operator gave that day. This document is
the contract that the code under `apps/arr-network` and `tools/arrnet` is written against.

## 1. What it is

A collection of every ARR order of India's distribution and transmission utilities. The key
figures and the key paragraphs of each order are parsed into a database and made available on
demand for analysis, search and citation.

The work of finding, reading and checking orders is done by a network of agents, and the
network is managed by agents. People do three things:

- supply keys and a budget;
- review figures;
- decide what the network may publish as reviewed.

The public application runs on Vercel. A visitor goes from a map of India to a state, then to
a utility (DISCOM or TRANSCO), then to its orders. For each order they see every number, with
its page and the line as printed, and the Commission's key paragraphs.

## 2. Rules the design must hold to

These come from `CLAUDE.md` and are not negotiable.

1. **Agents never mark anything reviewed.** An agent can say "three readers agree". Only a
   person can say "reviewed". The two are separate fields, and the app labels them differently.
2. **No figure without evidence.** Every stored value carries its order, page and a verbatim
   quote. The verifier checks that the quote is on that page and that the number is in the
   quote. A value that fails either check is not stored as a value. It is logged as a rejected
   extraction.
3. **Document text is data, never instructions.** Text from an order reaches a model only
   inside a delimited data block. The model's output is parsed against a schema. Nothing an
   order says can change what an agent does.
4. **Provider runs are reported separately from fixtures.** Every parse and extraction row
   records its provider, model, version and cost, and whether it was a real call or a fixture.
5. **Nothing is deployed to Google Cloud by this work.** The network runs on Vercel, a managed
   Postgres, and worker compute that the operator names (section 7).

## 3. The agents

Each agent is a small program with one job. It takes work items from a queue in Postgres and
writes its result and a run record back. "Managed by agents" means the Director decides what
is worked on, and the Auditor decides whether the output can be trusted.

| Agent | Job | Kind |
| --- | --- | --- |
| **Director** | Reads the coverage ledger, the queue, the budget and the Auditor's report. Decides the next work, creates work items, retries or parks failures, and writes a daily brief for the operator. | LLM agent with tools (read ledger, enqueue, park, brief). Its policy is data: `tools/arrnet/policy.yaml`. |
| **Scout** | Finds orders on each commission's listing pages using the discovery profiles, and proposes them with title, URL, utilities and years. | Deterministic. An LLM is used only to classify a title the rules cannot. |
| **Courier** | Downloads each order, hashes it, counts pages, records which pages have a text layer, and stores the page text. | Deterministic |
| **Reader: text layer** | The existing `arrdb.reader`: ARR tables read from word positions. | Deterministic |
| **Reader: Docling** | Layout and table structure, and OCR for scanned pages. Emits tables as cells and page markdown. | Local model, no key |
| **Reader: LlamaParse** | Cloud parse to markdown with tables. Used for pages where the other two disagree, or where neither found a table. | Provider call (key) |
| **Extractor** | From a page's parsed content, extracts ARR lines and key parameters into a fixed schema, each with page and quote. Classifies key paragraphs. | LLM call (key) |
| **Verifier** | Checks every extracted value: quote on page, number in quote, unit present, arithmetic identities. Compares readers and assigns a consensus class. | Deterministic |
| **Librarian** | Splits paragraphs into chunks, embeds them, and maintains the full-text and vector indexes. | Local embedding model, no key |
| **Analyst** | Answers a visitor's question by writing SQL and retrieving passages, and composes an answer in which every figure is cited. | Deterministic translator first. LLM optional. |
| **Auditor** | Measures the network nightly: accuracy against hand-read figures, cross-order agreement, reader disagreement rates, coverage, cost. Opens a finding when a measure falls. | Deterministic. An LLM writes the summary of findings. |

### How a value earns trust

```
extracted by one reader          -> consensus = 'single'
same figure from two readers     -> consensus = 'agreed_2'
same figure from three or more   -> consensus = 'agreed_3'
readers give different figures   -> consensus = 'conflict'   (all candidates kept and shown)
a person confirms it             -> reviewed_by, reviewed_at  (people only)
```

"Same figure" means the same order, utility, year, voice and head, and a value equal to within
0.005 in the printed unit. The app shows the consensus class on every figure. A conflict is
shown as a conflict, with each reader's value and quote. It is never resolved silently.

### The management loop

```
Director (every 6 h)
  reads: coverage ledger, queue depth, failures, spend against budget, Auditor findings
  writes: work items (scout / fetch / parse / extract / verify / index), parks, the brief
Workers (continuous)
  claim a work item (SELECT ... FOR UPDATE SKIP LOCKED), run, write the result and an agent_run
Auditor (nightly)
  writes: metrics, findings
Operator
  reads the brief on /agents; sets budget and keys; reviews figures
```

The Director may only use its tools: read ledgers, enqueue, park, write the brief. It cannot
write a value, change a consensus class or mark a review. A daily spend cap in `policy.yaml`
is enforced in code, not left to the model.

## 4. Data

One Postgres database holds both the relational data and the vectors (pgvector). This is the
"Postgres and vector" store: one system, with a B-tree and GIN side and an HNSW side.

The schema is `apps/arr-network/db/migrations/0001_init.sql`. In outline:

- **Reference**: `states`, `commissions`, `utilities` (kind: `discom`, `transco`, `genco`,
  `sldc`; ownership; aliases).
- **Documents**: `orders` (title, URL, SHA-256, pages, ARR year, kind, read status),
  `order_utilities`, `pages` (text, has text layer).
- **Parses**: `parses` (order, reader, version, provider, model, real or fixture, cost,
  status), `parsed_tables` (parse, page, title, unit, cells as JSON, markdown).
- **Facts**:
  - `arr_values`: one row per reader's reading, with page and quote.
  - `facts`: one row per order, utility, year, voice, head and label, with the consensus class
    and the chosen value. Review fields are written by people only.
  - `fact_readings`: links each fact to the readings behind it.
  - `parameters`: key ARR parameters outside the cost heads, such as sales, losses, average
    cost of supply, tariff change and rates.
- **Text**: `paragraphs` (order, page, kind: ruling, directive, reasoning, submission; text;
  summary), `chunks` (text, `tsvector`, `embedding vector(384)`).
- **Operations**: `work_items`, `agent_runs`, `spend`, `metrics`, `findings`, `briefs`,
  `gold_figures` (hand-read figures used to measure).

Order PDFs are not copied in the first version. Each order keeps its source URL and SHA-256,
and citations link to the commission's own file at `#page=N`. Copying files to Vercel Blob is
a later, separate decision, because it has a storage cost and a rights question.

### Embeddings

`BAAI/bge-small-en-v1.5` (384 dimensions) is computed locally by the Librarian (fastembed), and
by the app for the visitor's query (the same model through ONNX in a Node function). It needs
no key and has no cost per query. Each chunk records its model name, so the model can be
changed later by re-embedding. Search is hybrid: full-text rank and vector distance, fused by
reciprocal rank.

### Key parameters

The Extractor's schema asks for the following per utility, year and voice, each with page and
quote. A parameter the order does not print is left absent, never estimated.

- **Sales and energy**:
  - energy sales (MU);
  - energy input or power purchase quantum (MU);
  - distribution loss (%), AT&C loss (%);
  - collection efficiency (%);
  - transmission loss (%).
- **Cost and revenue**:
  - ARR and each cost head;
  - average power purchase cost (Rs/kWh), average cost of supply (Rs/kWh), average billing
    rate (Rs/kWh);
  - revenue at existing and at approved tariff;
  - revenue gap or surplus;
  - regulatory asset and its recovery;
  - subsidy;
  - tariff change approved (%).
- **Norms and rates**:
  - return on equity rate (%), interest rate on loans (%), interest rate on working capital (%);
  - O&M escalation (%);
  - depreciation rate (%);
  - debt:equity.
- **Capital**: capital expenditure, capitalisation, gross fixed assets opening and closing.
- **Transmission** (TRANSCO orders): transmission ARR, transmission charges, capacity (MW or
  MVA), line length (ckm), availability (%).

## 5. The application (Vercel)

`apps/arr-network` is a Next.js App Router application with server components that query
Postgres directly.

| Route | What it shows |
| --- | --- |
| `/` | Map of India. Each state is coloured by what the network holds for it. Headline counts and a search box. |
| `/state/[code]` | The commission, its DISCOMs and TRANSCOs, the orders found and read, and coverage by year. |
| `/utility/[code]` | ARR by year (claimed, approved, trued-up), the cost heads, the key parameters, and the orders. |
| `/order/[id]` | Everything read from one order: tables, facts with consensus and evidence, key paragraphs, the readers that ran, and a link to the PDF page. |
| `/search` | Hybrid search over paragraphs and facts, filtered by state, utility, year and kind. |
| `/ask` | A plain-English question, the SQL written for it with an explanation, and the answer with citations. |
| `/agents` | The network in the open: agents, queue, runs, spend, accuracy measures, findings and the Director's brief. |
| `/cite/[fact]` | One figure as a citation: text, BibTeX and a permanent link. |
| `/api/v1/*` | The same data as JSON for programmatic use. |
| `/api/ingest/*` | Authenticated write API used by the agents (section 6). |

The map uses real state boundaries drawn as SVG from a GeoJSON file of India's states and
union territories. The file must show the boundaries as the Survey of India draws them. Its
source and licence are recorded next to it. If no suitable file can be obtained, the existing
tile map is used and the page says so.

## 6. How agents write: the ingest API

Agents do not hold database credentials. They call the application:

```
POST /api/ingest/batch          Authorization: Bearer <INGEST_TOKEN>
{ "kind": "orders" | "pages" | "parses" | "parsed_tables" | "arr_values" | "parameters"
          | "facts" | "paragraphs" | "chunks" | "agent_runs" | "metrics" | ...,
  "rows": [ ... ] }             // shapes mirror the tables; natural keys, upserts
POST /api/ingest/migrate        applies pending SQL migrations
POST /api/ingest/work/claim     claims work items;  POST /api/ingest/work/{id}  completes one
```

The exact shapes are in [`INGEST.md`](INGEST.md). The Verifier computes the consensus and
posts the `facts`. The API never accepts a review field, and keeps a person's review when a
fact is posted again.

The API validates every row, and refuses a value without page and quote. It does not accept
the review fields at all. So only the application writes to the database, the rules of
section 2 are enforced in one place, and the same API serves a worker on any machine.

For local development the workers can also write straight to a local Postgres through the same
row validators.

## 7. Where things run

| Part | Runs on | Needs |
| --- | --- | --- |
| Application and ingest API | Vercel project | `DATABASE_URL`, `INGEST_TOKEN` |
| Postgres with pgvector | Neon through the Vercel Marketplace (recommended), or any Postgres 16 with pgvector | **the operator installs it** |
| Workers (Scout, Courier, readers, Extractor, Verifier, Librarian, Auditor) | First in this build session. After that a scheduled runner: GitHub Actions on a schedule, or a small VM. | `INGEST_URL`, `INGEST_TOKEN`, a LlamaParse key, an LLM key |
| Director | A scheduled agent session, or the same runner | LLM key |

Docling needs about 3 GB of model and library files and runs on CPU. It is too large for a
Vercel function, so the readers run on worker compute.

## 8. Providers and keys

| Provider | Used by | Key | Without the key |
| --- | --- | --- | --- |
| LlamaParse (`api.cloud.llamaindex.ai`) | Reader: LlamaParse | LlamaCloud API key | The reader is skipped. Consensus is drawn from the other readers. |
| Anthropic API (`api.anthropic.com`) | Extractor, Director, Analyst (optional) | Anthropic API key | Extractor and Director do not run. Facts come from the deterministic and Docling readers only, and key paragraphs are not classified. |
| Docling | Reader: Docling | none | |
| bge-small | Librarian, search | none | |

Models are named in `policy.yaml`: the Extractor uses the current Sonnet-class model for
volume, and the Director the current Opus-class model. Every call records its tokens and cost
in `spend`.

## 9. Measurement

The Auditor writes these to `metrics` after every run, and `/agents` shows them with dates:

- **Gold accuracy**: for the hand-read figures in `packages/order-reproductions` and
  `packages/reference-filings`, the share each reader found, and the share with the right
  voice and utility.
- **Cross-order agreement**: when a later order quotes an earlier approval, the share of pairs
  where both orders were read as the same figure.
- **Reader agreement**: the share of facts in each consensus class, by commission.
- **Evidence failures**: extractions rejected because the quote or the number was not on the
  page, by reader.
- **Coverage**: utilities with a headline ARR for each year, against the utilities listed.
- **Spend**: by agent, provider and day.

A figure's history is kept: readings are appended, not overwritten, with reader version.

## 10. Build order

1. Schema, ingest API and the application's read pages, against a local Postgres.
2. `tools/arrnet`: Courier and the three readers behind one interface, Verifier, consensus,
   Librarian, and the ingest client. Load the 111 orders already downloaded.
3. Extractor (LLM) and LlamaParse, run on real orders once keys exist. Until then they are
   tested on fixtures, labelled as fixtures.
4. Transmission utilities: registry, Scout, and reader filters by utility kind.
5. Director, Auditor, `/agents`, and the schedule.
6. Deploy to Vercel once the database exists, and load it through the ingest API.

## 11. Open decisions for the operator

1. **Database**: install Neon (Postgres) from the Vercel Marketplace on the project, or name
   another Postgres 16 with pgvector.
2. **Keys**: a LlamaCloud key and an Anthropic API key, and a daily spend cap.
3. **Worker compute after this session**: GitHub Actions on a schedule, or a VM.
4. **Order files**: link to commission URLs only (default), or also keep copies.
5. **The Google Cloud `dev` stack and the earlier studio code**: keep or shut down.
