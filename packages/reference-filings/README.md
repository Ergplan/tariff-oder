# Reference filings

Real ARR petitions as their licensee filed them, used as the **reference** a reproduction is
measured against (`docs/arr-filing-requirements.md` R-ACC-1).  Each file lists every
document of one filed petition: its role, which requirement or schedule it feeds, its URL on
the licensee's website, and — once downloaded — its SHA-256 and size.

| Role | Meaning |
|---|---|
| `formats` | the filed tariff formats (spreadsheets): the target of the reproduction |
| `narrative` | the petition's texts (true-up, APR, ARR, cost allocation, compliance, summary) |
| `filing_document` | cover letter, forms, index, fee, authorisations, public notices: the package checklist |
| `utility_record` | the licensee's own records the schedules are computed from (accounts, trial balance, asset register, power-purchase bills, billing determinants, capex, …) |
| `supporting_authority` | orders, approvals and letters the petition relies on |

**Status: unverified listings.**  The lists were read from the licensee's public petition
pages on 2026-11-01.  Hashes are `null` until the documents are downloaded with
`scripts/fetch_reference_filing.py`, which records them from the bytes (never copied).  The
documents are served from a non-443 port that the cloud build session cannot reach; run the
script on the VM.  A role and its `feeds` are a first classification by file name, to be
corrected when each document is opened.

These are public documents a licensee published for public comment; they are **real**
sources and are never mixed with fixtures.
