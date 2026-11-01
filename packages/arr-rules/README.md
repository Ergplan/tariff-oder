# ARR calculation rules

Executable, versioned calculation rules per commission (`docs/arr-filing-requirements.md` §3,
ADR-0021).  Each rule computes one output from typed inputs with a formula in a restricted
language (numbers, input names, `+ - * /`, `avg min max sum`), evaluated in decimals with
units checked dimensionally (`tariff_api/arr/rules.py`).

- **A rule cites its clause** (regulation, clause, page, excerpt) and says whether a person has
  verified the excerpt against the regulation (`verified`).
- **A rule applies to years** (`applies.from_fy` / `to_fy`): one petition can compute a true-up
  year under one regulation and the ARR year under the next; rules are chosen per year.
- **Worked examples** run as tests; an example says where it comes from.  Examples taken from a
  petitioner's filed formats show the petitioner's application of the rule, not the regulation.
- **Status** `draft` → `approved` (by a named person, on a verified clause, with examples) →
  `superseded`.  Nothing in the build approves a rule.  A case is filing-ready only when every
  rule it used is approved on a verified clause.

`uperc/` — first drafts for the capital chain (normative equity and return on equity; normative
loan and interest), one file per regulation regime: the 2019 MYT Regulations (FY2024-25 true-up)
and the 2025 MYT Regulations (from FY2025-26, applicability to be decided).
