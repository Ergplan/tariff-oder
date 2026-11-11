-- ARR Network schema (Postgres 16 + pgvector).  See docs/arr-network/ARCHITECTURE.md.
-- Rules enforced here: a value has a page and a quote; review fields exist only on `facts`
-- and are written by people through the application, never by the ingest API.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- reference

CREATE TABLE states (
  code TEXT PRIMARY KEY,                 -- ISO 3166-2:IN without the prefix: UP, MH, OD ...
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('state', 'union_territory'))
);

CREATE TABLE commissions (
  code TEXT PRIMARY KEY,                 -- UPERC, MERC, JERC-GOA-UT ...
  name TEXT NOT NULL,
  website TEXT,
  website_reachable BOOLEAN,             -- what the last Scout run observed; NULL: not tried
  checked_on DATE
);

CREATE TABLE commission_states (
  commission TEXT NOT NULL REFERENCES commissions(code),
  state TEXT NOT NULL REFERENCES states(code),
  PRIMARY KEY (commission, state)
);

CREATE TABLE utilities (
  code TEXT PRIMARY KEY,                 -- UPCL, MSEDCL, UPPTCL ...
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('discom', 'transco', 'genco', 'sldc')),
  commission TEXT NOT NULL REFERENCES commissions(code),
  state TEXT NOT NULL REFERENCES states(code),
  ownership TEXT NOT NULL CHECK (ownership IN ('state', 'private', 'municipal', 'central')),
  aliases JSONB NOT NULL DEFAULT '[]'    -- other names orders use for it
);

CREATE TABLE heads (
  code TEXT PRIMARY KEY,                 -- power_purchase, om, depreciation, arr, net_arr ...
  name TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE parameter_defs (
  code TEXT PRIMARY KEY,                 -- energy_sales_mu, distribution_loss_pct ...
  name TEXT NOT NULL,
  unit TEXT NOT NULL,                    -- MU, %, Rs/kWh, Rs crore, MW, ckm, ratio
  grp TEXT NOT NULL,                     -- sales_energy, cost_revenue, norms_rates, capital, transmission
  sort INTEGER NOT NULL DEFAULT 100
);

-- ---------------------------------------------------------------- documents

CREATE TABLE orders (
  order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  commission TEXT NOT NULL REFERENCES commissions(code),
  title TEXT NOT NULL,                   -- as the commission's website lists it
  url TEXT NOT NULL UNIQUE,
  sha256 TEXT,                           -- NULL until downloaded
  bytes BIGINT,
  pages INTEGER,
  pages_without_text INTEGER,
  arr_year TEXT,                         -- the year whose ARR the order approves: FY2026-27
  years_decided TEXT[] NOT NULL DEFAULT '{}',
  kind TEXT,                             -- tariff_order, true_up, myt, mtr, review ...
  utility_kind TEXT NOT NULL DEFAULT 'discom' CHECK (utility_kind IN ('discom', 'transco', 'genco', 'sldc', 'mixed')),
  order_date DATE,
  found_by TEXT,                         -- the discovery profile or listing that found it
  fetched_on DATE,
  read_status TEXT NOT NULL DEFAULT 'listed'
    CHECK (read_status IN ('listed', 'downloaded', 'read', 'no_tables_found', 'no_text_layer', 'unreadable')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX orders_commission ON orders (commission, arr_year);
CREATE UNIQUE INDEX orders_sha ON orders (sha256) WHERE sha256 IS NOT NULL;

CREATE TABLE order_utilities (
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  utility TEXT NOT NULL REFERENCES utilities(code),
  PRIMARY KEY (order_id, utility)
);

CREATE TABLE pages (
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  page INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '',         -- the PDF text layer, as extracted
  has_text_layer BOOLEAN NOT NULL,
  PRIMARY KEY (order_id, page)
);

-- ---------------------------------------------------------------- parses

CREATE TABLE parses (
  parse_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  reader TEXT NOT NULL CHECK (reader IN ('textlayer', 'docling', 'llamaparse', 'llm')),
  reader_version TEXT NOT NULL,
  provider TEXT,                         -- NULL for local readers
  model TEXT,
  is_real BOOLEAN NOT NULL DEFAULT TRUE, -- FALSE: a fixture, never a provider result
  status TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'failed', 'skipped')),
  pages_parsed INTEGER,
  cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, reader, reader_version)
);

