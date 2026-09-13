# Reading profiles

Versioned, per-commission/per-utility reading profiles (Section 6.11): page-label mapping,
schedule representation (`tables` | `clause_outline` | `mixed`), schedule locators,
secondary authoritative tables, header vocabularies, unit placement, currency convention,
load units and conversion factors, category code patterns, effective-rule type, schedule
scope, footnote conventions, known quirks.

Profiles are **data, not code**, loaded by version.  The initial `uperc-npcl`, `kerc-escoms`
and `gerc-discoms` profiles are seeded in Milestone 3 from Parts D, E and F of the
specification; the schema must express every difference among the three without code
changes.  Every later change links to the reviewer decision that motivated it and marks
affected orders "reprocess available".

Nothing here yet (Milestone 1).
