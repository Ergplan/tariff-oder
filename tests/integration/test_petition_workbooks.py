"""The petition fill in the client case flow (increment 151): a UPERC / NPCL case gets the layout of
NPCL's filed FY2026-27 formats workbook, downloads the inputs template, uploads it, asks for the
fill, and the worker fills it — the filled workbook (draft header, Fill trace sheet) and the
report stored with the case.  The template is the filing with the fill map blanked, so the fill
reproduces the filing's figures; that is the test, not a claim about any new petition.  Access:
a viewer reads but cannot upload or fill; another organisation sees nothing; a licensee the
engine cannot fill says so."""

from __future__ import annotations

import io

import openpyxl
import pytest

from conftest import ADMIN, CLIENT_A, CLIENT_A_VIEWER, CLIENT_B, headers

pytestmark = pytest.mark.integration


def _org(client, code: str, owner: str) -> str:
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        seed_registry(s)
    r = client.post(
        "/organisations",
        json={"code": code, "name": f"{code} consultants", "owner_email": owner},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _case(client, org: str, utility: str, years: list[str]) -> dict:
    r = client.post(
        "/cases",
        json={
            "organisation_id": org,
            "utility_code": utility,
            "title": f"{utility} petition",
            "filing_kind": "annual_arr",
            "base_fy": years[0],
            "target_years": years[1:],
        },
        headers=headers(CLIENT_A),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _xlsx(name: str, data: bytes):
    return {"file": (name, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_npcl_case_fills_its_formats_workbook(client, runner):
    org = _org(client, "PETFILL", CLIENT_A)
    r = client.post(
        f"/organisations/{org}/members", json={"email": CLIENT_A_VIEWER, "role": "viewer"}, headers=headers(CLIENT_A)
    )
    assert r.status_code in (200, 201), r.text
    case = _case(client, org, "NPCL", ["FY2025-26", "FY2026-27"])
    base = f"/cases/{case['id']}/petition"

    lay = client.get(f"{base}/layout", headers=headers(CLIENT_A)).json()
    assert lay["available"] and lay["package"] == "uperc-npcl-fy2026-27"
    assert lay["years"]["arr"] == "FY2026-27" and lay["warnings"] == []
    assert lay["cells_filled"] == lay["cells_computed"] + lay["cells_carried"] > 4000

    # another organisation does not see the case; a viewer reads but does not change it
    assert client.get(f"{base}/layout", headers=headers(CLIENT_B)).status_code == 404
    r = client.get(f"{base}/template", headers=headers(CLIENT_A_VIEWER))
    assert r.status_code == 200
    template = r.content
    tw = openpyxl.load_workbook(io.BytesIO(template), data_only=True)
    assert "About this template" in tw.sheetnames
    assert (
        client.post(f"{base}/workbooks", files=_xlsx("in.xlsx", template), headers=headers(CLIENT_A_VIEWER)).status_code
        == 403
    )

    # not a workbook; a workbook without the formats
    bad = client.post(
        f"{base}/workbooks", files=_xlsx("in.xlsx", b"%PDF-1.4 not a workbook"), headers=headers(CLIENT_A)
    )
    assert bad.status_code == 422 and bad.json()["error_type"] == "validation_failed"
    empty = openpyxl.Workbook()
    buf = io.BytesIO()
    empty.save(buf)
    bad = client.post(f"{base}/workbooks", files=_xlsx("in.xlsx", buf.getvalue()), headers=headers(CLIENT_A))
    assert bad.status_code == 422 and "sheet(s) the fill writes are missing" in bad.json()["detail"]

    r = client.post(f"{base}/workbooks", files=_xlsx("npcl-inputs.xlsx", template), headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    inputs = r.json()
    assert inputs["role"] == "inputs" and inputs["status"] == "stored"
    s = inputs["summary"]["inputs"]
    assert s["inputs_blank"] == 0 and s["inputs_changed"] == 0 and s["inputs_as_filed"] == s["input_cells"] > 0
    assert s["fill_cells_entered"] == 0

    assert client.post(f"{base}/workbooks/{inputs['id']}/fill", headers=headers(CLIENT_A_VIEWER)).status_code == 403
    r = client.post(f"{base}/workbooks/{inputs['id']}/fill", headers=headers(CLIENT_A))
    assert r.status_code == 202, r.text
    filled = r.json()
    assert filled["role"] == "filled" and filled["status"] == "queued" and filled["inputs_id"] == inputs["id"]
    # the report is not there before the fill runs
    assert client.get(f"{base}/workbooks/{filled['id']}/report", headers=headers(CLIENT_A)).status_code == 404

    while runner.run_once():
        pass

    w = client.get(f"{base}/workbooks/{filled['id']}", headers=headers(CLIENT_A)).json()
    assert w["status"] == "filled", w
    summ = w["summary"]
    assert summ["computed"] + summ["carried"] == lay["cells_filled"]
    # every map cell written; the outputs the engine could not compute are all cells the filed
    # format leaves blank (rates on empty tariff rows), counted apart from the blocked
    assert summ["conflicts"] == 0 and summ["blocked"] == 0 and summ["not_printed"] > 0
    assert "not a filing" in summ["status"]

    rep = client.get(f"{base}/workbooks/{filled['id']}/report", headers=headers(CLIENT_A_VIEWER)).json()
    assert len(rep["written"]) == lay["cells_filled"] and rep["package"] == "uperc-npcl-fy2026-27"

    r = client.get(f"{base}/workbooks/{filled['id']}/download", headers=headers(CLIENT_A))
    assert r.status_code == 200
    fw = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Fill trace" in fw.sheetnames
    assert "WORKING DRAFT" in fw["ARR"].oddHeader.center.text
    # the fill writes the filing's figures back from its inputs (the template is the filing, blanked)
    filed = openpyxl.load_workbook(io.BytesIO(template), data_only=True)
    cell = rep["written"][0]["cell"]
    sheet, _, ref = cell.rpartition("!")
    assert filed[sheet][ref].value is None and fw[sheet][ref].value is not None

    listed = client.get(f"{base}/workbooks", headers=headers(CLIENT_A)).json()
    assert [x["role"] for x in listed] == ["inputs", "filled"]
    assert client.get(f"{base}/workbooks", headers=headers(CLIENT_B)).status_code == 404
    acts = {a["action"] for a in client.get(f"/cases/{case['id']}/activity", headers=headers(CLIENT_A)).json()}
    assert {"arr_case.petition_inputs_uploaded", "arr_case.petition_fill_requested"} <= acts


def test_layout_names_the_year_mismatch_and_licensees_without_one(client):
    org = _org(client, "PETLAY", CLIENT_A)
    case = _case(client, org, "NPCL", ["FY2027-28", "FY2028-29"])
    lay = client.get(f"/cases/{case['id']}/petition/layout", headers=headers(CLIENT_A)).json()
    assert lay["available"] and len(lay["warnings"]) == 1 and "FY2026-27" in lay["warnings"][0]

    other = _case(client, org, "PVVNL", ["FY2025-26", "FY2026-27"])
    lay = client.get(f"/cases/{other['id']}/petition/layout", headers=headers(CLIENT_A)).json()
    assert not lay["available"] and "PVVNL" in lay["why"]
    r = client.get(f"/cases/{other['id']}/petition/template", headers=headers(CLIENT_A))
    assert r.status_code == 404
