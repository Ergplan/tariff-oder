"""Mapping conventions (increment 44): a read order's identity failure poses a convention
question in the commission's workbench, a reviewer answers it, and the drafted mapping states
it — never a confirmed mapping, never applied by the hint alone.  SYNTHETIC fixture data; the
preview's hint is written into the synthetic order's summary by the test."""

from __future__ import annotations

import json
import shutil

import pytest
from arr_helpers import read_and_publish
from sqlalchemy import select

from conftest import CLIENT_A, REVIEWER, headers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]

HINT = {"total": "C.PP", "includes": ["C.TX"], "why": "power purchase printed inclusive of transmission charges"}
KEY = "convention:total_includes:C.PP:C.TX"


def _pose_questions() -> None:
    from tariff_api.db import session_scope
    from tariff_api.models import Commission, SourceDocument, Utility

    with session_scope() as s:
        src = (
            s.execute(
                select(SourceDocument)
                .join(Utility, Utility.id == SourceDocument.utility_id)
                .join(Commission, Commission.id == Utility.commission_id)
                .where(Commission.code == "SYNTHERC", SourceDocument.arr_summary.is_not(None))
            )
            .scalars()
            .first()
        )
        summary = dict(src.arr_summary)
        summary["preview"] = {
            "rules": "test",
            "note": "SYNTHETIC",
            "chapters": [
                {
                    "chapter": 1,
                    "findings": [
                        {
                            "identity_id": "ARR-I1",
                            "message": "ARR-I1 … reconciles if C.PP includes C.TX",
                            "reconciles_if": HINT,
                        },
                        {"identity_id": "ARR-I3", "message": "ARR-I3 Revenue gap …", "reconciles_if": None},
                        {"identity_id": "ARR-I4", "message": "ARR-I4 …", "reconciles_if": None},
                        {
                            "identity_id": "ARR-I4",
                            "message": "ARR-I4 … reconciles if the loss applies to the sales within the state",
                            "reconciles_if": {"loss_basis": "sales_within_state", "why": "inter-state sales excluded"},
                        },
                    ],
                }
            ],
        }
        src.arr_summary = summary


def test_a_convention_question_is_answered_and_drafted(client, runner, object_store_root):
    read_and_publish(client, runner, "SYNTH-CV")
    _pose_questions()
    wb = client.get("/arr/mappings/SYNTHERC/workbench", headers=headers(CLIENT_A)).json()
    qs = {q["key"]: q for q in wb["conventions"]}
    # an ARR-I4 failure no convention explains poses no question; one the loss basis explains does
    assert set(qs) == {KEY, "convention:gap_convention", "convention:loss_basis"}, qs
    assert qs[KEY]["values"] == ["applies", "does_not_apply"] and qs[KEY]["decision"] is None
    assert qs[KEY]["evidence"][0]["chapter"] == 1

    base = "/arr/mappings/SYNTHERC/conventions"
    answer = {"key": KEY, "value": "applies", "note": "Table 63 prints transmission inside power purchase"}
    assert client.put(base, json=answer, headers=headers(CLIENT_A)).status_code == 403
    assert client.put(base, json={**answer, "value": "maybe"}, headers=headers(REVIEWER)).status_code == 422
    bad_key = {**answer, "key": "convention:total_includes:C.PP:X.NOPE"}
    assert client.put(base, json=bad_key, headers=headers(REVIEWER)).status_code == 422
    r = client.put(base, json=answer, headers=headers(REVIEWER))
    assert r.status_code == 200 and r.json()["value"] == "applies", r.text
    gap = {"key": "convention:gap_convention", "value": "after_subsidy"}
    assert client.put(base, json=gap, headers=headers(REVIEWER)).status_code == 200
    loss = {"key": "convention:loss_basis", "value": "sales_within_state", "note": "Table 4.5 rows 1-6"}
    assert client.put(base, json={**loss, "value": "most"}, headers=headers(REVIEWER)).status_code == 422
    assert client.put(base, json=loss, headers=headers(REVIEWER)).status_code == 200

    wb = client.get("/arr/mappings/SYNTHERC/workbench", headers=headers(CLIENT_A)).json()
    assert {q["key"]: (q["decision"] or {}).get("value") for q in wb["conventions"]} == {
        KEY: "applies",
        "convention:gap_convention": "after_subsidy",
        "convention:loss_basis": "sales_within_state",
    }
    assert all(not x["label"].startswith("convention:") for x in wb["labels"])

    d = json.loads(client.get("/arr/mappings/SYNTHERC/draft", headers=headers(CLIENT_A)).content)
    assert d["status"].startswith("draft") and "not confirmed" in d["status"]
    assert d["gap_convention"]["value"] == "after_subsidy"
    assert d["loss_basis"]["value"] == "sales_within_state"
    assert [(t["total"], t["includes"]) for t in d["total_includes"]] == [("C.PP", ["C.TX"])]
    from tariff_api.arr.taxonomy import Mapping

    Mapping(**d)  # the draft is a valid mapping file

    r = client.delete(f"/arr/mappings/SYNTHERC/decisions?label={KEY}", headers=headers(REVIEWER))
    assert r.status_code == 204
    d = json.loads(client.get("/arr/mappings/SYNTHERC/draft", headers=headers(CLIENT_A)).content)
    assert d["total_includes"] == []
