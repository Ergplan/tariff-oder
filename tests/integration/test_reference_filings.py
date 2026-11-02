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
    # clause candidates are proposals listed beside each rule (none until a regulation is read)
    assert all(isinstance(x["clause_candidates"], list) for x in d["rules"])
    assert d["summary"]["with_clause_candidates"] >= 0
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
    # the net ARR and gap match; the carried gap differs by A40's effect brought forward (0.25)
    assert end["counts"] == {"match": 10, "differs": 2} and len(end["fed"]) >= 12
    assert {c["output"]: c["computed"] for c in end["checks"]}["arr_net"] == "3481.83"
    # every format of the filing's index accounted for; the one listed and not filed is named
    acc = f["accounting"]
    assert sum(acc["counts"].values()) == 74
    assert [e["format"] for e in acc["formats"] if e["status"] == "missing"] == ["ESR7_BD monthly"]
    assert acc["counts"]["reproduced"] >= 27 and acc["not_in_index"] == ["F19A-O&M Normative"]
    # the narrative against the formats (R-ACC-5): the summary tables bound row by row, the
    # differing figures listed with their cells; the rest of the text traced by value
    nar = f["narrative"]
    assert nar["bound"]["counts"] == {"match": 232, "differs": 21}
    assert {c["key"] for c in nar["bound"]["checks"] if c["result"] == "differs"} >= {
        "arr",
        "open_access",
        "gap_previous",
    }
    assert len(nar["documents"]) == 7 and nar["untraced_by_table"][0]["figures"] > 0
    # the regulations' filing requirements with the evidence found (R-PKG-1)
    chk = f["checklist"]
    assert chk["counts"] == {"evidenced": 11, "partly": 2, "outside_package": 3, "mentioned": 1}
    assert chk["checklist"] == "uperc/myt-2025" and len(chk["items"]) == 17
    # the Commission's decisions read from its order, line by line (R-TU-5)
    dec = {t["proceeding"]: t for t in f["decisions"]["tables"]}
    assert set(dec) == {"true_up", "apr", "arr"}
    assert {r["key"]: r.get("decision") for r in dec["arr"]["rows"]}["arr_net"] == "29.51"
    assert client.get("/arr/reference-filings/nope", headers=headers(CLIENT_A)).status_code == 404


def test_independent_sign_off_is_pinned_to_the_reproduction_and_never_automatic(client):
    """R-ACC-2: a reviewer signs a scope off only with the attestation of independence, a reason
    for anything short of acceptance, and the hash of the reproduction they were shown; an
    analyst cannot sign; nothing is signed until someone does (every scope starts open)."""
    from conftest import ANALYST, REVIEWER

    url = "/arr/reference-filings/uperc-npcl-fy2026-27/acceptance"
    a = client.get(url, headers=headers(ANALYST)).json()
    assert a["records"] == [] or all(r["signed_by"] for r in a["records"])
    assert "filing" in a["scopes"] and "column:FY2026-27|petitioned" in a["scopes"] and "finding:A40" in a["scopes"]
    assert "filing" in a["open"]  # the build signs nothing
    sha = a["reproduction_sha256"]
    body = {
        "scope": "finding:A40",
        "decision": "accepted_with_reservations",
        "independent": True,
        "reproduction_sha256": sha,
    }
    assert client.post(url, json=body, headers=headers(ANALYST)).status_code == 403
    r = client.post(url, json={**body, "independent": False, "note": "x"}, headers=headers(REVIEWER))
    assert r.status_code == 422 and "did not build" in r.text
    assert client.post(url, json=body, headers=headers(REVIEWER)).status_code == 422  # a reservation needs its reason
    assert (
        client.post(
            url, json={**body, "scope": "column:FY2099-00|petitioned", "note": "x"}, headers=headers(REVIEWER)
        ).status_code
        == 422
    )
    stale = {**body, "note": "allow the amount disbursed", "reproduction_sha256": "0" * 64}
    assert client.post(url, json=stale, headers=headers(REVIEWER)).status_code == 409
    r = client.post(url, json={**body, "note": "allow the amount disbursed, 24.79"}, headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    a = client.get(url, headers=headers(ANALYST)).json()
    latest = a["latest"]["finding:A40"]
    assert latest["decision"] == "accepted_with_reservations" and latest["current"] and latest["signed_by"]
    assert "finding:A40" not in a["open"] and "filing" in a["open"]


def test_draft_queries_to_the_petitioner_are_a_labelled_draft(client):
    r = client.get("/arr/reference-filings/uperc-npcl-fy2026-27/queries", headers=headers(CLIENT_A))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    text = r.text
    assert "DRAFT for the reviewer to edit and issue" in text and "not issued" in text
    assert "(A44)" in text and "(A46)" in text  # questions to the petitioner, with their ids
    assert "## For the Commission" in text and "(A45)" in text  # the reviewer's own points, apart
    assert client.get("/arr/reference-filings/nope/queries", headers=headers(CLIENT_A)).status_code == 404
