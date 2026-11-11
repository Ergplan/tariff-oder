"""Paths and settings, from the environment (never from a file that holds a secret)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent  # tools/arrnet
REPO = TOOL.parent.parent
ARRDB = Path(os.environ.get("ARRDB_PATH", REPO / "tools" / "arrdb"))

if str(ARRDB) not in sys.path:
    sys.path.insert(0, str(ARRDB))  # arrdb is reused, not copied


def state_dir() -> Path:
    """Local work area: page text, each reader's readings, the ledger, the auditor's last run."""
    d = Path(os.environ.get("ARRNET_STATE", TOOL / ".state"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdf_dir() -> Path | None:
    """Where the downloaded orders are, named <sha256>.pdf (ARRNET_PDF_DIR)."""
    v = os.environ.get("ARRNET_PDF_DIR")
    return Path(v) if v else None


def default_manifest() -> Path:
    return ARRDB / "data" / "orders.json"


def default_manifests() -> list[Path]:
    """The DISCOM orders and, when present, the TRANSCO orders."""
    t = ARRDB / "data" / "orders-transco.json"
    return [default_manifest(), *([t] if t.exists() else [])]
