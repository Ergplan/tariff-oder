# Product specification (pointer)

The complete, governing specification is `docs/spec/master-build-prompt.md` (the supplied
"Master build prompt: Reliable Tariff Order Intelligence").  This file summarises scope for
orientation only; where they differ, the master prompt wins.

## Scope of phase one

- Retail supply tariffs and network/open-access determinations (Section 1, 5.1) from three
  supplied orders: UPERC/NPCL FY2026-27, KERC combined FY2025-28, GERC/MGVCL FY2026-27.
- Users: analyst, reviewer, administrator (Section 1.2).
- Questions the product must answer: Section 1.3.
- Out of scope now: comprehensive state coverage claims, bill computation, inferring reasons
  for changes, regional-language text without a reviewed translation step (Section 1.4).

## Definition of reliable (Section 0)

No unreviewed number is a fact; every fact resolves to a source page; the pipeline records
what it does not know; distinct value states stay distinct; the binding schedule is
localised, not guessed; failures are typed and recoverable; local and cloud behave
identically; every discovered reading failure becomes a fixture and a test.

## Milestone plan (Section 11)

M0 assessment → M1 foundation (this increment) → M2 triage/parsing → M3 localisation and
table integrity → M4 dual-channel extraction and validators → M5 review, publication,
explorer → M6 history → M7 text Q&A → M8 cloud hardening → M9 prod promotion → M10 voice →
M11 multi-state pilot → M12 ARR foundation.

## Source availability at Milestone 0/1

None of the three PDFs was present in the build environment (only the specification was
uploaded).  Their hashes, sizes and page counts are recorded in `tests/golden/manifest.json`
and are re-verified, never copied, when the files are registered.
