# ARR Network — the ingest contract

The agents (`tools/arrnet`) write to the database only through the application
(`apps/arr-network`). This file fixes the shapes both sides code against. The tables are in
`apps/arr-network/db/migrations/0001_init.sql`.

## Transport

```
POST {INGEST_URL}/api/ingest/batch
Authorization: Bearer {INGEST_TOKEN}
Content-Type: application/json
{ "kind": "<kind>", "rows": [ {...}, ... ] }
->  200 { "kind": "...", "written": n, "rejected": [ { "index": i, "reason": "..." } ] }
->  400 malformed request · 401 bad token · 413 more than 2,000 rows or 8 MB
```

A batch is one transaction. Rows that fail validation are rejected one by one with a reason,
and the rest are written. `POST /api/ingest/migrate` applies pending migrations and returns
the versions applied. `GET /api/ingest/health` returns the schema version and row counts.

## Keys

Orders are addressed by `order_url` (unique). A parse is addressed by
`(order_url, reader, reader_version)`. Writing a parse's rows again replaces them: the API
deletes that parse's `parsed_tables`, `arr_values` and `parameters` before inserting, when the
batch's first row has `"replace": true`.

## Kinds and row shapes

Fields not listed are not accepted. `?` marks an optional field.

| kind | row |
| --- | --- |
| `states` | `{code, name, kind}` |
| `commissions` | `{code, name, website?, website_reachable?, checked_on?, states: [state codes]}` |
| `utilities` | `{code, name, kind, commission, state, ownership, aliases?: [..]}` |
| `heads` | `{code, name, sort?}` |
| `parameter_defs` | `{code, name, unit, grp, sort?}` |
| `orders` | `{commission, title, url, sha256?, bytes?, pages?, pages_without_text?, arr_year?, years_decided?: [..], kind?, utility_kind?, order_date?, found_by?, fetched_on?, read_status?, utilities: [utility codes]}`. Upsert on `url`. |
| `pages` | `{order_url, page, text, has_text_layer}`. Upsert on `(order, page)`. |
| `parses` | `{order_url, reader, reader_version, provider?, model?, is_real, status, pages_parsed?, cost_usd?, note?}`. Upsert on its key. |
| `parsed_tables` | `{order_url, reader, reader_version, page, pages?: [..], title?, unit?, unit_from?, columns: [..], cells?, markdown?, replace?}` |
| `arr_values` | `{order_url, reader, reader_version, table_page?, table_title?, utility?, fiscal_year?, voice?, stage?, head, label, group_label?, value_printed, value, unit?, value_crore?, page, quote, column_header?, year_from?, voice_from?, is_primary?, replace?}` |
| `parameters` | `{order_url, reader, reader_version, utility?, fiscal_year?, voice?, code, label, value_printed, value, unit, page, quote, replace?}` |
| `facts` | `{order_url, utility, fiscal_year, voice, stage?, head, label, value_crore?, value, unit?, page, quote, consensus, readers: [..], is_headline?, headline_why?, set_aside?, readings: [{reader, reader_version, page, value_printed, agrees}]}`. Upsert on the fact's natural key. **`reviewed_by`, `reviewed_at`, `review_note` are refused if present, and are preserved on upsert.** A batch whose first row has `"replace_order": true` first deletes the order's facts that no person has reviewed. |
| `paragraphs` | `{order_url, page, seq, kind?, kind_by?, utility?, topic?, text, summary?}`. Upsert on `(order, page, seq)`. |
| `chunks` | `{order_url, page, paragraph_seq?, text, embedding?: [384 numbers], embedding_model?}`. Upsert on `(order, page, paragraph)`. |
| `work_items` | `{kind, target, priority?, created_by?}`. Insert if absent. |
| `agent_runs` | `{agent, version, order_url?, provider?, model?, is_real, started_at, finished_at?, outcome, rows_written?, rows_rejected?, input_tokens?, output_tokens?, cost_usd?, note?}` |
| `metrics` | `{measured_on, name, scope?, numerator?, denominator?, value?, detail?}`. Upsert on `(measured_on, name, scope)`. |
| `findings` | `{raised_by, severity, title, detail, order_url?}` |
| `briefs` | `{written_by, is_real, body, decisions?: [..]}` |
| `gold_figures` | `{order_sha256, key, source, page, value, voice?, utility?, what?}`. Upsert on its key. |

## Validation the API enforces

- `arr_values`, `parameters`, `facts`: `page >= 1`, `quote` non-empty, `value` a finite number.
  The API does not have the PDF, so the check that the quote is on the page is the Verifier's.
  The API checks the quote against `pages.text` when that page is stored: with white space
  normalised, the page text must contain each numeric token of `value_printed`. A row that
  fails is rejected with `reason: "number not on page"`.
- `voice`, `stage`, `consensus`, `reader`, `kind` values must be in the schema's lists.
- `head` and `code` must exist in `heads` and `parameter_defs`.
- `utility` must be a known utility code, `TOTAL`, or absent.
- Unknown fields, and any review field, reject the row.

## Work queue

```
POST /api/ingest/work/claim   { "agent": "...", "kinds": ["parse:docling", ...], "limit": n }
  -> 200 { "items": [ { work_id, kind, target, attempts } ] }      (FOR UPDATE SKIP LOCKED)
POST /api/ingest/work/{id}    { "state": "done" | "failed" | "parked", "result"?, "error"? }
```
