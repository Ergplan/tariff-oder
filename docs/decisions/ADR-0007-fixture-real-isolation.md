# ADR-0007 Fixture and real data isolation

Status: accepted (Milestone 1)

## Decision
A `datasets` table with exactly one row per kind (`real`, `fixture`, unique index on kind).
`utilities` and `source_documents` reference a dataset; every list response and UI row
carries `dataset_kind`; fixture rows render a FIXTURE badge and banner.  Fixture PDFs carry
the banner text "SYNTHETIC FIXTURE - NOT A TARIFF ORDER" on every page.

A separate PostgreSQL schema per kind was rejected because it duplicates every table and
migration; a tenant column with FK enforcement and per-route filtering gives the same
isolation and is testable (`test_fixture_and_real_datasets_are_separate`).  When regulatory
orders link sources to utilities (Milestone 3), a database trigger will reject links whose
dataset kinds differ (`fixture_real_isolation`).
