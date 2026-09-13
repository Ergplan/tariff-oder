"""Milestone 2a gate items: page references resolve (PDF index and printed label, roman front
matter, offset labels); low-quality pages are flagged and listed; unknown is visible; the
stage resumes after an intentional worker kill without re-running completed pages; artefacts
are immutable and versioned; a rerun after a rules change writes new artefacts beside old."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ADMIN, ANALYST, headers
from fixtures.synthetic_pdfs import garbled_text_pdf, labelled_order_pdf, mixed_text_and_image_pdf

pytestmark = pytest.mark.integration

HELPER = Path(__file__).with_name("_killable_worker.py")


def _upload(client, data: bytes, name="SYNTHETIC.pdf"):
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["source"]["id"]


def test_inventory_chains_into_triage_and_resolves_labels(client, runner, storage):
    src_id = _upload(client, labelled_order_pdf(), "SYNTHETIC_labelled.pdf")

    assert runner.run_once() is True  # inventory
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "inventoried"
    assert d["triage"] is None
    jobs = client.get("/jobs", params={"source_id": src_id}, headers=headers(ANALYST)).json()
    assert {j["job_type"]: j["status"] for j in jobs["items"]} == {
        "inventory_source": "succeeded",
        "triage_source": "queued",  # chained automatically; publication never is
    }

    assert runner.run_once() is True  # triage
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "triaged"
    jobs = client.get("/jobs", params={"source_id": src_id}, headers=headers(ANALYST)).json()
    assert {j["job_type"]: j["status"] for j in jobs["items"]}["parse_source"] == "queued"  # chained (2b)
    t = d["triage"]
    assert t["triage_version"] == "1"
    assert t["page_class_counts"] == {
        "narrative": 7,
        "annexure_cover": 1,
        "table": 1,
        "vector_graphics_text_sparse": 1,
        "image_only": 1,
        "blank": 1,
    }
    assert t["ocr_recommended_pages"] == [7, 8]
    assert t["unknown_pages"] == []
    assert t["label_flagged_pages"] == [11]
    segs = t["label_rule"]["segments"]
    assert [(s["start_index"], s["end_index"], s["style"], s["offset"]) for s in segs] == [
        (1, 3, "roman_lower", 0),
        (4, 12, "decimal", -3),
    ]

    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    assert [p["printed_label"] for p in pages] == ["i", "ii", "iii", "1", "2", "3", "4", "5", "6", "7", "99", "9"]
    assert [p["label_source"] for p in pages] == ["observed"] * 6 + ["rule"] * 3 + ["observed"] * 3
    assert "label_off_rule" in pages[10]["quality_flags"]
    assert pages[6]["page_class"] == "vector_graphics_text_sparse" and pages[6]["ocr_recommended"]
    assert "overlapping_graphics" in pages[6]["quality_flags"]
    assert pages[5]["page_class"] == "table" and pages[5]["text_quality"]["glyph_coverage"] == 1.0
    assert all(p["triage_rationale"] for p in pages)  # every decision explains itself
    assert all(p["triaged_at"] for p in pages)

    # filters
    ocr = client.get(f"/sources/{src_id}/pages", params={"ocr_recommended": "true"}, headers=headers(ANALYST)).json()
    assert [p["page_index"] for p in ocr["pages"]] == [7, 8]
    tables = client.get(f"/sources/{src_id}/pages", params={"page_class": "table"}, headers=headers(ANALYST)).json()
    assert [p["page_index"] for p in tables["pages"]] == [6]

    # artefacts: one per page plus a document-level one, immutable, versioned by tool + rules
    art = d["artefacts"]
    doc_art = [a for a in art if a["page_index"] == 0]
    assert len(doc_art) == 1 and doc_art[0]["stage"] == "triage"
    assert doc_art[0]["tool_version"].endswith("+rules@1")
    body = json.loads(storage.get("artefacts", doc_art[0]["object_key"]))
    assert body["label_rule"]["segments"] == segs
    page_art = json.loads(storage.get("artefacts", art[1]["object_key"]))
    assert page_art["page_index"] == 1 and page_art["triage"]["page_class"] == "narrative"
    assert page_art["label_observed"] == "i"


def test_garbled_text_layer_is_flagged_and_listed(client, runner):
    src_id = _upload(client, garbled_text_pdf(), "SYNTHETIC_garbled.pdf")
    assert runner.run_once() and runner.run_once()
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["triage"]["low_quality_pages"] == [1]
    assert d["triage"]["ocr_recommended_pages"] == [1]
    page = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"][0]
    assert page["has_text_layer"] is True  # a text layer exists...
    assert "text_not_wordlike" in page["quality_flags"]  # ...and is useless
    assert page["text_quality"]["dictionary_hit_rate"] < 0.1


def test_declared_labels_survive_triage_and_sparse_pages_are_unknown(client, runner):
    src_id = _upload(client, mixed_text_and_image_pdf(), "SYNTHETIC_mixed.pdf")
    assert runner.run_once() and runner.run_once()
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    assert [p["printed_label"] for p in pages] == ["i", "ii", "1", "2", "3", "4"]
    assert all(p["label_source"] == "declared" for p in pages)
    assert d["triage"]["label_flagged_pages"] == []
    # two lines of text is not enough to call a page anything; and a small image is not a scan
    assert d["triage"]["unknown_pages"] == [1, 2, 3, 4, 5, 6]
    assert d["triage"]["ocr_recommended_pages"] == [5, 6]


def test_triage_resumes_after_worker_kill_without_reprocessing(client, runner, storage):
    src_id = _upload(client, labelled_order_pdf(), "SYNTHETIC_labelled.pdf")
    assert runner.run_once() is True  # inventory; triage is now queued

    env = {**os.environ, "KILL_AFTER_CHECKPOINTS": "3", "JOB_LEASE_SECONDS": "2"}
    proc = subprocess.run([sys.executable, str(HELPER)], env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 137, proc.stdout + proc.stderr

    jobs = client.get("/jobs", params={"source_id": src_id}, headers=headers(ANALYST)).json()["items"]
    triage_job = next(j for j in jobs if j["job_type"] == "triage_source")
    assert triage_job["status"] == "leased"
    assert triage_job["checkpoint"]["next_page"] == 5  # initial + two batches of 2
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    assert [p["page_index"] for p in pages if p["triaged_at"]] == [1, 2, 3, 4]
    artefacts_before = {
        a["object_key"] for a in client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()["artefacts"]
    }

    assert runner.run_once() is False  # lease still held
    time.sleep(3.5)  # lease is 2 s; leave a margin for a loaded CI runner
    assert runner.run_once() is True  # reclaimed and resumed

    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "triaged"
    job = client.get(f"/jobs/{triage_job['id']}", headers=headers(ANALYST)).json()
    assert job["status"] == "succeeded" and job["attempts"] == 2
    claims = [e for e in job["events"] if e["event"] == "claimed"]
    assert claims[-1]["detail"]["checkpoint"]["next_page"] == 5  # resumed, not restarted
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    assert all(p["triaged_at"] for p in pages)
    assert artefacts_before <= {a["object_key"] for a in d["artefacts"]}
    assert d["triage"]["page_class_counts"]["narrative"] == 7


def test_stage_rerun_keeps_old_artefacts_and_is_audited(client, runner, storage):
    src_id = _upload(client, labelled_order_pdf(), "SYNTHETIC_labelled.pdf")
    assert runner.run_once() and runner.run_once()
    before = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert before["state"] == "triaged"

    r = client.post(f"/sources/{src_id}/stages/rerun", json={"job_type": "triage_source"}, headers=headers(ADMIN))
    assert r.status_code == 202, r.text
    assert r.json()["job_type"] == "triage_source" and r.json()["status"] == "queued"
    mid = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert mid["state"] == "inventoried"  # moved back through the transition table, audited
    # the parse job triage had chained is stale now: cancelled, never run against the rolled-back state
    jobs = client.get("/jobs", params={"source_id": src_id}, headers=headers(ANALYST)).json()["items"]
    assert sorted(j["status"] for j in jobs if j["job_type"] == "parse_source") == ["cancelled"]
    assert sorted(j["status"] for j in jobs if j["job_type"] == "triage_source") == ["queued", "succeeded"]
    audit = client.get(
        "/audit", params={"entity_type": "source_document", "entity_id": src_id}, headers=headers(ADMIN)
    ).json()
    assert any(a["reason"] == "rerun triage_source" for a in audit)

    assert runner.run_once() is True
    after = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert after["state"] == "triaged"
    assert after["triage"]["label_rule"] == before["triage"]["label_rule"]
    # same rules version -> same artefact keys; nothing overwritten, nothing duplicated
    assert {a["object_key"] for a in after["artefacts"]} == {a["object_key"] for a in before["artefacts"]}

    # analysts cannot trigger reruns; unknown stages are refused
    assert (
        client.post(
            f"/sources/{src_id}/stages/rerun", json={"job_type": "triage_source"}, headers=headers(ANALYST)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/sources/{src_id}/stages/rerun", json={"job_type": "extract_source"}, headers=headers(ADMIN)
        ).status_code
        == 422
    )
