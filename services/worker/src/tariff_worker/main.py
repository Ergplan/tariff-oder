"""``tariff-worker`` entrypoint.  Runs as a long-lived poller (local, Cloud Run worker
service) or drains the queue and exits (Cloud Run Job triggered by Cloud Scheduler)."""

from __future__ import annotations

import argparse
import logging

from tariff_api.adapters import build_adapters
from tariff_api.config import get_settings
from tariff_api.db import init_db
from tariff_api.telemetry import configure_logging

from .runner import Runner
from .stages.inventory import inventory_source
from .stages.localise import localise_source
from .stages.parse import parse_source
from .stages.triage import triage_source

HANDLERS = {
    "inventory_source": inventory_source,
    "triage_source": triage_source,
    "parse_source": parse_source,
    "localise_source": localise_source,
}


def build_runner(worker_name: str | None = None) -> Runner:
    settings = get_settings()
    configure_logging("tariff-worker", settings.deployment_profile.value, settings.log_format, settings.log_level)
    init_db(settings)
    # The worker serves no requests; it must not be able to authenticate anyone.
    adapters = build_adapters(settings, include_identity=False)
    return Runner(settings, adapters, HANDLERS, worker_name=worker_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tariff-worker")
    parser.add_argument("--once", action="store_true", help="process at most one job then exit")
    parser.add_argument("--drain", action="store_true", help="process jobs until the queue is empty then exit")
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--name", default=None)
    args = parser.parse_args(argv)

    runner = build_runner(args.name)
    runner.install_signal_handlers()
    log = logging.getLogger("tariff_worker")
    log.info(
        "worker started",
        extra={"worker": runner.worker, "mode": "once" if args.once else "drain" if args.drain else "forever"},
    )
    if args.once:
        return 0 if runner.run_once() else 3
    if args.drain:
        n = 0
        while runner.run_once():
            n += 1
        log.info("queue drained", extra={"processed": n})
        return 0
    runner.run_forever(poll_seconds=args.poll_seconds, max_jobs=args.max_jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
