# The Mac mini: primary database and agent engine

Operator's decision (2026-11-12): the Mac mini holds the **master copy** of the ARR Network
database and runs the agents; **Neon stays the public read copy** behind the Vercel site, so the
site stays fast (functions in `iad1`, 2 ms from Neon) and stays up when the Mac mini sleeps.

```
 Mac mini                                              cloud
 ┌──────────────────────────────────────────┐          ┌──────────────────────────┐
 │ agents (tools/arrnet): courier, text     │          │ Vercel  arr-101 (iad1)   │
 │ layer, Docling, LlamaParse, Extractor,   │          │   reads ▼                │
 │ verifier, librarian (embeddings) …       │          │ Neon Postgres + pgvector │
 │        │ ingest API (localhost:3100)     │ publish  │   (public read copy)     │
 │        ▼                                 │ ───────► │                          │
 │ Postgres 17 + pgvector  ← master copy    │ publish.sh                          │
 └──────────────────────────────────────────┘          └──────────────────────────┘
```

## Set up (once)

```bash
git clone https://github.com/Ergplan/tariff-oder && cd tariff-oder
bash deploy/macmini/setup.sh
```

`setup.sh` installs Postgres 17, pgvector, Node 22 and uv with Homebrew, creates the database
`arrnet`, builds the application against it and installs the agents (with Docling and the
embedder).  It writes `~/.arrnet/env` (mode 600) with the local database URL and a generated
local ingest token — never into the repository.

## Run

```bash
source ~/.arrnet/env
(cd apps/arr-network && npm run start) &                     # the local ingest API, :3100
curl -s -X POST -H "Authorization: Bearer $INGEST_TOKEN" $INGEST_URL/api/ingest/migrate
tools/arrnet/.venv/bin/python -I -m arrnet.run all --download   # or one step: read / verify / index …
```

## Publish to Neon

Add the Neon connection string (Neon console → the project → Connection string) to
`~/.arrnet/env` as `NEON_DATABASE_URL`, then:

```bash
source ~/.arrnet/env && bash deploy/macmini/publish.sh
```

One transaction on Neon: every data table is emptied and refilled from a data-only dump of the
Mac mini's database, then committed.  Visitors see the old data until the commit.  The schema is
never changed by it; both sides must have the same migrations (checked first: apply a new
migration on both before publishing).

## Status

- `publish.sh` tested between two local Postgres 16 databases (stale rows replaced, pgvector
  columns and sequences carried).  `setup.sh` passes `bash -n` and has **not yet run on the Mac
  mini**: this cloud session cannot reach it until a folder is shared from it (Claude desktop app
  on the Mac mini → Settings → Claude Code → Remote Control).
- The current data (462 MB on Neon) can seed the Mac mini with
  `pg_dump "$NEON_DATABASE_URL" --data-only | psql "$DATABASE_URL"` after migrating it.
