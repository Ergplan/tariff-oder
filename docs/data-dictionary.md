# Data dictionary (Milestone 1)

Migration owner: `services/api/migrations/versions/0001_foundation.py`.  All timestamps are
`timestamptz`; ids are UUIDv4 unless noted.  Enums are PostgreSQL enum types.

## `datasets`
| Column | Type | Meaning |
| --- | --- | --- |
| kind | `dataset_kind` (`real`, `fixture`) | Unique per kind (`uq_datasets_kind`): exactly one real and one fixture dataset |
| name | text | `real` / `fixture` |

Isolation rule (working agreement 12): `utilities.dataset_id` and `source_documents.dataset_id`
are foreign keys; every list endpoint carries `dataset_kind`; the UI labels fixture records.
A real utility linked to a fixture source will be rejected by the order-registration
service in Milestone 3 (link does not exist yet).

## `users`
`email` (unique), `display_name`, `role` (`user_role`: analyst | reviewer | administrator),
`active`.  Under the `gcp` profile IAP authenticates and this table authorises; under
`local` the allow-list carries the role.  Role changes are audit events.

## `jurisdictions`, `commissions`, `utilities`
Stable identities with `code`, `name`, `aliases` (JSONB list).  `utilities` additionally:
`licensed_area`, `active_reading_profile`, `active_reading_profile_version` (null until a
profile version is published in Milestone 3), `dataset_id`.  A state is not a schedule;
nothing here implies coverage.

## `source_documents`
| Column | Meaning |
| --- | --- |
| sha256 (unique), size_bytes, original_filename, content_type | Immutable identity of the bytes |
| provenance_url, acquired_at, uploaded_by | Provenance |
| object_key | `<sha256>.pdf` in the logical `sources` bucket |
| state, state_reason | `source_state` enum; transitions in `models.SOURCE_TRANSITIONS`; each transition is an audit event |
| page_count, pdf_version, producer, creator, is_encrypted, is_tagged, fonts_total, fonts_not_embedded | Document-level inventory; null until the inventory stage ran (never guessed) |
| pages_with_text, pages_without_text, inventory_tool, inventory_tool_version, inventoried_at | Text-layer summary and tool provenance |
| golden_id, manifest_check | Set when the hash matches `tests/golden/manifest.json`; `manifest_check` records expected vs observed per field |
| superseded_by_id | Supersession link (set by later milestones' supersede action) |
| version | Optimistic-concurrency counter; incremented on every transition |

## `source_pages`
One row per PDF page (`page_index` 1-based, unique per source): `printed_label` (PDF
page-label entry if the file declares one; footer-derived labels come in Milestone 2),
`width_pt`, `height_pt`, `rotation`, `text_chars` (non-whitespace characters from the text
layer), `has_text_layer`, `image_count`, `drawing_count`, `page_class` (Section 6.3;
`unknown` until Milestone 2), `page_role` (Section 6.5; `unknown` until Milestone 3),
`quality_flags` (JSONB list).

## `jobs`, `job_events`
| Column | Meaning |
| --- | --- |
| job_type, payload, idempotency_key (unique) | What to run; enqueue is idempotent |
| status | `job_status`: queued, leased, succeeded, failed, cancelled |
| priority, available_at | Ordering and delayed retry |
| attempts, max_attempts | Bounded retries; exceeding yields `retries_exhausted` |
| lease_owner, lease_expires_at, heartbeat_at, run_id | Lease; every claim mints a new run_id; writes are fenced on it |
| stage, checkpoint, progress | Resume point and UI progress (e.g. `{next_page}`, `{pages_done, pages_total}`) |
| cancel_requested | Observed by the handler at its next checkpoint/heartbeat |
| error_type, error_message | Typed failure (taxonomy in `errors.py`) |

`job_events`: append-only trail (`enqueued`, `claimed`, `lease_expired_reclaimed`,
`checkpoint`, `retry_scheduled`, `failed`, `succeeded`, `cancel_requested`, `cancelled`).

## `audit_events`
Append-only (UPDATE/DELETE raise via trigger): `actor`, `action`, `entity_type`, `entity_id`,
`before`, `after`, `reason`, `request_id`, `at`.

## `idempotency_records`
`(key, actor)` → request fingerprint, stored status and body, for `Idempotency-Key` replays.

## Reserved for later milestones (not created yet)
Regulatory order, schedule version, effective rule, category/version, option group, category
mapping, charge component, slab/time band, condition/rule, evidence span, table grid,
candidate, review decision, publication, coverage record, network charge determination,
loss record, reading profile, failure report — Section 5.2.  `value_state` and
`decision_status` enums will be introduced with the candidate schema (Milestone 4).
