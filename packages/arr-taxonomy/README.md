# ARR taxonomy and commission mappings

Data for Milestone 12 (ARR foundation), specified in [`docs/arr-spec.md`](../../docs/arr-spec.md).
No code reads these files yet; the loader, the candidate payload and the validators come in
the increments that follow the specification.  Until then a unit test keeps the files
internally consistent (codes unique, parents present, identities naming real codes, every
mapping pointing at the taxonomy version it was written for).

| File | What it is | Status |
| --- | --- | --- |
| `taxonomy.json` | The line items every ARR order is mapped onto: energy (`E`), transmission-only (`T`), costs (`C`), less-items (`L`), result (`R`), capital (`K`), detail tables (`X`); the value types (voices), the reason categories, the arithmetic identities `ARR-I1` … `ARR-I12` | v1 draft, seeded from domain expectations; not verified against any order |
| `mappings/uperc-arr.v1.json` | UPERC: licensees, orders expected, chapter cues, voice words, aliases, regulation clauses, unplaced lines | skeleton |
| `mappings/kerc-arr.v1.json` | KERC, five ESCOMs and KPTCL | skeleton |
| `mappings/gerc-arr.v1.json` | GERC, DISCOMs and GETCO | skeleton |
| `schema.json` | Shape of the two file kinds | hand-written for now |

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
