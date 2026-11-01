"""True-up and APR cases (ADR-0020): a client enters the licensee's actuals of a year, each
with its source; the application sets them against the reviewed approval of that year,
checks the identities over the actuals, freezes the statement and drafts the petition with
every number traced.  SYNTHETIC fixture data only."""

from __future__ import annotations

import io
import shutil

import pytest
from arr_helpers import read_and_publish, upload

from conftest import ADMIN, CLIENT_A, CLIENT_A_VIEWER, CLIENT_B, headers
from fixtures.synthetic_pdfs import accounts_extract_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
LICENSEE = "SYNTH-TRUEUP"
FY = "FY2025-26"
# actuals that differ from the approval and still close every identity: O&M 612.50 (from
# the accounts, in lakh), so the total, the ARR and the gap move by 12.50
CHANGED = {"C.TOTAL": "6712.50", "R.ARR": "6612.50", "R.GAP": "212.50"}


def _org(client, code: str, owner: str) -> str:
    r = client.post(
        "/organisations",
        json={"code": code, "name": f"{code} consultants", "owner_email": owner},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _case(client, org: str, kind: str = "true_up", user: str = CLIENT_A) -> dict:
    return client.post(
        "/cases",
        json={
            "organisation_id": org,
            "utility_code": LICENSEE,
            "title": f"{kind} {FY}",
            "filing_kind": kind,
            "base_fy": FY,
            "target_years": [FY],
        },
        headers=headers(user),
    )


def test_true_up_case_from_actuals_to_draft(client, runner, object_store_root):
    read_and_publish(client, runner, LICENSEE)
    accounts = upload(client, accounts_extract_pdf(LICENSEE), "SYNTHETIC_accounts_FY2025-26.pdf", order_type="other")
    org_a, _org_b = _org(client, "TUA", CLIENT_A), _org(client, "TUB", CLIENT_B)
    client.post(
        f"/organisations/{org_a}/members", json={"email": CLIENT_A_VIEWER, "role": "viewer"}, headers=headers(CLIENT_A)
    )

    # the year trued up is the only target
    bad = client.post(
        "/cases",
        json={
            "organisation_id": org_a,
            "utility_code": LICENSEE,
            "title": "x",
            "filing_kind": "true_up",
            "base_fy": FY,
            "target_years": ["FY2026-27"],
        },
        headers=headers(CLIENT_A),
    )
    assert bad.status_code == 422
    r = _case(client, org_a)
    assert r.status_code == 201, r.text
    case = r.json()
    cid = case["id"]
    assert case["targets"] == [{"fiscal_year": FY, "value_type": "final_true_up"}]
    st = case["readiness"]["statement"]
    approved = {row["line_code"]: row["approved"] for row in st["rows"]}
    assert approved["C.OM"]["value"] == "600.00" and approved["C.OM"]["page"] == 3
    assert {"C.OM", "C.TOTAL", "R.ARR", "R.GAP", "E.SALES"} <= set(approved)
    assert not st["summary"]["ready"] and set(case["readiness"]["missing_actuals"]) == set(approved)
    # no formulation on a true-up case
    assert client.post(f"/cases/{cid}/formulate", headers=headers(CLIENT_A)).status_code == 409

    def add(user: str = CLIENT_A, **b):
        return client.post(f"/cases/{cid}/actuals", json=b, headers=headers(user))

    # ---- grounding of a document actual is mechanical
    doc = {
        "line_code": "C.OM",
        "source_kind": "document",
        "stated_value": "61250.00",
        "stated_unit": "INR_lakh",
        "source_id": accounts,
        "page_index": 2,
    }
    r = add(**doc, excerpt="Operation and maintenance expenses for the year 62,250.00")
    assert r.status_code == 422 and "not on page" in r.json()["detail"]
    r = add(**{**doc, "stated_value": "56000.00"}, excerpt="Operation and maintenance expenses for the year 61,250.00")
    assert r.status_code == 422 and "not printed" in r.json()["detail"]
    assert (
        add(
            **doc, excerpt="Operation and maintenance expenses for the year 61,250.00", user=CLIENT_A_VIEWER
        ).status_code
        == 403
    )
    assert (
        add(**doc, excerpt="Operation and maintenance expenses for the year 61,250.00", user=CLIENT_B).status_code
        == 404
    )
    r = add(**doc, excerpt="Operation and maintenance expenses for the year 61,250.00")
    assert r.status_code == 201, r.text
    om = r.json()
    assert (
        om["canonical_value"] == "612.5"
        and om["canonical_unit"] == "INR_crore"
        and om["document_name"].startswith("SYNTHETIC_accounts")
    )

    # an estimate is an APR's, never a true-up's; a statement needs its document and reason
    assert (
        add(
            line_code="C.DEP",
            source_kind="estimate",
            stated_value="200",
            stated_unit="INR_crore",
            document_name="board note",
            rationale="half-year run rate",
        ).status_code
        == 422
    )
    assert (
        add(line_code="C.DEP", source_kind="statement", stated_value="200", stated_unit="INR_crore").status_code == 422
    )
    # a fact actual must be a reviewed fact of voice actual for the line and year
    r = add(line_code="C.DEP", source_kind="fact", fact_id=approved["C.DEP"]["fact_id"])
    assert r.status_code == 422 and "voice actual" in r.json()["detail"]

    # ---- the rest as statements; the total first entered wrongly
    for code, ap in approved.items():
        if code == "C.OM":
            continue
        value = "6800.00" if code == "C.TOTAL" else CHANGED.get(code, ap["value"])
        r = add(
            line_code=code,
            source_kind="statement",
            stated_value=value,
            stated_unit=ap["unit"],
            document_name="Audited accounts FY 2025-26",
            rationale="from the audited accounts",
        )
        assert r.status_code == 201, r.text
    assert len(client.get(f"/cases/{cid}/actuals", headers=headers(CLIENT_A_VIEWER)).json()) == len(approved)
    assert client.get(f"/cases/{cid}/actuals", headers=headers(CLIENT_B)).status_code == 404
    assert client.post(f"/cases/{cid}/statement/freeze", headers=headers(CLIENT_A)).status_code == 409

    r = client.post(f"/cases/{cid}/statement", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    st = r.json()["statement"]
    assert r.json()["status"] == "formulated" and not st["summary"]["ready"]
    assert any(f["severity"] == "blocking" and "C.TOTAL" in f["lines"] for f in st["findings"])
    r = client.post(f"/cases/{cid}/statement/freeze", headers=headers(CLIENT_A))
    assert r.status_code == 422 and "identity" in r.json()["detail"]

    # correct the total; the computed statement goes stale and is recomputed
    total = next(
        a for a in client.get(f"/cases/{cid}/actuals", headers=headers(CLIENT_A)).json() if a["line_code"] == "C.TOTAL"
    )
    assert client.delete(f"/cases/{cid}/actuals/{total['id']}", headers=headers(CLIENT_A)).status_code == 204
    assert (
        add(
            line_code="C.TOTAL",
            source_kind="statement",
            stated_value=CHANGED["C.TOTAL"],
            stated_unit="INR_crore",
            document_name="Audited accounts FY 2025-26",
            rationale="from the audited accounts",
        ).status_code
        == 201
    )
    got = client.get(f"/cases/{cid}", headers=headers(CLIENT_A)).json()
    assert got["status"] == "assumptions" and got["statement"] is None
    st = client.post(f"/cases/{cid}/statement", headers=headers(CLIENT_A)).json()["statement"]
    assert st["summary"]["ready"], st["summary"]
    assert not [f for f in st["findings"] if f["severity"] == "blocking"]
    rows = {row["line_code"]: row for row in st["rows"]}
    assert rows["C.OM"]["variance"] == "12.50" and rows["C.OM"]["actual"]["source_kind"] == "document"
    assert rows["R.GAP"]["variance"] == "12.50" and rows["E.SALES"]["variance"] == "0.00"
    assert st["summary"]["unchecked_statements"] == len(approved) - 1

    r = client.post(f"/cases/{cid}/statement/freeze", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "frozen" and r.json()["statement"]["frozen_by"] == CLIENT_A
    assert (
        add(
            line_code="L.NTI",
            source_kind="statement",
            stated_value="1",
            stated_unit="INR_crore",
            document_name="x",
            rationale="y",
        ).status_code
        == 409
    )

    # ---- the draft: every number traced, the unchecked figures named
    r = client.post(f"/cases/{cid}/draft", headers=headers(CLIENT_A))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["case_id"] == cid and d["formulation_id"] is None and d["status"] == "draft" and d["is_fixture"]
    kinds = d["trace"]["by_kind"]
    assert kinds["fact"] == len(approved) and kinds["actual"] == len(approved) and kinds["variance"] == len(approved)
    assert d["trace"]["statement_hash"] == st["input_hash"]
    om_actual = next(e for e in d["trace"]["entries"] if e["where"] == "TU-1!C.OM!actual")
    assert "checked on the page" in om_actual["origin"]["words"] and "p.2" in om_actual["origin"]["words"]
    assert client.get(f"/arr/drafts/{d['id']}", headers=headers(CLIENT_B)).status_code == 404
    f = client.get(f"/arr/drafts/{d['id']}/petition.docx", headers=headers(CLIENT_A_VIEWER))
    assert f.status_code == 200
    from docx import Document

    text = "\n".join(p.text for p in Document(io.BytesIO(f.content)).paragraphs)
    assert "DRAFT — prepared with software assistance; not filed" in text
    assert "could not check" in text and "not an amount the Commission has allowed" in text
    assert client.get(f"/cases/{cid}", headers=headers(CLIENT_A)).json()["status"] == "drafted"

    # ---- the case's activity: who did what, newest first; private to the organisation
    act = client.get(f"/cases/{cid}/activity", headers=headers(CLIENT_A_VIEWER)).json()
    actions = [a["action"] for a in act]
    assert actions[0] == "arr_case.drafted" and "arr_case.frozen" in actions and "arr_case.created" == actions[-1]
    assert actions.count("arr_case.actual_added") == len(approved) + 1 and "arr_case.actual_removed" in actions
    assert all(a["actor"] == CLIENT_A for a in act)
    assert client.get(f"/cases/{cid}/activity", headers=headers(CLIENT_B)).status_code == 404

    # ---- revise: the statement thaws, the draft stays on record
    r = client.post(f"/cases/{cid}/revise", headers=headers(CLIENT_A))
    assert r.status_code == 200 and r.json()["status"] == "assumptions" and r.json()["draft_id"] is None
    assert client.get(f"/arr/drafts/{d['id']}", headers=headers(CLIENT_A)).status_code == 200


def test_apr_case_takes_estimates(client, runner, object_store_root):
    read_and_publish(client, runner, LICENSEE)
    org = _org(client, "APRA", CLIENT_A)
    r = _case(client, org, "apr")
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["targets"][0]["value_type"] == "provisional_true_up"
    r = client.post(
        f"/cases/{cid}/actuals",
        json={
            "line_code": "C.DEP",
            "source_kind": "estimate",
            "stated_value": "205",
            "stated_unit": "INR_crore",
            "document_name": "half-year accounts",
            "rationale": "first half actual, second half at the same rate",
        },
        headers=headers(CLIENT_A),
    )
    assert r.status_code == 201, r.text
    st = client.get(f"/cases/{cid}", headers=headers(CLIENT_A)).json()["readiness"]["statement"]
    dep = next(row for row in st["rows"] if row["line_code"] == "C.DEP")
    assert dep["variance"] == "5.00" and dep["actual"]["source_kind"] == "estimate"
    assert st["summary"]["estimates"] == 1 and not st["summary"]["ready"]
