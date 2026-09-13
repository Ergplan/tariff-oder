"""Helper process for the worker-death test.

Runs one inventory job but hard-exits (``os._exit``) right after the N-th checkpoint, before
the job can complete, simulating a killed container.  No cleanup code runs, so the lease is
left dangling exactly as it would be after an instance termination.
"""

from __future__ import annotations

import os
import sys

from tariff_worker.runner import JobContext

KILL_AFTER = int(os.environ.get("KILL_AFTER_CHECKPOINTS", "2"))
_count = {"n": 0}
_orig = JobContext.save_checkpoint


def _patched(self, stage, checkpoint, progress):
    _orig(self, stage, checkpoint, progress)
    _count["n"] += 1
    if _count["n"] >= KILL_AFTER:
        sys.stdout.write(f"KILLING after checkpoint {checkpoint}\n")
        sys.stdout.flush()
        os._exit(137)


JobContext.save_checkpoint = _patched  # type: ignore[method-assign]

if __name__ == "__main__":
    from tariff_worker.main import build_runner

    runner = build_runner(worker_name="killable-worker")
    ran = runner.run_once()
    sys.exit(0 if ran else 3)
