# Filing templates (ADR-0018)

One folder per commission, `petition.v<n>.json`: the petition **formats** (rendered to XLSX)
and the **narrative** chapters (rendered to DOCX) of a draft ARR petition.  Read by
`tariff_api.arr.filing`.

- Numbers enter a draft only through placeholders — `{proj:CODE:T0}`, `{fact:CODE:VOICE:B}`,
  `{assumption:KEY:T0}` — each resolved value gets a trace id in the trace annex.  `{fy:…}`,
  `{formula:CODE}` and `{clause:CODE:T0}` add words.  A literal digit in template text, an
  unresolved placeholder or a number with no origin refuses generation.
- `status`: `synthetic` (tests), `skeleton` (shape only — `uperc` until the formats the
  regulation prescribes are on file and confirmed by a reviewer), `confirmed`.
- Every draft is watermarked "DRAFT — prepared with software assistance; not filed".  The
  application never files, e-mails or uploads a petition.

| Folder | Status |
| --- | --- |
| `syntherc/` | synthetic fixture for tests |
| `uperc/` | skeleton |