CREATE TABLE parsed_tables (
  table_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parse_id BIGINT NOT NULL REFERENCES parses(parse_id) ON DELETE CASCADE,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  page INTEGER NOT NULL,
  pages INTEGER[] NOT NULL DEFAULT '{}',
  title TEXT,
  unit TEXT,                             -- crore, lakh, million, MU ... NULL: not printed
  unit_from TEXT,                        -- where the unit was read from
  columns JSONB NOT NULL DEFAULT '[]',   -- [{index, header, utility, fiscal_year, voice, ...}]
  cells JSONB,                           -- reader-specific cell grid, when the reader has one
  markdown TEXT,
  UNIQUE (parse_id, page, title)
);
CREATE INDEX parsed_tables_order ON parsed_tables (order_id, page);

-- ---------------------------------------------------------------- facts

-- One row per reader's reading of one printed number.
CREATE TABLE arr_values (
  value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parse_id BIGINT NOT NULL REFERENCES parses(parse_id) ON DELETE CASCADE,
  table_id BIGINT REFERENCES parsed_tables(table_id) ON DELETE CASCADE,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  reader TEXT NOT NULL,
  utility TEXT,                          -- a utility code, 'TOTAL' (state total), or NULL (not printed)
  fiscal_year TEXT,
  voice TEXT CHECK (voice IN ('claimed', 'approved', 'approved_earlier', 'actual')),
  stage TEXT CHECK (stage IN ('ARR', 'APR', 'True-up', 'MYT projection')),
  head TEXT NOT NULL REFERENCES heads(code),
  label TEXT NOT NULL,                   -- the row label as printed
  group_label TEXT,
  value_printed TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT,
  value_crore NUMERIC,                   -- NULL when the unit is not printed
  page INTEGER NOT NULL CHECK (page > 0),
  quote TEXT NOT NULL CHECK (length(quote) > 0),
  column_header TEXT,
  year_from TEXT,
  voice_from TEXT,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX arr_values_lookup ON arr_values (utility, fiscal_year, voice, head);
CREATE INDEX arr_values_order ON arr_values (order_id, page);

-- One row per printed figure, across readers.  The consensus class is computed; the review
-- fields are a person's.
CREATE TABLE facts (
  fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  utility TEXT NOT NULL,
  fiscal_year TEXT NOT NULL,
  voice TEXT NOT NULL,
  stage TEXT,
  head TEXT NOT NULL REFERENCES heads(code),
  label TEXT NOT NULL,
  value_crore NUMERIC,
  value NUMERIC NOT NULL,
  unit TEXT,
  page INTEGER NOT NULL,
  quote TEXT NOT NULL,
  consensus TEXT NOT NULL CHECK (consensus IN ('single', 'agreed_2', 'agreed_3', 'conflict')),
  readers TEXT[] NOT NULL,               -- the readers that gave this value
  is_headline BOOLEAN NOT NULL DEFAULT FALSE,  -- the order's bottom-line ARR for this utility, year, voice
  headline_why TEXT,
  set_aside TEXT,                        -- why a headline is not used (an implausible outlier)
  reviewed_by TEXT,                      -- people only
  reviewed_at TIMESTAMPTZ,
  review_note TEXT,
  UNIQUE (order_id, utility, fiscal_year, voice, head, label, page)
);
CREATE INDEX facts_lookup ON facts (utility, fiscal_year, voice, head);
CREATE INDEX facts_headline ON facts (utility, fiscal_year) WHERE is_headline;

CREATE TABLE fact_readings (
  fact_id BIGINT NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
  value_id BIGINT NOT NULL REFERENCES arr_values(value_id) ON DELETE CASCADE,
  agrees BOOLEAN NOT NULL,               -- FALSE: this reader's value differs (a conflict candidate)
  PRIMARY KEY (fact_id, value_id)
);

-- Key ARR parameters outside the cost heads (sales, losses, ACoS, rates ...).
CREATE TABLE parameters (
  parameter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  parse_id BIGINT NOT NULL REFERENCES parses(parse_id) ON DELETE CASCADE,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  reader TEXT NOT NULL,
  utility TEXT,
  fiscal_year TEXT,
  voice TEXT CHECK (voice IN ('claimed', 'approved', 'approved_earlier', 'actual')),
  code TEXT NOT NULL REFERENCES parameter_defs(code),
  label TEXT NOT NULL,
  value_printed TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT NOT NULL,
  page INTEGER NOT NULL CHECK (page > 0),
  quote TEXT NOT NULL CHECK (length(quote) > 0),
  consensus TEXT NOT NULL DEFAULT 'single' CHECK (consensus IN ('single', 'agreed_2', 'agreed_3', 'conflict')),
  reviewed_by TEXT,
  reviewed_at TIMESTAMPTZ
);
CREATE INDEX parameters_lookup ON parameters (utility, fiscal_year, code);
CREATE INDEX parameters_order ON parameters (order_id);

-- ---------------------------------------------------------------- text

CREATE TABLE paragraphs (
  paragraph_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  page INTEGER NOT NULL,
  seq INTEGER NOT NULL,                  -- order on the page
  kind TEXT NOT NULL DEFAULT 'text'
    CHECK (kind IN ('text', 'ruling', 'directive', 'reasoning', 'submission', 'heading')),
  kind_by TEXT,                          -- the reader that classified it; NULL: unclassified
  utility TEXT,
  topic TEXT,                            -- a head or parameter code the paragraph is about, if any
  text TEXT NOT NULL,
  summary TEXT,                          -- an LLM's one-sentence summary; the text is the evidence
  UNIQUE (order_id, page, seq)
);
CREATE INDEX paragraphs_order ON paragraphs (order_id, page);
CREATE INDEX paragraphs_kind ON paragraphs (kind) WHERE kind <> 'text';

CREATE TABLE chunks (
  chunk_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  paragraph_id BIGINT REFERENCES paragraphs(paragraph_id) ON DELETE CASCADE,
  page INTEGER NOT NULL,
  text TEXT NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding vector(384),
  embedding_model TEXT,
  UNIQUE (order_id, page, paragraph_id)
);
CREATE INDEX chunks_tsv ON chunks USING GIN (tsv);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_order ON chunks (order_id);

-- ---------------------------------------------------------------- operations

CREATE TABLE work_items (
  work_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind TEXT NOT NULL,                    -- scout, fetch, parse:textlayer, parse:docling, parse:llamaparse,
                                         -- extract, verify, index, audit
  target TEXT NOT NULL,                  -- a commission code or an order's sha256 / id
  state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'claimed', 'done', 'failed', 'parked')),
  priority INTEGER NOT NULL DEFAULT 100,
  attempts INTEGER NOT NULL DEFAULT 0,
  claimed_by TEXT,
  claimed_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  result JSONB,
  error TEXT,
  created_by TEXT NOT NULL DEFAULT 'director',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (kind, target)
);
CREATE INDEX work_items_queue ON work_items (state, priority, work_id);

