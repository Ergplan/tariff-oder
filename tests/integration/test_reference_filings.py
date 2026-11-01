"""Reference filings and calculation rules for the desk (milestone 13): read-only views of the
real NPCL reference filing and the UPERC draft rules (files in packages/; no fixture data)."""

from __future__ import annotations

import pytest

from conftest import CLIENT_A, headers

pytestmark = [pytest.mark.integration]


def test_rules_are_listed_with_their_status_and_nothing_is_approved(client):
    r = client.get("/arr/rules/uperc", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["summary"]["rules"] >= 60
    assert d["summary"]["approved"] == 0 and d["summary"]["clauses_verified"] == 0  # the build approves nothing
    roe = [x for x in d["rules"] if x["output"] == "return_on_equity"]
    assert {x["to_fy"] or x["from_fy"] for x in roe} == {"FY2024-25", "FY2025-26"}  # two regimes
    assert client.get("/arr/rules/NOPE", headers=headers(CLIENT_A)).status_code == 404
    assert client.get("/arr/rules/uperc").status_code in (401, 403)


def test_the_npcl_reference_filing_and_its_reproduction(client):
    lst = client.get("/arr/reference-filings", headers=headers(CLIENT_A)).json()
    assert {x["id"] for x in lst} >= {"uperc-npcl-fy2026-27", "uperc-npcl-fy2025-26"}
    f = client.get("/arr/reference-filings/uperc-npcl-fy2026-27", headers=headers(CLIENT_A)).json()
    assert f["documents"]["hashed"] >= 69
    chain = f["chain"]["by_column"]
    assert chain["FY2026-27 · Projected"] == {"match": 12}
    assert {x["id"] for x in f["findings"]} >= {"A29", "A35", "A39", "A40", "A41"}
    # how each ARR figure is established: the projected column's power purchase is tied to its
    # schedule, the chain computes the net ARR, non-tariff income is still a record (on trust)
    cov = f["coverage"]
    m = {c["column"] for c in cov["columns"] if c["fiscal_year"] == "FY2026-27" and c["voice"] == "petitioned"}
    (col,) = m
    by_row = {line["row"]: line["cells"].get(col, {}).get("status") for line in cov["lines"]}
    assert by_row[20] == "tied" and by_row[53] == "computed" and by_row[50] == "record"
    assert cov["summary"][col].get("differs", 0) == 0
    # end to end: the projected column's chain fed by the schedules reproduces the net ARR
    (end,) = [p for p in f["pipeline"] if p["fiscal_year"] == "FY2026-27"]
    assert end["counts"] == {"match": 12} and len(end["fed"]) >= 12
    assert {c["output"]: c["computed"] for c in end["checks"]}["arr_net"] == "3481.83"
    assert client.get("/arr/reference-filings/nope", headers=headers(CLIENT_A)).status_code == 404
