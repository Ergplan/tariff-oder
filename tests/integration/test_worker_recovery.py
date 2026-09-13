"""Gate: queue lease recovery after a killed worker, resuming from the checkpoint without
duplicate page rows."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ADMIN, ANALYST, headers
from fixtures.synthetic_pdfs import mixed_text_and_image_pdf

pytestmark = pytest.mark.integration

HELPER = Path(__file__).with_name("_killable_worker.py")


def test_worker_killed_mid_job_is_resumed_from_checkpoint(client, runner):
    r = client.post(
        "/sources",
        files={"file": ("SYNTHETIC.pdf", mixed_text_and_image_pdf(), "application/pdf")},
        data={"dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201
    src_id = r.json()["source"]["id"]
    job_id = r.json()["job"]["id"]

    env = {**os.environ, "KILL_AFTER_CHECKPOINTS": "2", "JOB_LEASE_SECONDS": "2"}
    proc = subprocess.run([sys.executable, str(HELPER)], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 137, proc.stdout + proc.stderr
    assert "KILLING after checkpoint" in proc.stdout

    job = client.get(f"/jobs/{job_id}", headers=headers(ANALYST)).json()
    assert job["status"] == "leased"  # dangling lease, no cleanup ran
    assert job["lease_owner"] == "killable-worker"
    assert job["checkpoint"]["next_page"] == 3  # document inventory + first batch of 2 pages
    pages_before = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["total"]
    assert pages_before == 2

    # Nobody can claim it before the lease expires
    assert runner.run_once() is False
    time.sleep(2.5)

    # Second worker reclaims the expired lease and resumes from the checkpoint
    assert runner.run_once() is True
    job = client.get(f"/jobs/{job_id}", headers=headers(ANALYST)).json()
    assert job["status"] == "succeeded"
    assert job["attempts"] == 2
    events = [e["event"] for e in job["events"]]
    assert "lease_expired_reclaimed" in events
    claims = [e for e in job["events"] if e["event"] == "claimed"]
    assert claims[-1]["detail"]["checkpoint"]["next_page"] == 3  # resumed, not restarted

    detail = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert detail["state"] == "inventoried"
    assert detail["page_count"] == 6
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()
    assert pages["total"] == 6
    assert sorted(p["page_index"] for p in pages["pages"]) == [1, 2, 3, 4, 5, 6]  # no duplicates
