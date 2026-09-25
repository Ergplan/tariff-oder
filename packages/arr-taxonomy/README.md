# ARR taxonomy and commission mappings

Data for Milestone 12 (ARR foundation), specified in [`docs/arr-spec.md`](../../docs/arr-spec.md).
Read by `tariff_api.arr.taxonomy` (models and loader; `schema.json` is generated from them by
`tariff-api arr-schema -o packages/arr-taxonomy/schema.json`, and a unit test fails on
drift) and by the hand-mapping scanner `tariff-api arr-scan` (`tariff_api.arr.scan`).  No
pipeline stage reads them; the candidate payload and the validators come after the
hand-mapping gate.  Unit tests keep the files coherent (codes unique, parents present,
identities naming real codes, no alias that neither the licensee kind nor the table's unit
can resolve, every mapping on the taxonomy version it was written for).

## The hand-mapping scanner

```
# from an exported order (export version 2 carries page_texts.json):
uv run tariff-api arr-scan --exchange exchange/UPERC/NPCL_TariffOrder1-5f900540
# or from a registered source, on dev: make admin-dev ARGS=arr-scan,<source_id>,--out,/tmp/arr-scan.json
```

It writes `arr-scan.json` next to the export: every table-like line (a label followed by
numbers) placed on a line item, with the alias that matched, how (exact or contained),
the pages and an example; `ambiguous` lines whose label names two items the licensee kind
and the table's unit could not separate; `unplaced` lines with their pages; the fiscal
years and voice words seen in headers (to fill `year_columns` and `voice_columns`); and
the chapter headings the mapping's cues recognised.  The reviewer works the `unplaced`
list into the mapping (`label_aliases`, a new leaf, or "not an ARR line" in `unplaced`).

| File | What it is | Status |
| --- | --- | --- |
| `taxonomy.json` | The line items every ARR order is mapped onto: energy (`E`), transmission-only (`T`), costs (`C`), less-items (`L`), result (`R`), capital (`K`), detail tables (`X`); the value types (voices), the reason categories, the arithmetic identities `ARR-I1` … `ARR-I12` | v1 draft, seeded from domain expectations; not verified against any order |
| `mappings/uperc-arr.v1.json` | UPERC: licensees, orders expected, chapter cues, voice words, aliases, regulation clauses, unplaced lines | skeleton |
| `mappings/kerc-arr.v1.json` | KERC, five ESCOMs and KPTCL | skeleton |
| `mappings/gerc-arr.v1.json` | GERC, DISCOMs and GETCO | skeleton |
| `schema.json` | Shape of the two file kinds | generated from the models |

## Rules that hold for these files

- **A code is stable.**  A line item is never renamed or re-parented once a fact cites it;
  a wrong item is deprecated (`note` says so) and a new one added.
- **Generic aliases live in the taxonomy; commission words live in the mapping.**  A
  printed label that the generic aliases place needs no mapping entry.  One the taxonomy
  cannot place goes to the mapping's `unplaced` list, where a reviewer decides: an alias,
  a new leaf, or "not an ARR line".
- **Every mapping entry is an expectation until a reviewer confirms it** against the
  order's exported text (`exchange/<COMMISSION>/…/pages/*.json`).  The `status` field says
  which; the mapping version bumps when confirmed entries change.
- **Canonical units are INR crore and MU.**  The printed unit stays on every fact; the
  conversion applied is recorded, never assumed.
- **Identities are checks, not corrections.**  A failing identity is a validator finding
  on the chapter; nothing is auto-corrected.
