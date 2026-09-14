# Reading profiles

Versioned, per-commission/per-utility reading profiles (Section 6.11): page-label mapping,
schedule representation (`tables` | `clause_outline` | `mixed`), schedule locators,
secondary authoritative tables, header vocabularies, unit placement, currency convention,
load units and conversion factors, category code patterns, effective-rule type, schedule
scope, footnote conventions, inventory expectations, known quirks.

Profiles are **data, not code**, loaded by id and version from `profiles/<id>.v<n>.json`.
`schema.json` is generated from the pydantic model in `tariff_api.profiles`
(`tariff-api profiles-schema -o packages/reading-profiles/schema.json`); a unit test fails
when the two drift.  Every locator cue carries a `note` naming the specification paragraph or
review that motivated it.

| Profile | Seeded from | Representation | Schedule heading | Units | ToD |
| --- | --- | --- | --- | --- | --- |
| `uperc-npcl` v1 | Part D | tables | `RATE SCHEDULE LMV – 1` | in cells, rupees | percent of energy charge |
| `kerc-escoms` v1 | Part E | tables (+ vector-drawn summary) | `TARIFF SCHEDULE LT-1` | in headers, paise energy / rupee fixed | absolute paise per unit |
| `gerc-discoms` v1 | Part F | clause outline | `1. RATE: RGP` | in the value line | absolute paise per unit |

The seed profiles are expectations from the specification and have **not** been verified
against the real files.  Changing a profile: bump `version` in a new file (old versions stay
loadable), link the review that motivated it in `seeded_from`, add a fixture and a test.
Profile changes never alter approved facts; affected sources show "reprocess available".
