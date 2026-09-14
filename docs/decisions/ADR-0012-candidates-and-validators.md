# ADR-0012 Candidate extraction: schema, provider adapter, channels, validators, routing

Status: accepted (2026-09-14)

## Decision

- **One versioned candidate schema** (`tariff_api.tariff_schema`, `SCHEMA_VERSION`): a
  pydantic model that is both the storage shape and the JSON schema handed to the provider
  as the only tool.  Exact decimals as strings, original text, unit as read, a `value_state`
  on every numeric field, a `decision_status` on every network-charge family, applicability
  dimensions, conditions as verbatim text, and cell- or clause-level evidence with the exact
  excerpt.  A candidate without evidence does not validate.
- **Provider adapter** (`tariff_api.providers`): `FixtureProvider` (deterministic outputs
  from the extraction rules, labelled fixture on every run and every candidate, optional
  perturbations for tests) and `AnthropicProvider` (Messages API, versioned system prompt,
  tool-forced structured output, usage and cost recorded from configured prices, key from the
  secrets adapter).  `provider_backend` defaults to `fixture`; a real run needs the backend
  and a key, and is reported separately.  The live path is written but has not been run:
  no credentials exist in this environment.
- **The deterministic rules are the structure channel's reference.**  `rules_extract` turns
  confirmed structure cells and clause values into candidates without interpretation: cell
  state `unknown` is reported under `missing`, cross-references stay references, `Nil` stays
  a zero state without a number, conditions and footnotes attach as text.  In fixture mode
  both channels run the rules (the image channel optionally perturbed); with the live
  provider the model's structure and image outputs are compared with each other, and the
  rules remain what validators and reviewers can check against.
- **Prose decisions** for network-charge families are read deterministically from the
  network-charge regions: `approved_zero`, `not_levied_pending_petition`,
  `deferred_to_separate_petition`, `by_reference` with the instrument.  Families the text
  does not decide get nothing, and the completeness validator says so.
- **Comparison and routing** (Section 6.10) as specified: agree → high; disagreement on a
  value or unit → low + `channel_disagreement`; one channel missing → medium; plus
  `single_channel` (medium) when the image channel is off — a deviation recorded because
  the spec assumes both channels always run.  Cell flags become risk tags
  (`header_inherited`, `merged_cell_propagated`, `unit_unresolved`, `nil_word`,
  `slab_ambiguous`), OCR pages `ocr_page`, cross-references `cross_reference`, the first order
  read with a profile `new_profile`.  Any risk or non-high confidence → individual review;
  otherwise batch-eligible.  There is no auto-approval path.
- **Validators** (`tariff_api.validators`, VAL-01 … VAL-18 with gaps where the rule needs
  Milestone 4b inputs): field types and value-state legality, unit consistency, slab bounds
  with telescopic cumulative bounds derived, option groups, network-charge completeness,
  loss-role separation, unit sanity per family, time-band coverage, evidence existence,
  conflicting duplicates, inventory reconciliation, magnitude plausibility per profile,
  region provenance.  Findings attach to candidates; a warning or blocking finding adds the
  `validator_finding` risk tag and forces individual review.  Not built yet: derivation
  checks (VAL-07), amendment consistency (VAL-05), cross-representation agreement (VAL-16),
  temporal consistency (VAL-14), rate-condition links (VAL-12) — they need network-charge
  grids, amendment grids, schedule versions and condition records.
- **Stages**: `gridded → extracted` (both channels per approved region, prose decisions per
  network region, cost limits with `budget_exceeded` stopping the job, artefacts per channel)
  and `extracted → validated → awaiting_review` (findings, routing).  Re-extraction replaces
  only `pending` candidates.
- **Family dispositions**: a reviewer records `absent_in_source` / `out_of_scope` per family
  with a rationale and a pages-viewed statement, audited; the completeness validator reads
  them.  This is the only reviewer action in Milestone 4a; approval, correction and
  publication are Milestone 5.

## Addendum (Milestone 4b, 2026-09-14)

- **Network-charge grids** in `network_charges` and `loss_trajectory` regions are gridded
  by the structure stage and read by deterministic rules (`network_extract`): a grid's family
  comes from its own header/row vocabulary (wheeling, cross subsidy, loss) with the region's
  sub-role as fallback; a loss is filed as `oa_loss` in a network region and
  `distribution_loss_approved` in a loss-trajectory region, never by its number.  Derivation
  tables keep only the approved column as the candidate and the other columns as
  `derivation.inputs`; the wheeling working table keeps ARR and sales.  These candidates are
  single-channel (no provider call) and carry the `single_channel` risk.
- **Green-tariff premiums** are read from the provision text with the regulatory-discount
  exclusion attached; **condition records** (numbered general provisions and mid-line
  sub-provisions, cell footnotes, clause conditions) are stored verbatim with the category
  codes they name and `interpretation_status = verbatim_only`.
- **Validators added**: VAL-05 amendment consistency (from the amendment grid artefacts
  against the consolidated schedule text), VAL-07 derivation checks (ARR÷sales, lower-of,
  printed caps), VAL-12 condition links (a cited condition must be a recorded provision,
  footnote or a fragment of one), VAL-16 cross-representation agreement (schedule vs summary
  per category/component/period; a disagreement blocks both).  Still not built: VAL-14
  temporal consistency (needs schedule versions, Milestone 5).
- **Overlapping regions**: a page can belong to several network sub-role regions; each grid
  is read once and prose facts are de-duplicated by their evidence span.
- `tariff-api provider-smoke` runs one two-cell synthetic extraction through the configured
  provider and prints provider, model, tokens and cost — the first thing to run when a key
  exists, before any order is spent on it.

## Consequences

- Nothing in Milestone 4a publishes: candidates live in their own table with their own
  routes and no query tool reads them.
- The fixture provider makes every test deterministic and free; it also means the
  channel-comparison and adversarial tests exercise the plumbing and the rules, not a
  model.  A real provider run on a small NPCL category set remains a gate item that needs
  credentials and the real file.
