# ADR-0003 PostgreSQL-backed durable job queue

Status: accepted (Milestone 0/1)

## Decision
Jobs live in the `jobs` table.  Claim = `UPDATE … FROM (SELECT … FOR UPDATE SKIP LOCKED)`
taking queued jobs or leased jobs whose lease expired.  Every claim mints a `run_id`; all
worker writes (heartbeat, checkpoint, complete, fail, cancel) are fenced on
`(job_id, run_id, status='leased')` and raise `LeaseLost` on zero rows.  Attempts are bounded
(`retries_exhausted`).  Handlers checkpoint JSON state and upsert artefacts idempotently.

## Why not Pub/Sub or Cloud Tasks
Identical semantics in both profiles without an emulator; transactional with the data it
processes; queue depth and lease state are plain SQL for the job monitor.  A switch requires
an ADR with equivalence tests (spec 3.1).

## Verified
`tests/integration/test_queue.py`, `tests/integration/test_worker_recovery.py` (hard kill
via `os._exit` after a checkpoint, resume without duplicates).  A defect found while
writing the tests — ORM autoflush writing a stale `run_id` before the fence check — led to
the id-based fenced API; never pass mutated ORM objects to fenced writes.
