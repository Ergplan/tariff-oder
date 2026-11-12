-- Sections of an order: its power purchase, renewable portfolio, tariff (rate) schedule,
-- wheeling / open access and time-of-day tables, as printed.  One row per table: its columns
-- and rows (each row's cells as printed, with its page).  Written by the Section Reader
-- (tools/arrnet/arrnet/sections.py) through the ingest API; never reviewed by the API.

CREATE TABLE section_tables (
  section_table_id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
  section TEXT NOT NULL CHECK (section IN ('power_purchase', 're_portfolio', 'tariff_schedule', 'wheeling', 'tod')),
  seq INTEGER NOT NULL CHECK (seq > 0),           -- order within the section, as printed
  kind TEXT NOT NULL DEFAULT 'table' CHECK (kind IN ('table', 'text')),
  label TEXT,                                     -- "Table 6-21", or the rate schedule's category "LMV-1"
  category TEXT,                                  -- the rate schedule's category, when the table is in one
  title TEXT NOT NULL,                            -- as printed
  fiscal_year TEXT,
  page INTEGER NOT NULL CHECK (page > 0),
  pages INTEGER[] NOT NULL,
  columns JSONB NOT NULL,                         -- ["SN", "Source of Power", ...]
  rows JSONB NOT NULL,                            -- [{"cells": [...], "page": 291}, ...]
  n_rows INTEGER NOT NULL CHECK (n_rows >= 0),
  reader_version TEXT NOT NULL,
  is_real BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, section, seq, reader_version)
);
CREATE INDEX section_tables_order ON section_tables (order_id, section, seq);

-- one row per printed table row, for plain-English questions and SQL
CREATE VIEW v_section_rows AS
SELECT t.section_table_id, t.order_id, o.commission, o.arr_year, t.section, t.label, t.category, t.title, t.fiscal_year,
       r.ord::int AS row_no, (r.value->>'page')::int AS page, r.value->'cells' AS cells,
       (SELECT string_agg(c, ' | ') FROM jsonb_array_elements_text(r.value->'cells') AS c) AS row_text
FROM section_tables t
JOIN orders o ON o.order_id = t.order_id
CROSS JOIN LATERAL jsonb_array_elements(t.rows) WITH ORDINALITY AS r(value, ord);
