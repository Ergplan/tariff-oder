"""Increment A gate (docs/prompts/arr-build-prompt.md, ADR-0018): a SYNTHETIC ARR order goes
the whole way — chapters proposed and confirmed by a reviewer, two-channel candidates, the
deliberate identity break flagged, human decisions (the test harness's reviewers, on fixture
data only), publication into ARR facts, the history view, an assumption set with a
regulation parameter grounded on its clause, a formulation blocked for a missing parameter,
a complete one frozen and reproduced bit for bit, and a filing draft whose every number is
in the trace annex; an untraced number refuses generation; a draft can never be "filed"."""

from __future__ import annotations

import io
import json
import shutil

import pytest
from sqlalchemy import select, text

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import ARR_COSTS, ARR_ENERGY, ARR_GAP, arr_order_pdf, arr_regulation_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
COMMISSION, UTILITY = "SYNTHERC", "SYNTH-DISCOM"


def _run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def _registry() -> None:
    """The SYNTHETIC commission and licensee (fixture dataset), created once per database."""
    from tariff_api.db import session_scope
    from tariff_api.models import Commission, DatasetKind, Jurisdiction, JurisdictionKind, Utility
    from tariff_api.services.sources import get_or_create_dataset

    with session_scope() as s:
        if s.execute(select(Utility).where(Utility.code == UTILITY)).scalar_one_or_none():
            return
        j = s.execute(select(Jurisdiction).where(Jurisdiction.code == "SYN")).scalar_one_or_none()
        if j is None:
            j = Jurisdiction(code="SYN", name="SYNTHETIC jurisdiction", kind=JurisdictionKind.state)
            s.add(j)
            s.flush()
        c = Commission(code=COMMISSION, name="SYNTHETIC Electricity Regulatory Commission", jurisdiction_id=j.id)
        s.add(c)
        s.flush()
        s.add(
            Utility(
                code=UTILITY,
                name="SYNTHETIC distribution licensee",
                commission_id=c.id,
                dataset_id=get_or_create_dataset(s, DatasetKind.fixture).id,
                licensee_kind="distribution",
            )
        )


def _upload(client, data: bytes, name: str, **form: str) -> str:
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture", **form},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["source"]["id"]


def _decide(client, cand: dict, outcome: str, user: str, rationale: str | None = None) -> dict:
    r = client.get(f"/candidates/{cand['id']}/evidence/0/image", headers=headers(user))
    assert r.status_code == 200, r.text
    body = {
        "outcome": outcome,
        "expected_version": cand["version"],
        "evidence_view_ids": [r.headers["x-evidence-view-id"]],
    }
    if rationale:
        body["rationale"] = rationale
    r = client.post(f"/candidates/{cand['id']}/decision", json=body, headers=headers(user))
    assert r.status_code == 200, r.text
    return client.get(f"/candidates/{cand['id']}", headers=headers(user)).json()


