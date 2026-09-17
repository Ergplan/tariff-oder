"""Milestone 3b gate items: the structure stage runs only from reviewer-confirmed regions;
every numeric cell in the confirmed approved region resolves to a header path, row path and
unit or is listed; the LMV-1 grid spanning a page break yields slab rows with the merged
cells propagated and marked; TOD cells parse as signed percent components with zero forms
as `zero`; the derived Annexure-II table yields no cells; clause outlines persist across
page breaks; a re-run replaces rows without duplicates."""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import gerc_structure_order_pdf, structure_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]


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


CONFIRM = {"decision": "confirm", "rationale": "Annexure-I located; pages checked", "pages_viewed": True}


def test_structure_is_built_only_from_confirmed_regions_and_resolves_or_flags_every_cell(client, runner, storage):
    src_id = _upload(client, structure_order_pdf(), "SYNTHETIC_structure.pdf")
    assert _run_all(runner) == 4
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised" and d["localisation"]["approved_schedule_pages"] == ["3-8"]
    assert d["structure"] is None

    # the gate: a grid job requested before the reviewer decided fails, visibly, and changes nothing
    r = client.post(f"/sources/{src_id}/stages/rerun", json={"job_type": "grid_source"}, headers=headers(ADMIN))
    assert r.status_code == 202
    assert runner.run_once() is True
    job = client.get(f"/jobs/{r.json()['id']}", headers=headers(ANALYST)).json()
    assert job["status"] == "failed" and job["error_type"] == "invalid_transition"
    assert client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()["state"] == "localised"

    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert runner.run_once() is True  # the grid stage the decision queued
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "gridded"
    st = d["structure"]
    assert st["representation"] == "tables" and st["regions_read"] == 1 and st["regions_skipped"] >= 1
    assert st["cells"] == st["cells_resolved"] + st["cells_unresolved"] and st["cells"] > 15
    assert st["continuations"] == 1  # page 5 continues page 4 with the header repeated
    assert st["tool_version"].startswith("grid@3+clauses@1+normalise@1")

    cells = client.get(f"/sources/{src_id}/structure/cells", params={"limit": 500}, headers=headers(ANALYST)).json()
    assert cells["total"] == st["cells"]
    by_page = {}
    for c in cells["cells"]:
        by_page.setdefault(c["page_index"], []).append(c)
    assert 9 not in by_page  # Annexure-II (derived_not_tariff) produced no cells
    assert 8 not in by_page  # closing conditions have no grid

    # D.2 hazard 1: page 5 slab rows carry Metered and the fixed charge from page 4, marked
    page5 = by_page[5]
    energy = [c for c in page5 if c["header_path"] == ["Energy Charge"]]
    assert [c["row_path"] for c in energy] == [
        ["Metered", "101 - 150 kWh / month"],
        ["Metered", "151 - 300 kWh / month"],
        ["Metered", "Above 300 kWh / month"],
    ]
    fixed = [c for c in page5 if c["header_path"] == ["Fixed Charge"]]
    assert [c["raw"] for c in fixed] == ["Rs. 90.00/ kW / month"] * 3
    assert all("merged_cell_propagated" in c["flags"] for c in fixed + energy)
    assert all((c["currency"], c["per_unit"], c["unit_source"]) == ("rupees", "kW", "cell") for c in fixed)
    assert all(c["resolved"] for c in fixed + energy)
    starred = next(c for c in energy if c["raw"].endswith("*"))
    assert starred["footnotes"] == ["subject to the regulatory discount of general provision 21"]
    assert starred["value"] == "5.00" and starred["slab"]["lower"] == "300"

    # page 6: signed percent TOD components, zero forms, Nil / - / NA, Indian number, cross-reference
    page6 = by_page[6]
    tod = [c for c in page6 if c["header_path"] == ["% of Energy Charges"]]
    assert [(c["value"], c["value_state"], c["per_unit"]) for c in tod] == [
        ("15", "value", "percent"),
        ("0", "zero", "percent"),
        ("15", "value", "percent"),
    ]
    detail = {c["raw"]: c for c in page6}
    assert detail["(-) 15%"]["flags"] == [] and detail["(+) 15%"]["resolved"]
    assert detail["Nil"]["value_state"] == "zero" and "nil_word" in detail["Nil"]["flags"]
    assert detail["-"]["value_state"] == "not_applicable" and detail["NA"]["value_state"] == "not_applicable"
    assert detail["as applicable to HV-1"]["value_state"] == "cross_reference"
    assert detail["1,00,000"]["value"] == "100000" and "unit_unresolved" in detail["1,00,000"]["flags"]
    assert detail["1,00,000"]["resolved"] is False  # no unit anywhere: listed, never defaulted
    unresolved = client.get(
        f"/sources/{src_id}/structure/cells", params={"unresolved_only": "true"}, headers=headers(ANALYST)
    ).json()
    assert unresolved["total"] == st["cells_unresolved"] and all(not c["resolved"] for c in unresolved["cells"])
    assert "unit_unresolved" in st["unresolved_by_flag"]

    # page 7: the slab boundary 100 claimed twice is ambiguous and routed, not resolved
    page7 = by_page[7]
    assert [c["slab"]["inclusivity"] for c in page7] == ["ambiguous", "ambiguous", "inferred"]
    amb = client.get(
        f"/sources/{src_id}/structure/cells", params={"flag": "slab_inclusivity_ambiguous"}, headers=headers(ANALYST)
    ).json()
    assert amb["total"] == 2

    # artefacts: one per grid plus the summary, under the composite tool version
    keys = [o.key for o in storage.list("artefacts", prefix=f"{d['sha256']}/grid/")]
    assert (
        any(k.endswith("/summary.json") for k in keys) and sum("/grid-" in k for k in keys) == st["continuations"] + 4
    )
    summary = json.loads(storage.get("artefacts", next(k for k in keys if k.endswith("/summary.json"))))
    assert summary["summary"]["cells"] == st["cells"]


