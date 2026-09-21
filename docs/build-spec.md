# Build specification

The governing build specification is committed verbatim at
**[`docs/spec/master-build-prompt.md`](spec/master-build-prompt.md)** — the supplied
"Master build prompt: Reliable Tariff Order Intelligence" (Parts A–F, including the verified
reading hazards for the NPCL, KERC and GERC orders).

This file is the stable path other documents and prompts reference; the spec file itself is
never edited, so that what the build was measured against stays auditable.  Where any summary
in this repository differs from the master prompt, **the master prompt wins**.

Quick map:

| Section | Subject | Implemented in |
| --- | --- | --- |
| 0 | Definition of "reliable" | the gates in every milestone |
| 1 | Scope, sources, users, questions | `docs/product-spec.md` |
| 2 | Working agreement | `AGENTS.md`, `CLAUDE.md` |
| 3 | Google Cloud topology and portability contract | `docs/deployment.md`, `infra/`, `adapters/` |
| 4 | Architecture and technology choices | `docs/architecture.md`, ADRs |
| 5 | Data contract (charge families, entities) | `docs/data-dictionary.md`, `services/api/migrations/` |
| 6 | Reading Reliability Program | `docs/reading-reliability.md` (ledger), Milestones 2–4 |
| 7 | User interaction as the reliability engine | `docs/interaction-contract.md` |
| 8 | Query tools and answer contract | Milestone 7 |
| 9–10 | Product experience, voice | `apps/web`, Milestone 10 |
| 11 | Milestones and gates | `docs/BUILD_STATE.md` |
| 12 | Evaluation and operations | `docs/evaluation-plan.md`, `tests/` |
| 13 | Required handoff | `docs/BUILD_STATE.md` |
| 11 (M12) | ARR foundation: taxonomy, fact schema, identities, review screen, what-if | `docs/arr-spec.md`, `packages/arr-taxonomy/`, ADR-0017 |
| D/E/F | Per-order reading hazards and acceptance checks | `tests/golden/manifest.json`, Milestones 2–7 |
