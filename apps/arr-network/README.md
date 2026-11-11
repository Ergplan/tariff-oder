# ARR Network — web application

The public application of the ARR Network (`docs/arr-network/ARCHITECTURE.md`): a map of India
that drills down to each state's DISCOMs and to each DISCOM's ARR by year, cost heads, key
parameters and orders, with every figure cited to its page and the line as printed. The same
app serves the authenticated ingest API the agents write through (`docs/arr-network/INGEST.md`).

Next.js 16 (App Router, server components) on Node, Postgres 16 + pgvector through the
`postgres` package (no ORM). No figure is ever computed or estimated by the app: pages show only
what the database holds, with its consensus class ("one reader", "two readers agree", "three
readers agree", "readers disagree") and "reviewed by a person" only where `reviewed_by` is set.

## Routes

| Route | What it shows |
| --- | --- |
| `/` | The India map (inline SVG from `data/india-states.json`), each state a link shaded by what the database holds; the same links as a list; headline counts; search box. |
| `/state/[code]` | The state's DISCOMs first (then TRANSCOs, others) with coverage, ARR coverage by year, the commission(s), the orders. |
| `/utility/[code]` | ARR by year (claimed, approved in that year's order, latest word from `v_arr_latest`) as a bar chart and a table; cost heads by year; key parameters; orders. |
| `/order/[id]` | Metadata, readers that ran (real vs fixture), bottom lines, conflicts with each reader's value, tables read, figures by table / utility / year, key paragraphs. Large orders show four tables' figures by default (`?table=ID` or `?table=all` for more). |
| `/cite/[fact]` | One figure as plain-text citation and BibTeX, permanent link, the quote. |
| `/search` | Hybrid search over `chunks` (full text + bge-small vectors, reciprocal-rank fusion) and over fact labels; filters `state`, `utility`, `year`, `kind`. |
| `/ask` | Plain-English question → one SQL query (rules, no model; port of `apps/arr-db/nl2sql.js`), each clause explained, editable SQL, answer, per-row evidence, coverage note. |
| `/agents` | Agents' last runs (real and fixture apart), queue, spend by provider and day, latest measures, open findings, the Director's brief. |
| `/api/v1/states`, `/api/v1/utilities[?state=&kind=]`, `/api/v1/utilities/[code]/arr`, `/api/v1/orders/[id]`, `/api/v1/search?q=` | JSON of the same data. |
| `/api/ingest/batch`, `/migrate`, `/health`, `/work/claim`, `/work/[id]` | The write API, exactly per `INGEST.md` (bearer `INGEST_TOKEN`). |

Breadcrumbs on every drill-down page: India › State › DISCOM › Order › Figure.

## Run locally

```sh
pnpm install --filter @tariff/arr-network          # from the repo root
cd apps/arr-network
cat > .env.local <<'ENV'                           # git-ignored; never commit it
DATABASE_URL=postgresql://postgres@127.0.0.1:5433/arrnet
INGEST_TOKEN=<a long random string of your choosing>
ENV
pnpm dev                                           # http://localhost:3100
curl -X POST -H "authorization: Bearer $INGEST_TOKEN" localhost:3100/api/ingest/migrate
INGEST_URL=http://localhost:3100 INGEST_TOKEN=... node scripts/dev-seed.mjs
```

`scripts/dev-seed.mjs` (Node 22, `node:sqlite`) loads the real machine-read data of
`apps/arr-db/data/arr.sqlite` and `tools/arrdb/registry.json` through the ingest API: 36 states
and UTs, 29 commissions with the states they regulate, 67 DISCOMs, 22 heads, 111 orders, one
`textlayer` parse per read order (`arrdb-reader 1`, `is_real: true`), 487 tables, 24,888
readings and 19,008 facts (`consensus: "single"`). It is idempotent (about a minute locally)
and records its own run in `agent_runs` as `dev-seed`. The pipeline (`tools/arrnet`) replaces
this with multi-reader data through the same API.

Checks:

```sh
pnpm typecheck
pnpm test        # validator, SQL-guard and translator tests; the translator's database tests
                 # (hand-read figures from packages/order-reproductions) run when DATABASE_URL is set
pnpm build       # works with or without DATABASE_URL
```

## Environment

| Variable | Needed | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | yes | Postgres 16 with pgvector. Neon: use the pooled connection string (prepared statements are off). Unset or unreachable: every page shows "database not connected", the JSON API answers 503. |
| `INGEST_TOKEN` | for ingest | Bearer token of the ingest API (compared in constant time). Unset: every `/api/ingest/*` route answers 503. |
| `DATABASE_URL_READONLY` | recommended in production | A read-only role for the visitor-written SQL of `/ask`. Without it `/ask` uses `DATABASE_URL` (still inside a `READ ONLY` transaction, 5 s timeout, 2,000-row cap, one statement over the extended protocol). |
| `SITE_URL` | optional | Origin used in permanent links on `/cite` (default: the request's host). |
| `EMBED_DISABLED=1` | optional | Do not load the query embedder; search uses full text only and says so. |
| `EMBED_CACHE_DIR` | optional | Where the ONNX model is cached (default `.cache/hf`, or `/tmp/hf-cache` on Vercel). |
| `DATABASE_POOL_MAX` | optional | Pool size (default 5). |

## Database

Migrations are `db/migrations/NNNN_*.sql`. `scripts/gen-migrations.mjs` (run by `prebuild`)
bundles them into `lib/migrations.generated.ts`, so a Vercel function can apply them without a
file system; `pnpm test` fails if that file is stale. `POST /api/ingest/migrate` applies pending
ones in order, each in its own transaction under an advisory lock, recorded in
`schema_migrations`.

- `0001_init.sql` — the schema of the contract.
- `0002_arr_latest_per_commission.sql` — `v_arr_latest` partitioned also by commission, because
  every state's total is stored under utility `TOTAL` and the totals of different states collapsed
  into one row. Same columns; rows of real utilities are unchanged.

## Query embedding

`lib/embed.ts` embeds the visitor's query with `Xenova/bge-small-en-v1.5` through
`@huggingface/transformers` (ONNX, CPU), loaded lazily on the first search, never at build
time. It uses fastembed's recipe for this model, which is the **[CLS] vector, L2-normalised**
(checked against fastembed 0.9.1 in `tools/arrnet/.venv`: the vectors agree to about three
decimals; mean pooling does not match). Chunks are only compared when their `embedding_model` is
`BAAI/bge-small-en-v1.5`. If the model cannot be loaded, or no chunk has an embedding, search is
full-text only and the page says why.

## Deploy (Vercel) — not done by this build

Project root directory `apps/arr-network`, framework Next.js, install from the pnpm workspace
root (Vercel's default for a monorepo). Set `DATABASE_URL` (Neon from the Marketplace),
`INGEST_TOKEN`, and preferably `DATABASE_URL_READONLY`; then `POST /api/ingest/migrate`.
`next.config.ts` ships onnxruntime-node's linux-x64 binary with the two search routes (about
83 MB unzipped per function, under the 250 MB limit); the model itself (~130 MB) is downloaded
from Hugging Face into `/tmp` on a cold start, so the first search on a cold function is slow.
No `vercel.json` is needed. Nothing here has been deployed.
