# Evaluation plan

Per Section 12, every metric is reported with its denominator; real-source checks are kept
separate from synthetic fixtures; held-out orders are never used to tune prompts or profiles.

## Corpus

| Set | Contents | Location | Bytes in git |
| --- | --- | --- | --- |
| Golden (real, reviewed) | `npcl-fy2026-27`, `kerc-fy2025-28`, `gerc-mgvcl-fy2026-27` — hashes, sizes, page counts, structural expectations from Parts D–F; reviewed reference facts are empty until reviewers approve them | `tests/golden/manifest.json` | no (referenced by SHA-256) |
| Synthetic fixtures | One generator per failure mode as they are handled (Milestone 1: mixed text/image pages, labels, rotation, non-PDF) | `tests/fixtures/synthetic_pdfs.py` | generated on demand |
| Held-out | Fourth-state order for Milestone 11 | to be acquired | no |

## Milestone gates covered by the runner so far

The evaluation runner (`tests/evals/`) is a placeholder until Milestone 2; Milestone 1
acceptance runs as pytest:

| Gate item | Test | Denominator |
| --- | --- | --- |
| Registration records hash, page count, text-layer summary | `test_upload_inventory_reopen_and_dedup` | 6 pages of the synthetic fixture (real orders: blocked, bytes absent) |
| Deduplicate identical second upload | same | 1 |
| Reopen through authorized access | same; `test_unauthenticated_and_role_enforcement` | 1 |
| Unauthorized access refused | `test_unauthenticated_and_role_enforcement` | 6 negative cases |
| Queue lease recovery after a killed worker | `test_worker_killed_mid_job_is_resumed_from_checkpoint`, `test_claim_heartbeat_fencing_and_lease_expiry` | 1 kill, 3 fenced operations |
| Idempotent upload | `test_idempotent_upload` | 3 requests |
| Migrations replay from empty | `test_downgrade_and_upgrade_roundtrip` | 1 |

## Question set (Section 12, Parts D.3/E.3/F.3 — for Milestone 7)

Recorded now so that later milestones do not invent them; every expected answer is a
structural or reviewer-supplied value, never a hard-coded tariff number.

### NPCL (`npcl-fy2026-27`)
1. "What is the LMV-1 urban energy charge for 101–150 kWh on 1 August 2026?" → fact + citation + regulatory-discount condition, or `coverage_insufficient` while the effective date is `pending_external_event`.
2. "Does the 10% regulatory discount apply to green tariff?" → condition-backed `no`, citing provision 20(f).
3. "What is the TOD adjustment for HV-2 in summer between 07:00 and 16:00?" → percent component with season and hours.
4. "What is the LMV-10 tariff?" → `insufficient_evidence`, explicit absent-category explanation.
5. "What did NPCL propose for billable demand?" → `verified` explanation claim citing Chapter 7, labelled a proposal not approved.
6. "What losses apply to an open-access consumer connected at 11 kV in NPCL's area?" → 3.58% + 3.18% + 2.58% with stacking rule and citation.
7. "What is NPCL's additional surcharge?" → `approved_zero` with the deferral statement.
8. "What is the green tariff for an LMV-6 consumer?" → Rs 0.17/unit over the regular tariff with the regulatory-discount exclusion.

### KERC (`kerc-fy2025-28`)
1. "What is the BESCOM LT-1 energy charge for FY2026-27?" → paise/unit fact bound to the FY2026-27 version with the meter-reading effective rule stated.
2. "What is the HT-1 ToD adjustment between 22:00 and 06:00 in January?" → negative absolute adjustment with season, citing Annexure-9.
3. "What fixed charge applies to an IP set of 8 HP?" → `not_applicable` fixed charge with the subsidy condition.
4. "Which ESCOMs does this schedule apply to?" → all five from the schedule-scope record.
5. "What did the ESCOMs propose for HT-2(a) demand charges?" → `verified` explanation claim citing Table 6.2, labelled a proposal.
6. "What wheeling charge and losses apply for injection at HT and drawal at LT in HESCOM's area in FY2026-27?" → matrix cell (127 paise, 11.87%) with citation.
7. "What is the additional surcharge in Karnataka?" → pending-petition decision.
8. "Can I bank RE power with GESCOM?" → `by_reference` naming the separate regulations.
9. "What is the CSS for HT-2(a) at 66 kV in FY2027-28?" → 183 paise/unit.

### GERC/MGVCL (`gerc-mgvcl-fy2026-27`)
1. "What fixed charge does a 3 kW RGP consumer pay?" → Rs 25/month per connection with load-range applicability.
2. "What is the RGP energy charge for the first 50 units?" → clarification post-paid vs pre-paid, then the value.
3. "What are the agricultural tariff options?" → three-alternative option group with the Tatkal reversion condition.
4. "What is the ToU charge for an HTP-1 consumer with 800 kVA billing demand at 09:00?" → +85 paise/unit with band, window, citation.
5. "What is the FPPAS for MGVCL?" → `formula` answer with base parameters and caps; monthly value not in the order.
6. "What CSS does an HT open-access consumer of MGVCL pay in FY 2026-27?" → Rs 1.33/kWh with cap explanation and both citations.
7. "What is the additional surcharge?" → 9.87% parameter and referenced methodology.
8. "What are the banking rules in Gujarat?" → `coverage_insufficient` naming the missing source.
9. "What is the green power tariff?" → Rs 0.75/kWh over the normal tariff with the notice condition.

## Metrics to be produced per stage (Section 12)

Reading: triage accuracy, localisation precision/recall, table integrity (resolved
header/row/unit cells ÷ numeric cells), reader agreement and correction rates, channel
agreement and correction rates.  Extraction/review: coverage per charge family,
decision-status accuracy, exact numeric/unit/value_state/period/applicability accuracy,
validator precision, review minutes per candidate by risk tag, false-publication rate.
Answers: citation correctness, mapping correctness, clarification/abstention
appropriateness, latency, spoken numeric fidelity.  Operations: duration, retries, provider
tokens and cost per order/page, cross-profile artefact diffs.
