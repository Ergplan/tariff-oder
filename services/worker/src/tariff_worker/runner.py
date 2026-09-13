"""Durable job runner.

One process polls the PostgreSQL queue, claims a job, runs the registered handler while a
background thread heartbeats the lease, and records success or a typed failure.  A handler
receives a :class:`JobContext` through which it checkpoints and observes cancellation.  A
lost lease (``LeaseLost``) aborts the handler; the job is resumed by whichever worker claims
it next, from its last checkpoint.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tariff_api import queue as q
from tariff_api.config import Settings
from tariff_api.db import session_scope
from tariff_api.telemetry import job_id_var, run_id_var

log = logging.getLogger(__name__)


class JobFailure(Exception):
    """Typed failure raised by handlers.  ``retry`` decides whether the job is re-queued."""

    def __init__(self, error_type: str, message: str, *, retry: bool = True) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retry = retry


@dataclass
class JobContext:
    job_id: uuid.UUID
    run_id: uuid.UUID
    worker: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    settings: Settings
    adapters: Any
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lease_lost: threading.Event = field(default_factory=threading.Event)

    def save_checkpoint(self, stage: str, checkpoint: dict[str, Any], progress: dict[str, Any]) -> None:
        if self._lease_lost.is_set():
            raise q.LeaseLost(str(self.job_id))
        with session_scope() as s:
            q.checkpoint(
                s, self.job_id, self.run_id, worker=self.worker, stage=stage, checkpoint=checkpoint, progress=progress
            )
        self.checkpoint = checkpoint
        if self._cancel.is_set():
            raise q.CancelRequested(str(self.job_id))

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()


Handler = Callable[[JobContext], dict[str, Any]]


class Runner:
    def __init__(
        self, settings: Settings, adapters: Any, handlers: dict[str, Handler], worker_name: str | None = None
    ) -> None:
        self.settings = settings
        self.adapters = adapters
        self.handlers = handlers
        self.worker = worker_name or f"{socket.gethostname()}:{os.getpid()}"
        self._stop = threading.Event()

    def install_signal_handlers(self) -> None:
        def _stop(signum, frame):  # noqa: ANN001
            log.warning("signal received; finishing current job then stopping", extra={"signal": signum})
            self._stop.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

    def run_forever(self, poll_seconds: float = 1.0, max_jobs: int | None = None) -> int:
        """Poll until stopped.  Returns the number of jobs processed."""
        processed = 0
        while not self._stop.is_set():
            ran = self.run_once()
            if ran:
                processed += 1
                if max_jobs is not None and processed >= max_jobs:
                    break
            else:
                self._stop.wait(poll_seconds)
        return processed

    def run_once(self) -> bool:
        """Claim and run at most one job.  Returns True if a job was processed."""
        with session_scope() as s:
            job = q.claim(s, worker=self.worker, lease_seconds=self.settings.job_lease_seconds)
            if job is None:
                return False
            job_id, run_id, job_type, payload, checkpoint = (
                job.id,
                job.run_id,
                job.job_type,
                dict(job.payload),
                dict(job.checkpoint),
            )
        job_token = job_id_var.set(str(job_id))
        run_token = run_id_var.set(str(run_id))
        try:
            self._execute(job_id, run_id, job_type, payload, checkpoint)
        finally:
            job_id_var.reset(job_token)
            run_id_var.reset(run_token)
        return True

    def _execute(self, job_id: uuid.UUID, run_id: uuid.UUID, job_type: str, payload: dict, checkpoint: dict) -> None:
        ctx = JobContext(
            job_id=job_id,
            run_id=run_id,
            worker=self.worker,
            payload=payload,
            checkpoint=checkpoint,
            settings=self.settings,
            adapters=self.adapters,
        )
        stop_hb = threading.Event()
        hb = threading.Thread(target=self._heartbeat_loop, args=(ctx, stop_hb), daemon=True, name=f"hb-{job_id}")
        hb.start()
        log.info("job started", extra={"job_type": job_type, "resumed_from_checkpoint": bool(checkpoint)})
        started = time.perf_counter()
        try:
            handler = self.handlers.get(job_type)
            if handler is None:
                raise JobFailure("validation_failed", f"no handler registered for job type {job_type!r}", retry=False)
            result = handler(ctx)
            stop_hb.set()
            hb.join(timeout=5)
            with session_scope() as s:
                q.complete(
                    s,
                    ctx.job_id,
                    ctx.run_id,
                    worker=self.worker,
                    result={**result, "duration_seconds": round(time.perf_counter() - started, 2)},
                )
            log.info(
                "job succeeded",
                extra={"job_type": job_type, "duration_seconds": round(time.perf_counter() - started, 2)},
            )
        except q.CancelRequested:
            stop_hb.set()
            with session_scope() as s:
                q.cancel_from_worker(s, ctx.job_id, ctx.run_id, worker=self.worker)
            log.warning("job cancelled at checkpoint", extra={"job_type": job_type})
        except q.LeaseLost:
            stop_hb.set()
            log.error("lease lost; abandoning job to the worker that holds it now", extra={"job_type": job_type})
        except JobFailure as e:
            stop_hb.set()
            with session_scope() as s:
                try:
                    q.fail(
                        s,
                        ctx.job_id,
                        ctx.run_id,
                        worker=self.worker,
                        error_type=e.error_type,
                        message=str(e),
                        retry=e.retry,
                    )
                except q.LeaseLost:
                    log.error("lease lost while recording failure")
            log.error("job failed", extra={"job_type": job_type, "error_type": e.error_type, "retry": e.retry})
        except Exception as e:  # noqa: BLE001
            stop_hb.set()
            message = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"
            with session_scope() as s:
                try:
                    q.fail(
                        s,
                        ctx.job_id,
                        ctx.run_id,
                        worker=self.worker,
                        error_type="internal_error",
                        message=message,
                        retry=True,
                    )
                except q.LeaseLost:
                    log.error("lease lost while recording failure")
            log.exception("job crashed", extra={"job_type": job_type})
        finally:
            stop_hb.set()
            hb.join(timeout=5)

    def _heartbeat_loop(self, ctx: JobContext, stop: threading.Event) -> None:
        interval = self.settings.job_heartbeat_seconds
        while not stop.wait(interval):
            try:
                with session_scope() as s:
                    cancel = q.heartbeat(s, ctx.job_id, ctx.run_id, lease_seconds=self.settings.job_lease_seconds)
                if cancel:
                    ctx._cancel.set()
            except q.LeaseLost:
                ctx._lease_lost.set()
                log.error("heartbeat: lease lost")
                return
            except Exception:  # noqa: BLE001 - transient DB errors; the lease may still expire
                log.exception("heartbeat failed")
