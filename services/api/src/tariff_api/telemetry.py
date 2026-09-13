"""Structured logging with request/job ids.

Both profiles emit one JSON object per line to stdout with the same event schema.  The only
platform difference is the ``severity`` key, which Cloud Logging uses to set log level
(local runs ignore it).  Never log document text, secrets, or signed URLs.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
actor_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("actor", default=None)

_SEVERITY = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, profile: str) -> None:
        super().__init__()
        self.service = service
        self.profile = profile

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "severity": _SEVERITY.get(record.levelname, "DEFAULT"),
            "level": record.levelname,
            "service": self.service,
            "profile": self.profile,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "job_id": job_id_var.get(),
            "run_id": run_id_var.get(),
            "actor": actor_var.get(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get() or job_id_var.get() or "-"
        base = f"{record.levelname:8s} [{rid}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(service: str, profile: str, fmt: str = "json", level: str = "INFO") -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, profile) if fmt == "json" else TextFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
