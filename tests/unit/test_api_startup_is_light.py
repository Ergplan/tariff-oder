"""The API process must start fast: importing the application never loads Haystack (the
worker's retrieval library), which costs seconds and tens of megabytes and on 2026-09-17
pushed Cloud Run start-up past its probe and left the API unreachable."""

from __future__ import annotations

import subprocess
import sys


def test_importing_the_api_application_does_not_load_haystack():
    code = (
        "import sys, tariff_api.main; print(sorted(m for m in sys.modules if m.startswith('haystack'))[:3] or 'clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "clean", out.stdout