CREATE TABLE agent_runs (
  run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  agent TEXT NOT NULL,                   -- director, scout, courier, reader:docling, extractor ...
  version TEXT NOT NULL,
  work_id BIGINT REFERENCES work_items(work_id) ON DELETE SET NULL,
  order_id BIGINT REFERENCES orders(order_id) ON DELETE SET NULL,
  provider TEXT,
  model TEXT,
  is_real BOOLEAN NOT NULL DEFAULT TRUE,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  outcome TEXT NOT NULL CHECK (outcome IN ('ok', 'partial', 'failed', 'skipped')),
  rows_written INTEGER NOT NULL DEFAULT 0,
  rows_rejected INTEGER NOT NULL DEFAULT 0,   -- extractions refused for missing evidence
  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
  note TEXT
);
CREATE INDEX agent_runs_agent ON agent_runs (agent, started_at DESC);

CREATE TABLE metrics (
  metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  measured_on DATE NOT NULL,
  name TEXT NOT NULL,                    -- gold_values_found, cross_order_agreement, coverage_utilities ...
  scope TEXT NOT NULL DEFAULT 'all',     -- all, a reader, or a commission
  numerator NUMERIC,
  denominator NUMERIC,
  value NUMERIC,
  detail JSONB,
  UNIQUE (measured_on, name, scope)
);

