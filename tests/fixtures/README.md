# Synthetic fixtures

Everything under this directory is **synthetic** and labelled as such inside the file
(`SYNTHETIC FIXTURE - NOT A TARIFF ORDER`).  Nothing here is a tariff order, a rate, or a
citation.  Fixtures are uploaded into the `fixture` dataset only; the API labels every
fixture-derived record with `dataset_kind: fixture` and real-utility queries never join to it.

| Generator | Failure modes reproduced (Section 6.1) | Used by |
| --- | --- | --- |
| `synthetic_pdfs.mixed_text_and_image_pdf` | image-only pages mixed with born-digital pages; roman + offset page labels; rotated page inside a portrait document | `tests/integration/test_sources.py`, `test_worker_recovery.py` |
| `synthetic_pdfs.text_only_pdf` | baseline born-digital document; variants differ only in text so hashes differ | dedup and idempotency tests |
| `synthetic_pdfs.not_a_pdf` | PDF header with corrupt body | `source_unreadable` typed failure |

Generate files on disk with `uv run python tests/fixtures/synthetic_pdfs.py tests/fixtures/generated`
(the `generated/` directory is git-ignored).  Real orders are referenced by hash in
`tests/golden/manifest.json`; their bytes never enter git.
