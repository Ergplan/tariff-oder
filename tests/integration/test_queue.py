"""Queue semantics: idempotent enqueue, fenced writes, lease expiry recovery, bounded retries."""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.fixture()
def db(app):
    from tariff_api.db import init_db, session_scope

    init_db(app.state.settings)
    return session_scope


def test_enqueue_is_idempotent(db):
    from tariff_api import queue as q

    with db() as s:
        j1, created1 = q.enqueue(s, job_type="noop", payload={"a": 1}, idempotency_key="k")
        j2, created2 = q.enqueue(s, job_type="noop", payload={"a": 2}, idempotency_key="k")
        assert created1 and not created2
        assert j1.id == j2.id
        assert q.queue_depth(s)["queued"] == 1


def test_claim_heartbeat_fencing_and_lease_expiry(db):
    from tariff_api import queue as q
    from tariff_api.models import Job, JobEvent, JobStatus

    with db() as s:
        job, _ = q.enqueue(s, job_type="noop", payload={}, idempotency_key="lease")
        job_id = job.id

    with db() as s:
        a = q.claim(s, worker="A", lease_seconds=1)
        assert a is not None and a.id == job_id and a.status == JobStatus.leased
        run_a = a.run_id

    with db() as s:
        assert q.claim(s, worker="B", lease_seconds=1) is None  # still leased by A

    time.sleep(1.3)  # A dies without heartbeating; lease expires
    with db() as s:
        b = q.claim(s, worker="B", lease_seconds=5)
        assert b is not None and b.id == job_id
        assert b.run_id != run_a
        assert b.attempts == 2
        run_b = b.run_id
        events = [
            e.event
            for e in s.execute(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id)).scalars()
        ]
        assert events == ["enqueued", "claimed", "lease_expired_reclaimed", "claimed"]

    # A wakes up and tries to heartbeat/checkpoint/complete with its stale run id -> fenced out
    for op in (
        lambda s: q.heartbeat(s, job_id, run_a, lease_seconds=5),
        lambda s: q.checkpoint(s, job_id, run_a, worker="A", stage="x", checkpoint={"n": 9}, progress={}),
        lambda s: q.complete(s, job_id, run_a, worker="A", result={}),
    ):
        with pytest.raises(q.LeaseLost):
            with db() as s:
                op(s)
    with db() as s:
        assert s.get(Job, job_id).run_id == run_b  # A's writes never landed

    # B completes normally
    with db() as s:
        q.checkpoint(s, job_id, run_b, worker="B", stage="x", checkpoint={"n": 1}, progress={"done": 1})
        q.complete(s, job_id, run_b, worker="B", result={"ok": True})
    with db() as s:
        final = s.get(Job, job_id)
        assert final.status == JobStatus.succeeded
        assert final.lease_owner is None and final.checkpoint == {"n": 1}


def test_retries_are_bounded(db):
    from tariff_api import queue as q
    from tariff_api.models import Job, JobStatus

    with db() as s:
        job, _ = q.enqueue(s, job_type="noop", payload={}, idempotency_key="bounded", max_attempts=2)
        job_id = job.id
    for attempt in (1, 2):
        with db() as s:
            j = q.claim(s, worker="W", lease_seconds=5)
            assert j is not None and j.attempts == attempt
            q.fail(
                s,
                j.id,
                j.run_id,
                worker="W",
                error_type="provider_unavailable",
                message="boom",
                retry=True,
                retry_delay_seconds=0,
            )
    with db() as s:
        j = s.get(Job, job_id)
        assert j.status == JobStatus.failed
        assert j.error_type == "retries_exhausted"
        assert q.claim(s, worker="W", lease_seconds=5) is None


def test_expired_lease_beyond_max_attempts_fails_typed(db):
    from tariff_api import queue as q
    from tariff_api.models import Job, JobStatus

    with db() as s:
        job, _ = q.enqueue(s, job_type="noop", payload={}, idempotency_key="crashloop", max_attempts=1)
        job_id = job.id
    with db() as s:
        assert q.claim(s, worker="W1", lease_seconds=1) is not None
    time.sleep(1.2)
    with db() as s:
        assert q.claim(s, worker="W2", lease_seconds=1) is None  # reclaimed and immediately failed
        j = s.get(Job, job_id)
        assert j.status == JobStatus.failed and j.error_type == "retries_exhausted"


def test_cancel_requested_is_observed_at_heartbeat(db):
    from tariff_api import queue as q
    from tariff_api.models import Job

    with db() as s:
        job, _ = q.enqueue(s, job_type="noop", payload={}, idempotency_key="cancel")
        job_id = job.id
    with db() as s:
        j = q.claim(s, worker="W", lease_seconds=5)
        run = j.run_id
    with db() as s:
        assert q.request_cancel(s, s.get(Job, job_id), actor="admin") == "cancel_requested"
    with db() as s:
        assert q.heartbeat(s, job_id, run, lease_seconds=5) is True
        q.cancel_from_worker(s, job_id, run, worker="W")
    with db() as s:
        assert s.get(Job, job_id).status.value == "cancelled"
        assert q.request_cancel(s, s.get(Job, job_id), actor="admin") == "not_cancellable"


def test_skip_locked_concurrent_claims(db):
    """Two sessions claiming concurrently never receive the same job."""
    from sqlalchemy.orm import Session

    from tariff_api import queue as q
    from tariff_api.db import get_engine

    with db() as s:
        for i in range(2):
            q.enqueue(s, job_type="noop", payload={}, idempotency_key=f"conc-{i}")
    engine = get_engine()
    s1, s2 = Session(engine), Session(engine)
    try:
        j1 = q.claim(s1, worker="S1", lease_seconds=5)  # holds row lock until commit
        j2 = q.claim(s2, worker="S2", lease_seconds=5)  # must skip the locked row
        assert j1 is not None and j2 is not None
        id1, id2 = j1.id, j2.id
        s1.commit()
        s2.commit()
    finally:
        s1.close()
        s2.close()
    assert isinstance(id1, uuid.UUID) and id1 != id2