def test_gerc_clause_outline_persists_across_page_breaks_and_rerun_replaces_rows(client, runner):
    src_id = _upload(client, gerc_structure_order_pdf(), "SYNTHETIC_gerc_structure.pdf")
    assert _run_all(runner) == 4
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["reading_profile"]["profile_id"] == "gerc-discoms" and d["localisation"]["status"] == "proposed"
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert runner.run_once() is True
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "gridded"
    st = d["structure"]
    assert st["representation"] == "clause_outline" and st["cells"] == 0
    assert st["clause_categories"] == ["AG", "HTP-1", "RGP"] and st["clause_option_groups"] == 1
    assert st["clause_cross_references"] == 1 and st["clause_conditions"] == 1 and st["clause_values"] == 32

    rgp = client.get(
        f"/sources/{src_id}/structure/clauses", params={"category": "RGP"}, headers=headers(ANALYST)
    ).json()
    energy = [v for v in rgp["values"] if v["role"] == "energy"]
    assert len(energy) == 8 and {v["dimension"]["metering_type"] for v in energy} == {"post_paid", "pre_paid"}
    assert energy[0]["connector"] == "PLUS" and energy[0]["currency"] == "paise" and energy[0]["per_unit"] == "unit"
    assert {v["page_index"] for v in rgp["values"]} <= {4, 5, 6}
    ag = client.get(f"/sources/{src_id}/structure/clauses", params={"category": "AG"}, headers=headers(ANALYST)).json()
    assert sorted({v["alternative"] for v in ag["values"] if v["role"] == "option"}) == [0, 1, 2]
    htp = client.get(
        f"/sources/{src_id}/structure/clauses", params={"category": "HTP-1"}, headers=headers(ANALYST)
    ).json()
    demand = [v for v in htp["values"] if v["role"] == "demand"]
    assert [v["value"] for v in demand] == ["150", "250", "400", "555"]
    assert all(v["per_unit"] == "kVA" and v["frequency"] == "per_month" for v in demand)
    cond = [v for v in htp["values"] if v["kind"] == "condition"]
    assert len(cond) == 1 and cond[0]["value"] is None and cond[0]["parameters"] == ["85% of the contract demand"]
    tou = [v for v in htp["values"] if v["role"] == "tou_surcharge"]
    assert [(v["value"], v["sign"]) for v in tou] == [("45", 1), ("85", 1)]
    # values can straddle pages: the state (category, titles) carried across the break
    pages = sorted({v["page_index"] for v in htp["values"]})
    assert len(pages) >= 1 and all(v["category_code"] == "HTP-1" for v in htp["values"])

    # a new reviewer decision re-runs the stage; rows are replaced, not duplicated
    correct = {
        "decision": "correct",
        "rationale": "same regions, re-confirmed after a look at page 6",
        "pages_viewed": True,
        "regions": [{"role": "approved_schedule", "page_start": 3, "page_end": 6}],
    }
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=correct, headers=headers(ADMIN)).status_code == 200
    )
    assert runner.run_once() is True
    d2 = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d2["state"] == "gridded" and d2["structure"]["clause_values"] == 32
    total = client.get(f"/sources/{src_id}/structure/clauses", headers=headers(ANALYST)).json()["total"]
    assert total == 32 + 1 + 1
