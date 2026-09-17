"""Milestone 2b gate items: OCR runs on the pages triage routed to it and its confidence is
recorded; reader disagreement is visible per table with both grids kept; a silently empty
grid is recorded and never treated as a table; the heading inventory counts each schedule
once; the stage resumes after a kill and re-runs without duplicating grids."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ADMIN, ANALYST, headers
from fixtures.synthetic_pdfs import labelled_order_pdf, readers_and_headings_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed"),
]

HELPER = Path(__file__).with_name("_killable_worker.py")


def _upload(client, data: bytes, name: str) -> str:
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["source"]["id"]


def _run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def test_parse_readers_headings_and_ocr_end_to_end(client, runner, storage):
    src_id = _upload(client, readers_and_headings_pdf(), "SYNTHETIC_readers.pdf")
    assert _run_all(runner) == 4  # inventory -> triage -> parse -> localise, chained
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised"
    assert d["parse"]["parse_version"] == "3"
    tv = d["parse"]["table_summary"]["tool_version"]
    assert tv.startswith("pymupdf@") and "+pdfplumber@" in tv and "+tesseract@" in tv and "absent" not in tv

    # headings: each schedule once, KERC duplicate collapsed, dash variants canonical
    h = client.get(f"/sources/{src_id}/headings", headers=headers(ANALYST)).json()
    assert [(x["page_index"], x["kind"], x["code_canonical"]) for x in h["headings"]] == [
        (1, "tariff_schedule", "LT-1"),
        (2, "rate_clause", "RGP"),
        (3, "rate_schedule", "LMV-1"),
        (4, "rate_schedule", "LMV-1"),  # read back by OCR from the scanned copy of page 3
        (5, "chapter", "6"),
        (5, "table_caption", "6-7"),
    ]
    assert h["headings"][3]["text_source"] == "ocr" and h["headings"][2]["text_source"] == "text_layer"
    assert [x["ordinal"] for x in h["headings"]] == [1, 2, 3, 4, 5, 6]
    inv = h["inventory"]
    assert inv["counts"] == {
        "tariff_schedule": 1,
        "rate_clause": 1,
        "rate_schedule": 2,
        "chapter": 1,
        "table_caption": 1,
    }
    assert inv["repeated_codes"]["rate_schedule"] == ["LMV-1"]  # the scan repeats the printed page: shown, not hidden
    one = client.get(f"/sources/{src_id}/headings", params={"kind": "rate_clause"}, headers=headers(ANALYST))
    assert one.json()["total"] == 1

    # table grids: unruled KERC-style page via text strategy, ruled UPERC page and Table 6-7 via rulings
    t = client.get(f"/sources/{src_id}/tables", headers=headers(ANALYST)).json()
    by_page = {}
    for g in t["grids"]:
        by_page.setdefault(g["page_index"], []).append(g)
    assert sorted(by_page) == [1, 3, 5]
    for page, strategy in ((1, "text"), (3, "lines"), (5, "lines")):
        grids = by_page[page]
        assert {g["reader"] for g in grids} == {"pymupdf", "pdfplumber"}
        assert all(g["strategy"] == strategy for g in grids)
        assert all(g["agreement_class"] == "high_agreement" for g in grids), grids
        prim = next(g for g in grids if g["is_primary"])
        assert prim["reader"] == "pymupdf" and prim["row_count"] >= 4 and prim["col_count"] == 4
        grid = json.loads(storage.get("artefacts", prim["object_key"]))
        assert grid["agreement"]["cell_equality"] == 1.0
        assert any("Description" in row or "Particulars" in row for row in grid["grid"]["rows"])
    assert d["parse"]["table_summary"]["primary_grids"] == 3
    assert d["parse"]["table_summary"]["agreement_classes"] == {"high_agreement": 6}
    assert d["parse"]["table_summary"]["pages_needing_review"] == []
    only_primary = client.get(
        f"/sources/{src_id}/tables", params={"primary_only": "true"}, headers=headers(ANALYST)
    ).json()
    assert only_primary["total"] == 3

    # OCR on the scanned page: confidence recorded, words read, grids from OCR honestly pending
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    scan = pages[3]
    assert scan["page_class"] == "image_only" and scan["ocr_used"] is True
    assert scan["ocr_engine"].startswith("tesseract@")
    assert scan["ocr_confidence"] > 60 and scan["ocr_word_count"] > 20
    assert scan["ocr_agreement"] is None  # no text layer to compare with
    assert "grid_from_ocr_pending" in scan["quality_flags"]
    assert "ocr_low_confidence" not in scan["quality_flags"]
    assert d["parse"]["table_summary"]["ocr_pages"] == [4]
    assert d["parse"]["table_summary"]["grid_from_ocr_pending_pages"] == [4]
    assert all(p["ocr_used"] is False for i, p in enumerate(pages) if i != 3)
    # the detail lists document-level artefacts plus a sample of page ones; find the OCR
    # artefact by its immutable key prefix <sha>/parse/<tool_version>/ocr/
    ocr_keys = [o.key for o in storage.list("artefacts", prefix=f"{d['sha256']}/parse/") if "/ocr/" in o.key]
    assert len(ocr_keys) == 1, ocr_keys
    ocr = json.loads(storage.get("artefacts", ocr_keys[0]))
    assert ocr["dpi"] == 300 and ocr["psm"] == 4 and ocr["words"][0]["conf"] > 0
    assert "RATE SCHEDULE" in ocr["text"]


def test_silent_empty_grid_and_unreadable_vector_page_are_findings(client, runner, storage):
    src_id = _upload(client, labelled_order_pdf(), "SYNTHETIC_labelled.pdf")
    assert _run_all(runner) == 4
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised"
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]

    # page 7: vector strokes, no text -> OCR ran and found nothing; recorded, not guessed
    vector = pages[6]
    assert vector["ocr_used"] and vector["ocr_word_count"] == 0
    assert {"ocr_low_confidence", "ocr_no_text"} <= set(vector["quality_flags"])
    # its grids were never attempted from the text layer (there is none); pdfplumber's phantom
    # table on this page would only be produced by the readers, which run on text-layer pages
    t = client.get(f"/sources/{src_id}/tables", params={"page_index": 7}, headers=headers(ANALYST)).json()
    assert t["total"] == 0
    # page 8: grey image, nothing to read
    assert pages[7]["ocr_used"] and pages[7]["ocr_word_count"] == 0
    assert d["parse"]["table_summary"]["ocr_low_confidence_pages"] == [7, 8]

    # page 6: the ruled rate table - both readers, high agreement
    t = client.get(f"/sources/{src_id}/tables", params={"page_index": 6}, headers=headers(ANALYST)).json()
    assert {g["agreement_class"] for g in t["grids"]} == {"high_agreement"}
    assert d["parse"]["heading_inventory"]["counts"] == {"rate_schedule": 1, "annexure": 1}
    assert d["parse"]["heading_inventory"]["unique_codes"]["rate_schedule"] == ["LMV-1"]


def test_silent_empty_grid_from_secondary_reader_is_recorded_never_extracted(client, runner, storage):
    """Force the reader pair onto the vector page by classing it `table` (as a reviewer might
    when the rules misfire): pdfplumber returns a grid of empty cells, PyMuPDF returns none."""
    from sqlalchemy import update

    from tariff_api.db import session_scope
    from tariff_api.models import SourcePage

    src_id = _upload(client, labelled_order_pdf(), "SYNTHETIC_labelled.pdf")
    assert runner.run_once() and runner.run_once()  # inventory, triage
    import uuid as _uuid

    with session_scope() as s:
        s.execute(
            update(SourcePage)
            .where(SourcePage.source_id == _uuid.UUID(src_id), SourcePage.page_index == 6)
            .values(has_text_layer=True)
        )
        # page 6 already is a text-layer table; also drive the vector page through the readers
        s.execute(
            update(SourcePage)
            .where(SourcePage.source_id == _uuid.UUID(src_id), SourcePage.page_index == 7)
            .values(page_class="table", has_text_layer=True, ocr_recommended=False)
        )
    assert runner.run_once() is True  # parse
    t = client.get(f"/sources/{src_id}/tables", params={"page_index": 7}, headers=headers(ANALYST)).json()
    assert t["total"] == 1
    g = t["grids"][0]
    assert g["reader"] == "pdfplumber" and g["is_primary"] is False and g["is_empty"] is True
    assert g["agreement_class"] == "primary_missing"
    assert "empty_grid" in g["risk_tags"]
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert 7 in d["parse"]["table_summary"]["pages_needing_review"]
    page7 = client.get(f"/sources/{src_id}/pages", params={"page_class": "table"}, headers=headers(ANALYST)).json()[
        "pages"
    ]
    assert any("empty_grid" in p["quality_flags"] for p in page7 if p["page_index"] == 7)


def test_parse_resumes_after_kill_and_rerun_replaces_grids_without_duplicates(client, runner):
    src_id = _upload(client, readers_and_headings_pdf(), "SYNTHETIC_readers.pdf")
    assert runner.run_once() and runner.run_once()  # inventory, triage; parse queued

    env = {**os.environ, "KILL_AFTER_CHECKPOINTS": "2", "JOB_LEASE_SECONDS": "2"}
    proc = subprocess.run([sys.executable, str(HELPER)], env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 137, proc.stdout + proc.stderr
    jobs = client.get("/jobs", params={"source_id": src_id}, headers=headers(ANALYST)).json()["items"]
    parse_job = next(j for j in jobs if j["job_type"] == "parse_source")
    assert parse_job["status"] == "leased" and parse_job["checkpoint"]["next_page"] == 3
    pages = client.get(f"/sources/{src_id}/pages", headers=headers(ANALYST)).json()["pages"]
    assert [p["page_index"] for p in pages if p["parsed_at"]] == [1, 2]

    time.sleep(3.5)  # lease is 2 s; leave a margin for a loaded CI runner
    assert runner.run_once() is True
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "parsed"
    grids_after_resume = client.get(f"/sources/{src_id}/tables", headers=headers(ANALYST)).json()["total"]
    assert grids_after_resume == 6
    job = client.get(f"/jobs/{parse_job['id']}", headers=headers(ANALYST)).json()
    assert job["status"] == "succeeded" and job["attempts"] == 2
    assert [e for e in job["events"] if e["event"] == "claimed"][-1]["detail"]["checkpoint"]["next_page"] == 3

    # rerun at the same version: same grids, same headings, same artefact keys - nothing duplicated
    r = client.post(f"/sources/{src_id}/stages/rerun", json={"job_type": "parse_source"}, headers=headers(ADMIN))
    assert r.status_code == 202
    assert runner.run_once() is True
    d2 = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d2["state"] == "parsed"
    assert client.get(f"/sources/{src_id}/tables", headers=headers(ANALYST)).json()["total"] == 6
    assert client.get(f"/sources/{src_id}/headings", headers=headers(ANALYST)).json()["total"] == 6
    assert {a["object_key"] for a in d2["artefacts"]} == {a["object_key"] for a in d["artefacts"]}