def _add(client, set_id: str, **body) -> dict:
    r = client.post(f"/arr/assumption-sets/{set_id}/assumptions", json=body, headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    return r.json()


def test_arr_read_formulate_file_end_to_end(client, runner, object_store_root, monkeypatch, tmp_path):
    _registry()
    order = _upload(client, arr_order_pdf(), "SYNTHETIC_arr_order.pdf", utility_code=UTILITY, order_type="tariff_order")
    regulation = _upload(client, arr_regulation_pdf(), "SYNTHETIC_arr_regulation.pdf", order_type="regulation")
    _run_all(runner)

    # ---- read: chapters proposed from the mapping's cues, then the reviewer's checkpoint
    assert client.post(f"/sources/{order}/arr/read", headers=headers(REVIEWER)).status_code == 403
    r = client.post(f"/sources/{order}/arr/read", headers=headers(ADMIN))
    assert r.status_code == 202, r.text
    _run_all(runner)
    reading = client.get(f"/sources/{order}/arr", headers=headers(ANALYST)).json()
    assert reading["arr_state"] == "chapters_proposed"
    assert [(c["branch"], c["cue_page"]) for c in reading["chapters"]] == [("E", 2), ("C", 3), ("R", 4)]
    assert reading["mapping_confirmed"] is True  # the SYNTHETIC mapping is confirmed
    # the page-5 sentence that reads like an instruction opened no chapter: document text is data
    assert all("IGNORE" not in c["cue_text"] for c in reading["chapters"])
    r = client.post(f"/sources/{order}/arr/chapters/decision", json={"rationale": "  "}, headers=headers(REVIEWER))
    assert r.status_code == 422
    r = client.post(
        f"/sources/{order}/arr/chapters/decision",
        json={"rationale": "Three ARR chapters located; tables checked against the pages"},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    _run_all(runner)

    # ---- candidates: every placed row x every year/voice column, both channels agreeing
    reading = client.get(f"/sources/{order}/arr", headers=headers(ANALYST)).json()
    assert reading["arr_state"] == "awaiting_review"
    rows = len(ARR_ENERGY) + len(ARR_COSTS) + len(ARR_GAP)
    cands = client.get(f"/sources/{order}/arr/candidates", headers=headers(ANALYST)).json()["candidates"]
    assert len(cands) == rows * 3, [c["candidate_key"] for c in cands]
    assert all(c["payload_kind"] == "arr" and c["is_fixture"] and c["channel_agreement"] == "agree" for c in cands)
    by = {(c["record"]["line_code"], c["record"]["fiscal_year"], c["record"]["value_type"]): c for c in cands}
    loan = by[("C.INT.LOAN", "FY2025-26", "approved")]["record"]
    assert loan["stated_value"] == "150.00" and loan["stated_unit"] == "INR_crore"  # the mapping's alias placed it
    loss = by[("E.LOSS.DIST_PCT", "FY2024-25", "final_true_up")]["record"]
    assert loss["stated_unit"] == "percent" and loss["evidence"][0]["kind"] == "cell"
    assert by[("E.SALES", "FY2025-26", "petitioned")]["record"]["canonical_value"] == "9100.00"
    # tariff paths never see ARR candidates
    assert client.get(f"/sources/{order}/candidates", headers=headers(ANALYST)).json()["total"] == 0

    # ---- the deliberate break: the petition's total does not add up
    blocking = [f for f in reading["findings"] if f["severity"] == "blocking"]
    assert [(f["validator_id"], f["detail"]["group"]["value_type"]) for f in blocking] == [("ARR-I1", "petitioned")]
    bad_total = by[("C.TOTAL", "FY2025-26", "petitioned")]
    assert str(bad_total["id"]) in blocking[0]["candidate_ids"] and "identity_failure" in bad_total["risk_tags"]
    r = client.post(f"/sources/{order}/arr/publish", headers=headers(REVIEWER))
    assert r.status_code == 422 and "blocking identity" in r.text

    # ---- human decisions (harness reviewers, fixture data): the first ARR order of a
    # licensee needs a second reviewer; the bad total is rejected with a rationale
    for c in cands:
        if c["id"] == bad_total["id"]:
            _decide(client, c, "reject", REVIEWER, "Printed total does not equal its components; components verified")
            continue
        c = _decide(client, c, "approve", REVIEWER)
        assert c["review_status"] == "awaiting_second_review"
        c = _decide(client, c, "approve", ADMIN)
        assert c["review_status"] == "approved"
    _run_all(runner)  # the rejection re-runs the identities
    reading = client.get(f"/sources/{order}/arr", headers=headers(ANALYST)).json()
    assert not [f for f in reading["findings"] if f["severity"] == "blocking"]
    r = client.post(f"/sources/{order}/arr/publish", headers=headers(REVIEWER))
    assert r.status_code == 200, r.text
    assert r.json()["published"] == rows * 3 - 1 and r.json()["pending"] == 0
    # a published candidate's decision is frozen
    any_id = by[("R.ARR", "FY2025-26", "approved")]["id"]
    decisions = client.get(f"/candidates/{any_id}/decisions", headers=headers(REVIEWER)).json()
    last = decisions[-1] if isinstance(decisions, list) else decisions["decisions"][-1]
    assert client.post(f"/review/decisions/{last['id']}/undo", headers=headers(ADMIN)).status_code == 409

    # ---- history: facts by line, year and voice; disallowance computed, never stored
    h = client.get(f"/arr/utilities/{UTILITY}/history", headers=headers(ANALYST)).json()
    assert h["kind"] == "fact" and h["is_fixture"] and h["years"] == ["FY2024-25", "FY2025-26"]
    om = next(line for line in h["lines"] if line["line_code"] == "C.OM")
    cell = next(c for c in om["cells"] if c["fiscal_year"] == "FY2025-26")
    assert {f["value_type"] for f in cell["facts"]} == {"petitioned", "approved"}
    assert cell["disallowance"][0]["value"] == "40.00"

    # ---- assumptions: user entries need a rationale; a regulation parameter is grounded
    r = client.post(f"/arr/utilities/{UTILITY}/assumption-sets", json={"name": "Base case"}, headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    aset = r.json()["id"]
    _add(
        client,
        aset,
        key="E.SALES",
        fiscal_year="FY2026-27",
        value="9300",
        unit="MU",
        rationale="Load forecast (synthetic)",
    )
    _add(
        client,
        aset,
        key="E.LOSS.DIST_PCT",
        fiscal_year="FY2026-27",
        value="9.5",
        unit="percent",
        rationale="Loss trajectory",
    )
    _add(client, aset, key="param.pp_rate_inr_per_kwh", value="5.10", unit="INR_per_kWh", rationale="Average PP rate")
    _add(client, aset, key="param.tx_growth_pct", value="4.0", unit="percent", rationale="Transmission tariff growth")
    _add(
        client, aset, key="param.avg_realisation_inr_per_kwh", value="7.20", unit="INR_per_kWh", rationale="Realisation"
    )
    clause = {
        "source_id": regulation,
        "page_index": 2,
        "citation": "Regulation 23(1)",
        "excerpt": "shall be escalated at the rate of 5.00 per cent per annum",
    }
    for bad, why in (
        ({**clause, "excerpt": "shall be escalated at the rate of 6.00 per cent"}, "not on page"),
        ({**clause, "source_id": order}, "registered regulation"),
    ):
        r = client.post(
            f"/arr/assumption-sets/{aset}/assumptions",
            json={
                "key": "param.om_escalation_pct",
                "value": "5.00",
                "unit": "percent",
                "source_kind": "regulation_clause",
                "rationale": "Regulation 23",
                "clause_ref": bad,
            },
            headers=headers(REVIEWER),
        )
        assert r.status_code == 422 and why in r.text, r.text
    r = client.post(
        f"/arr/assumption-sets/{aset}/assumptions",
        json={
            "key": "param.om_escalation_pct",
            "value": "6.00",
            "unit": "percent",
            "source_kind": "regulation_clause",
            "rationale": "Regulation 23",
            "clause_ref": clause,
        },
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "not printed in the cited excerpt" in r.text
    om_param = _add(
        client,
        aset,
        key="param.om_escalation_pct",
        value="5.00",
        unit="percent",
        source_kind="regulation_clause",
        rationale="Regulation 23(1) of the regulations on file",
        clause_ref=clause,
    )
    assert om_param["clause_ref"]["confirmed_by"] == REVIEWER

    # ---- formulation 1: a parameter is missing, so its line and everything after it block
    body = {
        "name": "FY2026-27 petition",
        "base_fy": "FY2025-26",
        "targets": [{"fiscal_year": "FY2026-27"}],
        "assumption_set_id": aset,
    }
    r = client.post(f"/arr/utilities/{UTILITY}/formulations", json=body, headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    f1 = r.json()
    blocked = {ln["line_code"]: ln["blocked_reason"] for ln in f1["lines"] if ln["status"] == "blocked"}
    assert blocked["C.INT.WC"] == "parameter missing: param.iwc_growth_pct for FY2026-27"
    assert set(blocked) == {"C.INT.WC", "C.TOTAL", "R.ARR", "R.GAP", "R.ACOS"}
    assert all(ln["kind"] == "projection" for ln in f1["lines"])
    r = client.post(f"/arr/formulations/{f1['id']}/freeze", headers=headers(REVIEWER))
    assert r.status_code == 422 and "arr_parameter_missing" in r.text

    # ---- formulation 2: the parameter supplied; computed from the approved FY2025-26 base
    _add(client, aset, key="param.iwc_growth_pct", value="6.0", unit="percent", rationale="Working capital growth")
    r = client.post(f"/arr/utilities/{UTILITY}/formulations", json=body, headers=headers(REVIEWER))
    f2 = r.json()
    lines = {ln["line_code"]: ln for ln in f2["lines"]}
    assert f2["summary"]["blocked"] == 0 and f2["summary"]["identity_findings"] == []
    assert lines["E.INPUT.DIST"]["value"] == "10276.24"
    assert lines["C.OM"]["value"] == "630.00" and lines["C.OM"]["regulation_clause"]["citation"] == "Regulation 23(1)"
    assert lines["C.PP"]["value"] == "5240.88"
    assert lines["C.TOTAL"]["value"] == "6989.88"
    assert lines["R.ARR"]["value"] == "6889.88" and lines["R.GAP"]["value"] == "193.88"
    assert lines["R.ACOS"]["value"] == "7.41"
    om_inputs = lines["C.OM"]["inputs"]
    assert om_inputs["facts"][0]["value_type"] == "approved" and om_inputs["facts"][0]["value"] == "600.00"
    r = client.post(f"/arr/formulations/{f2['id']}/drafts", headers=headers(REVIEWER))
    assert r.status_code == 409  # a draft is drafted from a frozen formulation only
    r = client.post(f"/arr/formulations/{f2['id']}/freeze", headers=headers(REVIEWER))
    assert r.status_code == 200 and r.json()["status"] == "frozen"
    r = client.post(
        f"/arr/assumption-sets/{aset}/assumptions",
        json={"key": "param.extra", "value": "1", "unit": "percent", "rationale": "late"},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 409  # the set froze with the formulation
    rep = client.post(f"/arr/formulations/{f2['id']}/reproduce", headers=headers(ANALYST)).json()
    assert rep["identical"] is True and rep["recomputed_hash"] == f2["input_hash"], rep

    # ---- the filing draft: watermarked, every number traced
    r = client.post(f"/arr/formulations/{f2['id']}/drafts", headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "draft" and draft["is_fixture"] and draft["template_status"] == "synthetic"
    by_kind = draft["trace"]["by_kind"]
    assert by_kind["fact"] > 0 and by_kind["assumption"] > 0 and by_kind["projection"] > 0
    xlsx = client.get(f"/arr/drafts/{draft['id']}/formats.xlsx", headers=headers(ANALYST))
    docx_r = client.get(f"/arr/drafts/{draft['id']}/petition.docx", headers=headers(ANALYST))
    assert xlsx.status_code == 200 and docx_r.status_code == 200
    from docx import Document
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(xlsx.content))
    traced = {e["id"] for e in draft["trace"]["entries"]}
    numbers = 0
    for name in ("F-1", "F-2"):
        ws = wb[name]
        assert ws["A1"].value.startswith("DRAFT")
        for row in ws.iter_rows(min_row=5):
            for c in row:
                if isinstance(c.value, int | float):
                    numbers += 1
                    assert c.comment is not None and c.comment.text.split()[-1] in traced, (name, c.coordinate)
    assert numbers > 0
    f1_rows = {r[0].value: [c.value for c in r] for r in wb["F-1"].iter_rows(min_row=5)}
    assert f1_rows["C.OM"][2:] == [560.0, 600.0, 630.0]  # true-up, approved, projection
    doc = Document(io.BytesIO(docx_r.content))
    body_text = "\n".join(p.text for p in doc.paragraphs)
    assert "DRAFT — prepared with software assistance; not filed" in doc.sections[0].header.paragraphs[0].text
    assert "FIXTURE" in body_text and "6,889.88 Rs crore" in body_text and "Regulation 23(1)" in body_text

    # ---- an untraced number refuses generation
    from tariff_api.arr import filing

    bad = json.loads((filing.templates_dir() / "syntherc" / "petition.v1.json").read_text())
    bad["narrative"][0]["paragraphs"].append("The licensee also claims Rs 125 crore of other expenses.")
    (tmp_path / "syntherc").mkdir()
    (tmp_path / "syntherc" / "petition.v1.json").write_text(json.dumps(bad))
    monkeypatch.setenv("FILING_TEMPLATES_DIR", str(tmp_path))
    filing.load_template.cache_clear()
    try:
        r = client.post(f"/arr/formulations/{f2['id']}/drafts", headers=headers(REVIEWER))
        assert r.status_code == 422 and "filing_untraced_number" in r.text, r.text
    finally:
        monkeypatch.delenv("FILING_TEMPLATES_DIR")
        filing.load_template.cache_clear()

    # ---- the schema has no "filed" state
    from tariff_api.db import session_scope

    with pytest.raises(Exception, match="ck_filing_draft_only_draft"), session_scope() as s:
        s.execute(text("update filing_drafts set status = 'filed' where id = :i"), {"i": draft["id"]})
