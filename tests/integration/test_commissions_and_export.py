"""Increment 20: an order belongs to a utility (its reading profile binds at registration
and the commission's reviewer is inherited); commissions are the folders the operator
works in; an order exports as JSON files (zip download, export bucket, local directory)."""

from __future__ import annotations

import io
import json
import shutil
import zipfile

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import structure_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
CONFIRM = {"decision": "confirm", "rationale": "Annexure located; pages checked", "pages_viewed": True}


def _seed(app):
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        seed_registry(s)


def _run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def test_an_order_registered_under_a_utility_binds_its_profile_and_inherits_the_commission_reviewer(client, app):
    _seed(app)
    # the commission's reviewer, set before the order arrives
    r = client.put("/commissions/UPERC/assignment", json={"reviewer": REVIEWER}, headers=headers(ADMIN))
    assert r.status_code == 200 and r.json()["assigned_to"] == REVIEWER
    assert (
        client.put("/commissions/UPERC/assignment", json={"reviewer": REVIEWER}, headers=headers(REVIEWER)).status_code
        == 403
    )
    r = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_npcl.pdf", structure_order_pdf() + b"\n%commission-test\n", "application/pdf")},
        data={"dataset_kind": "fixture", "utility_code": "npcl"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    src = r.json()["source"]
    assert src["utility_code"] == "NPCL" and src["commission_code"] == "UPERC" and src["assigned_to"] == REVIEWER
    d = client.get(f"/sources/{src['id']}", headers=headers(ANALYST)).json()
    assert d["reading_profile"]["profile_id"] == "uperc-npcl" and d["reading_profile"]["source"] == "utility"
    # unknown utility is refused; the commission folder lists the order
    r = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_x.pdf", structure_order_pdf(), "application/pdf")},
        data={"dataset_kind": "fixture", "utility_code": "NOPE"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 422
    folders = client.get("/commissions", headers=headers(ANALYST)).json()["commissions"]
    up = next(c for c in folders if c["code"] == "UPERC")
    npcl = next(u for u in up["utilities"] if u["code"] == "NPCL")
    assert up["assigned_to"] == REVIEWER and npcl["sources"] == 1 and up["jurisdiction_code"] == "UP"
    listed = client.get("/sources", params={"commission": "uperc"}, headers=headers(ANALYST)).json()
    assert [x["id"] for x in listed["items"]] == [src["id"]]
    assert client.get("/sources", params={"commission": "KERC"}, headers=headers(ANALYST)).json()["total"] == 0


def test_an_order_exports_as_json_files_in_a_zip_and_to_the_export_bucket(client, app, runner, storage, tmp_path):
    _seed(app)
    r = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_export.pdf", structure_order_pdf() + b"\n%export-test\n", "application/pdf")},
        data={"dataset_kind": "fixture", "utility_code": "NPCL"},
        headers=headers(ADMIN),
    )
    src_id = r.json()["source"]["id"]
    _run_all(runner)
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    _run_all(runner)
    r = client.get(f"/sources/{src_id}/export.zip", headers=headers(ANALYST))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = {n.split("/", 1)[1] for n in z.namelist()}
    assert {
        "source.json",
        "localisation.json",
        "candidates.json",
        "decisions.json",
        "summaries.json",
        "findings.json",
        "runs.json",
        "README.txt",
    } <= names
    assert any(n.startswith("pages/page-") for n in names)
    root = z.namelist()[0].split("/", 1)[0]
    source = json.loads(z.read(f"{root}/source.json"))
    assert source["utility"] == "NPCL" and source["commission"] == "UPERC" and source["state"] == "awaiting_review"
    cands = json.loads(z.read(f"{root}/candidates.json"))
    assert cands and all(c["review_status"] == "pending" for c in cands) and "record" in cands[0]
    page = json.loads(z.read(sorted(n for n in z.namelist() if "/pages/" in n)[0]))
    assert page["grids"] and page["cells"]
    # the CLI writes the same files to the bucket and a local folder
    from tariff_api.cli import main as cli_main

    assert cli_main(["export", src_id, "--out", str(tmp_path)]) == 0
    local = next(tmp_path.iterdir())
    assert (local / "source.json").is_file() and (local / "candidates.json").is_file()
    keys = [o.key for o in storage.list("exports", prefix="UPERC/NPCL/")]
    assert any(k.endswith("/candidates.json") for k in keys)
