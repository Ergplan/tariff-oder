# ARR Network agents (`tools/arrnet`)

The worker side of the ARR Network ([`docs/arr-network/ARCHITECTURE.md`](../../docs/arr-network/ARCHITECTURE.md)).
The agents read Indian electricity ARR orders and write what they read to the application's
database **only through its ingest API** ([`docs/arr-network/INGEST.md`](../../docs/arr-network/INGEST.md)).
Every value keeps its order, page and the line as printed. Nothing here marks anything reviewed.

## Agents

| Module | Agent | What it does | Needs |
| --- | --- | --- | --- |
| `reference.py` + `reference.json` | seed | States (36), commissions with their states, utilities (the DISCOMs of `tools/arrdb/registry.json`, the TRANSCOs of `tools/arrdb/registry-transco.json`), heads (`arrdb.heads`), the key parameters of ARCHITECTURE.md | — |
| `courier.py` | Courier | Order rows, every page's text (`page.get_text()`), `has_text_layer` (15+ words, arrdb's threshold), `pages_without_text`. Downloads missing files with `arrdb.scrape.download` (`--download`) | — |
| `readers/textlayer.py` | Reader: text layer | `arrdb.reader.read_tables` + `arrdb.build.infer_units`; emits exactly the tables and values `arrdb.build` stores. TRANSCO orders are read with `kind="transco"`; a combined order is read once per kind | — |
| `readers/docling_reader.py` | Reader: Docling | Converts only the text-layer ARR table pages ±1 (cap 24) and the pages without a text layer (cap 6, OCR, a separate pass). Cells are interpreted by `readers/interpret.py`: arrdb's title filter, column meaning, heads, units and number parsing | `[docling]`, CPU, ~5–10 s a page |
| `readers/llamaparse_reader.py` | Reader: LlamaParse | LlamaCloud parse API v2: upload with `page_ranges.target_pages`, poll, read the per-page markdown tables with the same interpretation. Keeps the raw response (`llamaparse_raw.json`) so a re-read costs nothing | `LLAMA_CLOUD_API_KEY`, budget |
| `readers/llm_extractor.py` | Extractor | One page (plus the next, for context) inside a delimited data block; structured output (JSON schema) of ARR lines, key parameters and paragraph classes, each with page and quote. Counts tokens, reserves the estimate against the cap, records tokens and cost | `ANTHROPIC_API_KEY`, `[llm]`, budget |
| `verifier.py` | Verifier | (a) evidence: every numeric token of the quote is on the page (text layer, or the reader's own OCR text for a page without one, recorded), the printed value is in the quote — failures are counted per reader and not posted; (b) consensus across readers (`single` / `agreed_2` / `agreed_3` / `conflict`, value within 0.005, same utility/year/voice/head, same page or label); (c) headline and outlier set-aside, ported from `arrdb.build` | — |
| `librarian.py` | Librarian | Paragraphs (blank lines, paragraph numbers, simple headings; table rows skipped), chunks of ~200–400 tokens that never cross a page, embeddings `BAAI/bge-small-en-v1.5` (384-d) via fastembed | `[embed]` |
| `auditor.py` | Auditor | Metrics: gold accuracy per reader (port of `arrdb.check`) and on a common set, cross-order agreement, consensus shares by commission, agreement of each sampled reader with the text layer, evidence rejections, coverage (DISCOMs and TRANSCOs), spend. Posts `gold_figures`; raises `findings` when a measure falls against the previous run | — |
| `director.py` + `policy.yaml` | Director | Rule-based planner (works with no key): fetch → parse:textlayer → parse:docling (no table found, or scanned pages) → parse:llamaparse (readers disagree on > 20 % of the shared pages' figures) → extract → verify → index → audit; retries up to `max_attempts`, then parks; respects the budget; writes the brief (`is_real: false` without a model). With `ANTHROPIC_API_KEY`, a model writes the narrative and may reorder or park planned items, only through `Queue.enqueue` / `Queue.park` | — (model optional) |
| `ingest.py` | ingest client | Batches of ≤ 1,000 rows and ≤ 4 MB, retries with backoff on 5xx and network errors, per-row rejections returned with their row; review fields are refused client-side. `DryRunSink` writes the batches as JSONL and applies the API's shape rules (`shapes.py`) | `INGEST_URL`, `INGEST_TOKEN` |
| `spend.py` | budget | Daily caps from `policy.yaml`, enforced in code before every paid call; a ledger of real spend | — |

Fixture results (`is_real: false`) are never verified into real output, and fixture spend is not
counted against the cap.

## Setup

```
cd tools/arrnet
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev,embed,docling]"    # add llm for the Extractor
```

`tools/arrdb` is put on `sys.path` by `arrnet/config.py` (override with `ARRDB_PATH`).

## Environment

| Variable | Meaning |
| --- | --- |
| `ARRNET_PDF_DIR` | the order files, named `<sha256>.pdf` (untrusted downloaded data) |
| `ARRNET_STATE` | the local work area (default `tools/arrnet/.state`, git-ignored): page text, each reader's result, the queue, the spend ledger, the auditor's last run |
| `INGEST_URL`, `INGEST_TOKEN` | the application's ingest API (not needed with `--dry-run`) |
| `LLAMA_CLOUD_API_KEY` | LlamaParse; without it the reader returns `skipped`. Where a proxy injects the key, set a placeholder |
| `ANTHROPIC_API_KEY` | Extractor and the Director's narrative; without it they return `skipped` / the rule-based brief |
| `ARRNET_BUDGET_DAILY_USD` | overrides `budget.daily_usd` for one run (the policy default is 0: no paid call) |

Keys come only from the environment; nothing writes a key to a file.

## Commands

Run Python that reads the PDFs isolated (`-I`), from a directory other than the PDFs':

```
PY="tools/arrnet/.venv/bin/python -I"
$PY -m arrnet.run seed      --dry-run OUT
$PY -m arrnet.run courier   --dry-run OUT [--download]
$PY -m arrnet.run read --reader textlayer|docling|llamaparse|llm --dry-run OUT
$PY -m arrnet.run verify    --dry-run OUT
$PY -m arrnet.run index     --dry-run OUT [--no-embed]
$PY -m arrnet.run audit     --dry-run OUT
$PY -m arrnet.run direct    --dry-run OUT       # plan, enqueue, write the brief
$PY -m arrnet.run work      --dry-run OUT       # run the queued items
$PY -m arrnet.run all       --dry-run OUT       # seed, courier, text layer, direct, work, direct
  common: [--only UERC,OERC] [--limit N] [--manifest FILE ...] [--max-pages N] [--max-total-pages N]
```

Without `--dry-run` the rows go to `INGEST_URL`. The default manifests are
`tools/arrdb/data/orders.json` and `tools/arrdb/data/orders-transco.json`; MERC's pooled STU
orders are skipped (the STU is not a utility) and `JSPL` is the utility `JSPL-T`.

Tests (the tool's own environment; no network, no PDF, no key):

```
tools/arrnet/.venv/bin/python -m pytest tests/unit/test_arrnet_*.py
uv run ruff check tools/arrnet tests/unit/test_arrnet_*.py && uv run ruff format --check tools/arrnet tests/unit/test_arrnet_*.py
```

## Interpretations of the contract

- **Order of posting.** `verify` posts, per parse: the `parses` row, then `parsed_tables` with
  `replace: true` on the first row (the app then clears the parse's tables, values and
  parameters), then `arr_values` and `parameters` without `replace`; then the order's `facts`
  with `replace_order: true` on the first row. `read` posts only the `parses` row and keeps the
  readings locally, because a value is posted only after its evidence check.
- **Facts' natural key.** `(order, utility, year, voice, head, label, page)` holds one figure.
  The same figure printed in two tables of a page becomes one fact. Two columns of one voice in
  one table (an "MTR order" and a "revised" column both read as approved) cannot both be facts:
  the first is kept, the others stay in `arr_values`, and the Verifier counts them.
- **Conflict readers.** In a `conflict` fact, `readers` lists every reader involved (the app
  needs two). `readings[].agrees` says which reader gave the fact's value.
- **LlamaParse cost.** The API reports credits, not money. The parse records `cost_usd: 0` and
  the credits in its note. The spend ledger keeps the policy-price equivalent, so the cap still
  counts it.
- **Previous metrics.** No read endpoint for metrics is relied on: the Auditor keeps its last run
  in `ARRNET_STATE/auditor-last.json`.
- **Work queue.** The queue is kept locally and mirrored to `work_items`. Claiming from
  `/api/ingest/work/claim` is not used yet.
