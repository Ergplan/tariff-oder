"""The ARR taxonomy and mappings are readable in the app (analyst and above), as data."""

from __future__ import annotations

from conftest import ANALYST, headers


def test_taxonomy_and_mappings_are_served_read_only(client):
    r = client.get("/arr/taxonomy", headers=headers(ANALYST))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["id"] == "arr-taxonomy" and t["version"] >= 1
    codes = {i["code"] for i in t["line_items"]}
    assert {"R.ARR", "C.OM.EMPLOYEE", "E.LOSS.DIST_PCT", "T.TARIFF.TOTAL"} <= codes
    assert {"UPERC", "KERC", "GERC"} <= set(t["mappings"])
    assert any(i["id"] == "ARR-I1" and i["severity"] == "blocking" for i in t["identities"])

    m = client.get("/arr/mappings/uperc", headers=headers(ANALYST))
    assert m.status_code == 200 and m.json()["commission"] == "UPERC"
    assert m.json()["taxonomy_version"] == t["version"]
    assert client.get("/arr/mappings/NOPE", headers=headers(ANALYST)).status_code == 404
    assert client.get("/arr/taxonomy").status_code in (401, 403)
