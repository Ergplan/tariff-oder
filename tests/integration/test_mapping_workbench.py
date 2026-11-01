"""The mapping workbench (increment 39): the unplaced labels of a commission's read orders,
a reviewer's decisions on them, and the next mapping version drafted with them — never a
confirmed mapping.  SYNTHETIC fixture data."""

from __future__ import annotations

import json
import shutil

import pytest
from arr_helpers import read_and_publish

from conftest import ADMIN, CLIENT_A, REVIEWER, headers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]


def test_workbench_decisions_and_the_drafted_mapping(client, runner, object_store_root):
    read_and_publish(client, runner, "SYNTH-WB")
    r = client.get("/arr/mappings/SYNTHERC/workbench", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    wb = r.json()
    assert wb["commission"] == "SYNTHERC" and wb["mapping"]["id"] == "syntherc-arr" and wb["orders"]
    print("UNPLACED", [(x["label"], x["count"]) for x in wb["labels"]][:10])
    assert client.get("/arr/mappings/NOSUCH/workbench", headers=headers(CLIENT_A)).status_code == 404

    body = {"label": "Units at Licensee Periphery", "kind": "alias", "code": "E.INPUT.DIST", "note": "same quantity"}
    assert client.put("/arr/mappings/SYNTHERC/decisions", json=body, headers=headers(CLIENT_A)).status_code == 403
    assert (
        client.put(
            "/arr/mappings/SYNTHERC/decisions", json={**body, "code": "X.NOPE"}, headers=headers(REVIEWER)
        ).status_code
        == 422
    )
    r = client.put("/arr/mappings/SYNTHERC/decisions", json=body, headers=headers(REVIEWER))
    assert r.status_code == 200 and r.json()["label"] == "units at licensee periphery"
    r = client.put(
        "/arr/mappings/SYNTHERC/decisions",
        json={"label": "Contracted Quantum", "kind": "not_a_line", "note": "a schedule column"},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200 and r.json()["code"] is None

    r = client.get("/arr/mappings/SYNTHERC/draft", headers=headers(CLIENT_A))
    assert r.status_code == 200 and "syntherc-arr.v2.json" in r.headers["content-disposition"]
    d = json.loads(r.content)
    assert d["version"] == 2 and d["status"].startswith("draft") and "not confirmed" in d["status"]
    assert {"label": "units at licensee periphery", "code": "E.INPUT.DIST"}.items() <= next(
        e for e in d["label_aliases"]["entries"] if e["label"] == "units at licensee periphery"
    ).items()
    assert any(e["label"] == "interest on loan" for e in d["label_aliases"]["entries"])  # v1's own alias kept
    assert any(e["label"] == "contracted quantum" and e["decision"] == "not_a_line" for e in d["unplaced"]["entries"])

    assert (
        client.delete(
            "/arr/mappings/SYNTHERC/decisions?label=Contracted%20Quantum", headers=headers(REVIEWER)
        ).status_code
        == 204
    )
    d = json.loads(client.get("/arr/mappings/SYNTHERC/draft", headers=headers(ADMIN)).content)
    assert not any(e["label"] == "contracted quantum" for e in d["unplaced"]["entries"])


def test_a_commission_without_a_mapping_starts_from_the_generic_skeleton(client):
    from tariff_api.db import session_scope
    from tariff_api.models import Commission, Jurisdiction, JurisdictionKind

    with session_scope() as s:
        j = Jurisdiction(code="SYNB", name="SYNTHETIC jurisdiction B", kind=JurisdictionKind.state)
        s.add(j)
        s.flush()
        s.add(Commission(code="SYNTHB", name="SYNTHETIC commission B", jurisdiction_id=j.id))
    r = client.put(
        "/arr/mappings/SYNTHB/decisions",
        json={"label": "Units at Periphery", "kind": "alias", "code": "E.INPUT.DIST"},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    d = json.loads(client.get("/arr/mappings/SYNTHB/draft", headers=headers(CLIENT_A)).content)
    assert (d["id"], d["version"], d["commission"]) == ("synthb-arr", 1, "SYNTHB")
    assert "the generic skeleton" in d["status"] and "not confirmed" in d["status"]
    assert any(e["label"] == "units at periphery" for e in d["label_aliases"]["entries"])
