# ADR-0018 ARR read → formulate → file

Status: accepted (2026-10-31), Increment A of `docs/prompts/arr-build-prompt.md`.
Builds on ADR-0017 (taxonomy as data, facts versioned by order).

## Context

The operator asked for the ARR milestone to end in a **draft ARR petition** a person edits
and submits, built by reading what the commission printed in past orders and formulating
the next ARR from it.  They chose to build the architecture before the hand-mapping gate of
`docs/arr-spec.md` §9, on synthetic fixtures, with UPERC / NPCL as the first real target.

## Decision

### Four kinds of number, four homes

| Kind | What it is | Where it lives | Who makes it |
| --- | --- | --- | --- |
| **Fact** | A number a commission printed, reviewed and published | `arr_facts` (from `candidates` with `payload_kind = 'arr'`) | Reader + human reviewer |
| **Assumption** | A number a named user entered with a rationale, or a regulation parameter a reviewer confirmed against a clause | `arr_assumptions` in a versioned `arr_assumption_sets` | A reviewer or administrator |
| **Projection** | A number a versioned formula computed from facts, assumptions and parameters | `arr_projection_lines` of an `arr_formulations` version | The formulation engine |
| **Scenario** | A what-if on a frozen formulation | (Increment D; spec §8) | A user |

They never share a table, every API response and screen names the kind, and a projection
is never published, cited or shown as a fact.

### Read

- **ARR candidates use the existing envelope.**  `candidates.payload_kind` is `tariff`
  (default) or `arr`; an ARR candidate's `record` is an `ArrCandidate`
  (`tariff_api.arr.schema`): the §1 fields of the ARR spec plus the shared `EvidenceRef`.
  Evidence rendering, evidence views, decisions, second review and undo work unchanged;
  every tariff stage, the tariff queue, checklist and publication filter on
  `payload_kind = 'tariff'`, so neither track can delete, validate or publish the other's
  rows.
- **The ARR track is beside the tariff state machine, not in it.**  An NPCL tariff order is
  both a schedule and an ARR order.  `source_documents.arr_state`
  (`chapters_proposed → chapters_confirmed → extracted → awaiting_review → published`)
  tracks the ARR reading of a source that has been parsed; the tariff `state` is untouched.
- **Stages**: `arr_localise_source` (chapters from the mapping's cues over the page text;
  a reviewer confirms) → `arr_extract_source` (per confirmed chapter: the rules read the
  primary grids, the model channel reads page images through `tariff_api.arr.provider`;
  channels compared field by field) → `arr_validate_source` (identities `ARR-I*`, findings
  in `validator_findings` with the identity id).  Chained like the tariff stages.
- **The gate that remains** (operator decision of 2026-10-31): a decision that approves or
  corrects a **real** ARR candidate is refused while the commission's mapping status is not
  `confirmed…`.  Fixture candidates are not gated.
- **Publication** copies the effective record of finally approved ARR candidates into
  `arr_facts` with the identity `(utility, line_code, fiscal_year, value_type, as_of_order,
  category_code)`; a later reading of the same order supersedes, never overwrites; any open
  blocking identity finding refuses publication.

### Formulate

- **Formula library is code, versioned** (`tariff_api.arr.formulate.LIBRARY_VERSION`); each
  formula declares its inputs and the parameters it needs.  **Which formula computes which
  line is data**: a formulation plan per commission in
  `packages/arr-taxonomy/formulation/<commission>-plan.v<n>.json`, with the **base-selection
  rule** (the order of voices to take as the base year's value) in the same file.
- **No parameter without a source** (prompt rule 7): a formula's parameter is an assumption
  row whose `source_kind` is `user` (with a rationale) or `regulation_clause` (with the clause
  citation and the confirming reviewer).  A missing parameter marks the line `blocked` with
  the reason, and every line that depends on it is blocked in turn; nothing defaults.
- **Reproducibility**: a formulation version records the facts (by id), assumptions (by id),
  plan, library version and base rule it used, and an input hash over all of them.
  Freezing it freezes its assumption set; recomputing a frozen version must give the same
  lines bit for bit (Decimal arithmetic, no floats), and `reproduce` reports any difference.
- The ARR identities run over the projection lines as they do over facts.

### File

- **Templates are data per commission**: `packages/filing-templates/<commission>/petition.v<n>.json`
  — the formats (sheets of line codes against target and history columns) and the narrative
  chapters, with placeholders (`{proj:…}`, `{fact:…}`, `{assumption:…}`, `{formula:…}`,
  `{clause:…}`, `{fy:…}`).  A template's `status` is `synthetic`, `skeleton` (UPERC until the
  formats the regulation prescribes are confirmed by a reviewer) or `confirmed`.
- **Every number traces** (prompt rule 8): numbers enter a draft only through placeholders,
  each resolved value gets a trace id listed in the trace annex (DOCX table and XLSX sheet);
  literal digits in narrative text, an unresolved placeholder or a number with no origin
  make generation fail.  A blocked projection renders as `[blocked: reason]`, never a number.
- Output: **XLSX** (formats + trace sheet) with `openpyxl` and **DOCX** (narrative + trace
  annex) with `python-docx` — both pure-Python, no office suite in the image.  Every page and
  sheet carries `DRAFT — prepared with software assistance; not filed`.
- `filing_drafts.status` is `draft` by a check constraint: there is no "filed" state, no
  submission, e-mail or upload anywhere in the code.
- Model-drafted narrative prose arrives in Increment E; in Increment A narrative text is the
  template's own, marked as such.

### No agent framework

ADR-0017 stands: chapters are jobs on the existing worker, channels go through the
provider adapter, and the shared store is the artefact store.

## Consequences

- One migration (`0015_arr_read_formulate_file`) adds `candidates.payload_kind`,
  `source_documents.arr_state` / `arr_summary`, the `arr_petition` order type (data only:
  `order_type` is free text validated by the API), and the tables `arr_chapters`,
  `arr_facts`, `arr_assumption_sets`, `arr_assumptions`, `arr_formulations`,
  `arr_projection_lines`, `filing_drafts`.
- The ARR image channel is fixture-only in Increment A; the Anthropic implementation is
  written in Increment B against the real NPCL pages.
- KERC still waits on grids from OCR word boxes (ADR-0017).
- The UPERC formulation plan and petition template ship as skeletons; their real content
  needs the UPERC regulations on file and a reviewer, which is Increment B/D/E work.

## Amendment (increment 35, 2026-11-01): combined orders

Many commissions decide the ARR of all their state's distribution licensees in one order (UP's
five discoms, Bihar's two).  An order's licensees are its primary licensee and the further
licensees in `source_licensees`, set by an administrator (or by the library, when the same
document is acquired for a second licensee).  With several licensees, the structure channel
attributes each value to the licensee its column header names (the year and the voice then
come from the caption) or its table's caption names; a total across licensees, or a column for
which no licensee can be read, is skipped and reported, never attributed.  The licensee is
part of the candidate's identity and a correctable field; identities are evaluated per
licensee; publication files each fact under its candidate's licensee and refuses a value whose
licensee is not one of the order's.  The model channel is told the order's licensees and its
candidates naming another are dropped.

