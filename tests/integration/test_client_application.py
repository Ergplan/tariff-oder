"""The client application (ADR-0019): organisations and roles, a client's ARR case from setup
to draft petition (annual and MYT), isolation between organisations, and the regulatory
library (seeded expectations, URLs, acquisition through the worker, coverage levels).
SYNTHETIC fixture data; the acquisition test serves the PDF from a local HTTP server."""

from __future__ import annotations

import shutil
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest
from arr_helpers import read_and_publish, run_all

from conftest import ADMIN, CLIENT_A, CLIENT_A_VIEWER, CLIENT_B, REVIEWER, headers
from fixtures.synthetic_pdfs import text_only_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
LICENSEE = "SYNTH-CLIENT"


def _org(client, code: str, owner: str) -> str:
    r = client.post(
        "/organisations",
        json={"code": code, "name": f"{code} consultants", "owner_email": owner},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _params(client, case_id: str, years: list[str], user: str = CLIENT_A, clause: dict | None = None) -> None:
    def add(**b):
        r = client.post(f"/cases/{case_id}/assumptions", json=b, headers=headers(user))
        assert r.status_code == 201, r.text

    for i, fy in enumerate(years):
        add(key="E.SALES", fiscal_year=fy, value=str(9300 + 300 * i), unit="MU", rationale="load forecast")
        add(key="E.LOSS.DIST_PCT", fiscal_year=fy, value="9.5", unit="percent", rationale="loss trajectory")
    add(key="param.pp_rate_inr_per_kwh", value="5.10", unit="INR_per_kWh", rationale="average PP rate")
    add(key="param.tx_growth_pct", value="4.0", unit="percent", rationale="transmission growth")
    add(key="param.avg_realisation_inr_per_kwh", value="7.20", unit="INR_per_kWh", rationale="realisation")
    add(key="param.iwc_growth_pct", value="6.0", unit="percent", rationale="working capital growth")
    if clause:
        add(
            key="param.om_escalation_pct",
            value="5.00",
            unit="percent",
            source_kind="regulation_clause",
            rationale="Regulation 23(1)",
            clause_ref=clause,
        )
    else:
        add(key="param.om_escalation_pct", value="5.00", unit="percent", rationale="O&M escalation")


def test_organisations_cases_and_isolation(client, runner, object_store_root):
    _order, regulation = read_and_publish(client, runner, LICENSEE)
    org_a, org_b = _org(client, "ACME", CLIENT_A), _org(client, "BETA", CLIENT_B)
    assert (
        client.post(
            "/organisations", json={"code": "X1", "name": "xx", "owner_email": CLIENT_A}, headers=headers(CLIENT_A)
        ).status_code
        == 403
    )
    r = client.post(
        f"/organisations/{org_a}/members", json={"email": CLIENT_A_VIEWER, "role": "viewer"}, headers=headers(CLIENT_A)
    )
    assert r.status_code == 200 and {m["email"] for m in r.json()["members"]} == {CLIENT_A, CLIENT_A_VIEWER}
    assert (
        client.post(
            f"/organisations/{org_a}/members", json={"email": "x@example.com"}, headers=headers(CLIENT_B)
        ).status_code
        == 404
    )
    r = client.delete(f"/organisations/{org_a}/members/{CLIENT_A}", headers=headers(CLIENT_A))
    assert r.status_code == 422  # the last owner stays
    assert [o["id"] for o in client.get("/me", headers=headers(CLIENT_B)).json()["organisations"]] == [org_b]
    me = client.get("/me", headers=headers(CLIENT_A)).json()
    assert [(o["code"], o["role"]) for o in me["organisations"]] == [("ACME", "owner")]

    # ---- a case: readiness says what is missing before anything is computed
    body = {
        "organisation_id": org_a,
        "utility_code": LICENSEE,
        "title": "FY2026-27 ARR petition",
        "filing_kind": "annual_arr",
        "base_fy": "FY2025-26",
        "target_years": ["FY2026-27"],
    }
    assert (
        client.post(
            "/cases", json={**body, "target_years": ["FY2026-27", "FY2027-28"]}, headers=headers(CLIENT_A)
        ).status_code
        == 422
    )
    assert (
        client.post("/cases", json={**body, "target_years": ["FY2027-28"]}, headers=headers(CLIENT_A)).status_code
        == 422
    )
    assert client.post("/cases", json=body, headers=headers(CLIENT_A_VIEWER)).status_code == 403
    assert client.post("/cases", json=body, headers=headers(CLIENT_B)).status_code == 404
    r = client.post("/cases", json=body, headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    case = r.json()
    rd = case["readiness"]
    assert case["status"] == "setup" and rd["missing_base_facts"] == [] and not rd["ready_to_formulate"]
    assert {"E.SALES", "param.om_escalation_pct", "param.iwc_growth_pct"} <= set(rd["missing_parameters"])
    om = next(b for b in rd["base_facts"] if b["line_code"] == "C.OM")
    assert om["present"] and om["value"] == "600.00" and om["value_type"] == "approved"

    clause = {
        "source_id": regulation,
        "page_index": 2,
        "citation": "Regulation 23(1)",
        "excerpt": "shall be escalated at the rate of 5.00 per cent per annum",
    }
    _params(client, case["id"], ["FY2026-27"], clause=clause)
    r = client.get(f"/cases/{case['id']}", headers=headers(CLIENT_A_VIEWER))  # the viewer reads
    assert r.status_code == 200 and r.json()["readiness"]["ready_to_formulate"] and r.json()["status"] == "assumptions"
    bad = {"key": "param.x", "value": "1", "unit": "percent", "rationale": "x"}
    assert (
        client.post(f"/cases/{case['id']}/assumptions", json=bad, headers=headers(CLIENT_A_VIEWER)).status_code == 403
    )

    # ---- formulate, freeze, draft; another organisation sees none of it
    r = client.post(f"/cases/{case['id']}/formulate", headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    f = r.json()
    lines = {ln["line_code"]: ln["value"] for ln in f["lines"]}
    assert f["organisation_id"] == org_a and f["summary"]["blocked"] == 0 and lines["R.ARR"] == "6889.88"
    assert client.post(f"/cases/{case['id']}/draft", headers=headers(CLIENT_A)).status_code == 409
    assert client.post(f"/cases/{case['id']}/freeze", headers=headers(CLIENT_A)).status_code == 200
    r = client.post(f"/cases/{case['id']}/draft", headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    draft = r.json()
    case = client.get(f"/cases/{case['id']}", headers=headers(CLIENT_A)).json()
    assert case["status"] == "drafted" and case["draft_id"] == draft["id"]
    for path in (
        f"/cases/{case['id']}",
        f"/arr/formulations/{f['id']}",
        f"/arr/drafts/{draft['id']}",
        f"/arr/drafts/{draft['id']}/petition.docx",
        f"/arr/assumption-sets/{case['assumption_set_id']}",
    ):
        assert client.get(path, headers=headers(CLIENT_B)).status_code == 404, path
        assert client.get(path, headers=headers(CLIENT_A_VIEWER)).status_code == 200, path
    assert client.get("/cases", headers=headers(CLIENT_B)).json() == []
    assert [c["id"] for c in client.get("/cases", headers=headers(CLIENT_A)).json()] == [case["id"]]
    listed = client.get(f"/arr/utilities/{LICENSEE}/formulations", headers=headers(CLIENT_B)).json()
    assert f["id"] not in {x["id"] for x in listed}
    assert client.get(f"/cases/{case['id']}", headers=headers(ADMIN)).status_code == 200  # support reads
    assert client.post(f"/cases/{case['id']}/formulate", headers=headers(ADMIN)).status_code == 403  # but not change
    # the shared corpus stays readable by every client
    assert client.get(f"/arr/utilities/{LICENSEE}/history", headers=headers(CLIENT_B)).status_code == 200

    # ---- revise: a new assumption-set version copied from the frozen one
    r = client.post(f"/cases/{case['id']}/revise", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    revised = r.json()
    assert revised["status"] == "assumptions" and revised["assumption_set_id"] != case["assumption_set_id"]
    assert revised["readiness"]["ready_to_formulate"]  # the assumptions came along
    aset = client.get(f"/arr/assumption-sets/{revised['assumption_set_id']}", headers=headers(CLIENT_A)).json()
    sales = next(a for a in aset["assumptions"] if a["key"] == "E.SALES")
    r = client.delete(f"/cases/{case['id']}/assumptions/{sales['id']}", headers=headers(CLIENT_A))
    assert r.status_code == 204
    assert (
        "E.SALES"
        in client.get(f"/cases/{case['id']}", headers=headers(CLIENT_A)).json()["readiness"]["missing_parameters"]
    )

    # ---- an MYT case: every year of the control period
    myt = {
        **body,
        "title": "MYT FY2026-27 to FY2028-29",
        "filing_kind": "myt",
        "target_years": ["FY2026-27", "FY2027-28", "FY2028-29"],
    }
    r = client.post("/cases", json=myt, headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    mcase = r.json()
    assert {t["value_type"] for t in mcase["targets"]} == {"control_period"}
    _params(client, mcase["id"], ["FY2026-27", "FY2027-28", "FY2028-29"])
    r = client.post(f"/cases/{mcase['id']}/formulate", headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    om = {ln["fiscal_year"]: ln["value"] for ln in r.json()["lines"] if ln["line_code"] == "C.OM"}
    assert om == {"FY2026-27": "630.00", "FY2027-28": "661.50", "FY2028-29": "694.58"}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: ANN002
        pass


def test_library_seed_locate_acquire_and_coverage(client, runner, object_store_root, app, tmp_path):
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        seed_registry(s)
    years = ["FY2024-25", "FY2025-26", "FY2026-27"]
    assert client.post("/library/seed", json={"fiscal_years": years}, headers=headers(REVIEWER)).status_code == 403
    r = client.post(
        "/library/seed", json={"fiscal_years": years, "commission_codes": ["UPERC"]}, headers=headers(ADMIN)
    )
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["created"] > 0
    again = client.post(
        "/library/seed", json={"fiscal_years": years, "commission_codes": ["UPERC"]}, headers=headers(ADMIN)
    ).json()
    assert again["created"] == 0 and again["existing"] == first["created"] + first["existing"]
    npcl = client.get("/library/entries?utility=NPCL", headers=headers(CLIENT_B)).json()
    kinds = {(e["document_kind"], e["fiscal_year"]) for e in npcl}
    assert {
        ("tariff_order", "FY2026-27"),
        ("arr_petition", "FY2025-26"),
        ("myt_order", ""),
        ("myt_petition", ""),
    } <= kinds
    assert all(e["reading"] == "missing" and e["url"] is None for e in npcl)

    # an official URL, then acquisition through the worker (a local server stands in)
    (tmp_path / "order.pdf").write_bytes(text_only_pdf(seed="library-npcl-order"))
    server = HTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/order.pdf"
        entry = {
            "commission_code": "UPERC",
            "utility_code": "NPCL",
            "document_kind": "tariff_order",
            "fiscal_year": "FY2026-27",
            "title": "NPCL tariff order FY2026-27",
            "url": url,
        }
        r = client.put("/library/entries", json=entry, headers=headers(ADMIN))
        assert r.status_code == 200 and r.json()["status"] == "located" and r.json()["reading"] == "located"
        eid = r.json()["id"]
        r = client.put("/library/entries", json={**entry, "utility_code": "KESCO-NOT-REAL"}, headers=headers(ADMIN))
        assert r.status_code == 422
        bad = {**entry, "fiscal_year": "FY2025-26", "url": f"http://127.0.0.1:{server.server_port}/missing.pdf"}
        bad_id = client.put("/library/entries", json=bad, headers=headers(ADMIN)).json()["id"]
        assert client.post(f"/library/entries/{eid}/acquire", headers=headers(ADMIN)).status_code == 202
        assert client.post(f"/library/entries/{bad_id}/acquire", headers=headers(ADMIN)).status_code == 202
        runner.run_once()
        runner.run_once()
    finally:
        server.shutdown()
    got = {
        e["id"]: e for e in client.get("/library/entries?utility=NPCL&kind=tariff_order", headers=headers(ADMIN)).json()
    }
    assert got[eid]["status"] == "acquired" and got[eid]["source_id"] and got[eid]["reading"] == "acquired"
    assert got[bad_id]["status"] == "failed" and "404" in got[bad_id]["last_error"] and got[bad_id]["attempts"] == 1
    src = client.get(f"/sources/{got[eid]['source_id']}", headers=headers(ADMIN)).json()
    assert src["provenance_url"].endswith("/order.pdf") and src["dataset_kind"] == "real"
    assert client.post(f"/library/entries/{eid}/acquire", headers=headers(ADMIN)).status_code == 409
    run_all(runner)  # the acquired order is inventoried like any upload
    # a combined order listed for another licensee: linked to the copy already acquired, not
    # fetched again (the server is down by now)
    twin = client.put("/library/entries", json={**entry, "utility_code": "KESCO"}, headers=headers(ADMIN)).json()["id"]
    assert client.post(f"/library/entries/{twin}/acquire", headers=headers(ADMIN)).status_code == 202
    run_all(runner)
    t = next(e for e in client.get("/library/entries?utility=KESCO", headers=headers(ADMIN)).json() if e["id"] == twin)
    assert t["status"] == "acquired" and t["source_id"] == got[eid]["source_id"] and t["attempts"] == 0
    # and the order is recorded as a combined order for both licensees
    lic = client.get(f"/sources/{t['source_id']}/licensees", headers=headers(ADMIN)).json()
    assert [(x["code"], x["primary"]) for x in lic] == [("NPCL", True), ("KESCO", False)]

    # discovery profiles: listed for analysts; a commission without one is told so (no fetch)
    assert "UPERC" in client.get("/library/discovery-profiles", headers=headers(CLIENT_A)).json()
    r = client.post(
        "/library/discover/profile",
        json={"commission_code": "KERC", "fiscal_years": ["FY2025-26"]},
        headers=headers(ADMIN),
    )
    assert r.status_code == 422 and "no discovery profile" in r.json()["detail"]
    assert (
        client.post(
            "/library/discover/profile",
            json={"commission_code": "UPERC", "fiscal_years": ["FY2025-26"]},
            headers=headers(CLIENT_A),
        ).status_code
        == 403
    )

    cov = client.get("/library/coverage", headers=headers(CLIENT_A)).json()
    assert set(years) <= set(cov["fiscal_years"]) and cov["totals"]["acquired"] >= 1 and cov["totals"]["failed"] >= 1
    up = next(st for st in cov["states"] for c in st["commissions"] if c["code"] == "UPERC")
    uperc = next(c for c in up["commissions"] if c["code"] == "UPERC")
    npcl_row = next(u for u in uperc["licensees"] if u["code"] == "NPCL")
    assert npcl_row["cells"]["tariff_order|FY2026-27"]["level"] == "acquired"
    assert npcl_row["cells"]["tariff_order|FY2025-26"]["level"] == "failed"
    assert uperc["commission_wide"]["regulation|"]["level"] == "missing"