CREATE TABLE findings (
  finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  raised_on DATE NOT NULL DEFAULT CURRENT_DATE,
  raised_by TEXT NOT NULL,               -- auditor, verifier ...
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warn', 'block')),
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  order_id BIGINT REFERENCES orders(order_id) ON DELETE SET NULL,
  state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'closed')),
  closed_note TEXT
);

CREATE TABLE briefs (
  brief_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  written_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  written_by TEXT NOT NULL,              -- director
  is_real BOOLEAN NOT NULL DEFAULT TRUE, -- FALSE: written by the rule-based fallback, no model
  body TEXT NOT NULL,                    -- markdown
  decisions JSONB NOT NULL DEFAULT '[]'  -- the work items it created or parked, with reasons
);

CREATE TABLE gold_figures (
  gold_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_sha256 TEXT NOT NULL,
  key TEXT NOT NULL,                     -- the hand-read figure's key in its package
  source TEXT NOT NULL,                  -- the package file it comes from
  page INTEGER NOT NULL,
  value NUMERIC NOT NULL,
  voice TEXT,
  utility TEXT,
  what TEXT,
  UNIQUE (order_sha256, source, key)
);

-- ---------------------------------------------------------------- views the app reads

CREATE VIEW v_facts AS
SELECT f.fact_id, f.order_id, f.utility, u.name AS utility_name, u.kind AS utility_kind, u.state,
       s.name AS state_name, o.commission, u.ownership, f.fiscal_year, f.voice, f.stage, f.head,
       h.name AS head_name, f.label, f.value_crore, f.value, f.unit, f.page, f.quote, f.consensus,
       f.readers, f.is_headline, f.headline_why, f.set_aside, f.reviewed_by, f.reviewed_at,
       o.title AS order_title, o.url AS order_url, o.arr_year AS order_arr_year
FROM facts f
JOIN orders o ON o.order_id = f.order_id
JOIN heads h ON h.code = f.head
LEFT JOIN utilities u ON u.code = f.utility
LEFT JOIN states s ON s.code = u.state;

-- The bottom-line ARR per order, utility, year and voice.
CREATE VIEW v_arr AS
SELECT * FROM v_facts WHERE is_headline AND set_aside IS NULL;

-- The latest word on each utility, year and voice: the headline from the newest order.
CREATE VIEW v_arr_latest AS
SELECT DISTINCT ON (utility, fiscal_year, voice) *
FROM v_arr
ORDER BY utility, fiscal_year, voice, order_arr_year DESC NULLS LAST, fact_id DESC;

CREATE VIEW v_coverage AS
SELECT u.code AS utility, u.name, u.kind, u.state, u.commission,
       COUNT(DISTINCT ou.order_id) AS orders,
       COUNT(DISTINCT ou.order_id) FILTER (WHERE o.read_status = 'read') AS orders_read,
       (SELECT COUNT(DISTINCT a.fiscal_year) FROM v_arr a WHERE a.utility = u.code) AS years_with_arr,
       (SELECT MAX(a.fiscal_year) FROM v_arr a WHERE a.utility = u.code AND a.voice = 'approved') AS latest_approved_year
FROM utilities u
LEFT JOIN order_utilities ou ON ou.utility = u.code
LEFT JOIN orders o ON o.order_id = ou.order_id
GROUP BY u.code;

INSERT INTO schema_migrations (version) VALUES ('0001_init');
