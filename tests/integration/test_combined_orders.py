"""Combined orders (increment 35): one order decides the ARR of several licensees.  The order's
licensees are set by a person; each value is attributed to the licensee its column or its
table's caption names; a total across licensees is skipped and reported; identities hold per
licensee; publication files each fact under its own licensee.  SYNTHETIC fixture data."""

from __future__ import annotations

import shutil

import pytest
from arr_helpers import decide, ensure_licensee, run_all, upload

from conftest import ADMIN, CLIENT_A, REVIEWER, headers
from fixtures.synthetic_pdfs import combined_arr_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
NORTH, SOUTH = "SYNTH-NORTH", "SYNTH-SOUTH"


def test_a_combined_order_is_read_and_published_per_licensee(client, runner, object_store_root):
    ensure_licensee(NORTH)
    ensure_licensee(SOUTH)
    order = upload(client, combined_arr_order_pdf(NORTH, SOUTH), "SYNTHETIC_combined_arr_order.pdf", utility_code=NORTH)
    run_all(runner)

    # the order's licensees are set by a person
    assert client.put(f"/sources/{order}/licensees", json={"codes": [SOUTH]}, headers=headers(ADMIN)).status_code == 422
    assert (
        client.put(f"/sources/{order}/licensees", json={"codes": [NORTH, SOUTH]}, headers=headers(REVIEWER)).status_code
        == 403
    )
    r = client.put(f"/sources/{order}/licensees", json={"codes": [NORTH, SOUTH]}, headers=headers(ADMIN))
    assert r.status_code == 200, r.text
    assert [(x["code"], x["primary"]) for x in r.json()] == [(NORTH, True), (SOUTH, False)]
    assert [x["code"] for x in client.get(f"/sources/{order}/licensees", headers=headers(CLIENT_A)).json()] == [
        NORTH,
        SOUTH,
    ]

    assert client.post(f"/sources/{order}/arr/read", headers=headers(ADMIN)).status_code == 202
    run_all(runner)
    r = client.post(
        f"/sources/{order}/arr/chapters/decision", json={"rationale": "chapters checked"}, headers=headers(REVIEWER)
    )
    assert r.status_code == 200, r.text
    run_all(runner)

    reading = client.get(f"/sources/{order}/arr", headers=headers(REVIEWER)).json()
    cands = client.get(f"/sources/{order}/arr/candidates", headers=headers(REVIEWER)).json()["candidates"]
    by = {
        (c["record"]["utility"], c["record"]["line_code"], c["record"]["fiscal_year"], c["record"]["value_type"]): c
        for c in cands
    }
    assert by[(NORTH, "C.PP", "FY2025-26", "approved")]["record"]["stated_value"] == "2800.00"
    assert by[(SOUTH, "C.PP", "FY2025-26", "approved")]["record"]["stated_value"] == "2200.00"
    assert by[(SOUTH, "E.SALES", "FY2025-26", "approved")]["record"]["stated_value"] == "3600.00"
    # the caption names the licensee of a table whose columns carry the year and the voice
    assert by[(SOUTH, "C.OM", "FY2024-25", "final_true_up")]["record"]["stated_value"] == "240.00"
    assert not [k for k in by if k[0] not in (NORTH, SOUTH)]  # nothing from the total column
    skipped = [c for ch in reading["arr_summary"]["extraction"]["chapters"] for c in ch["columns_skipped"]]
    assert {c["header"] for c in skipped if "total across licensees" in c["reason"]} == {"Total"}
    # identities hold per licensee (a pooled check would add the two licensees together)
    assert not [f for f in reading["findings"] if f["severity"] == "blocking"], reading["findings"]

    for c in cands:
        c = decide(client, c, "approve", REVIEWER)
        if c["review_status"] == "awaiting_second_review":
            decide(client, c, "approve", ADMIN)
    run_all(runner)
    r = client.post(f"/sources/{order}/arr/publish", headers=headers(REVIEWER))
    assert r.status_code == 200, r.text

    south = client.get(f"/arr/utilities/{SOUTH}/history", headers=headers(CLIENT_A)).json()
    north = client.get(f"/arr/utilities/{NORTH}/history", headers=headers(CLIENT_A)).json()

    def fact(h, line, fy, vt):
        cell = next(c for ln in h["lines"] if ln["line_code"] == line for c in ln["cells"] if c["fiscal_year"] == fy)
        return next(f for f in cell["facts"] if f["value_type"] == vt)

    assert fact(south, "C.PP", "FY2025-26", "approved")["canonical_value"] == "2200.00"
    assert fact(north, "C.PP", "FY2025-26", "approved")["canonical_value"] == "2800.00"
    assert fact(south, "C.OM", "FY2024-25", "final_true_up")["canonical_value"] == "240.00"
    assert not [ln for ln in north["lines"] if any(c["fiscal_year"] == "FY2024-25" for c in ln["cells"])]
    b = client.get("/arr/benchmarks?fiscal_year=FY2025-26&include_fixtures=true", headers=headers(CLIENT_A)).json()
    rows = {r["code"]: r["values"] for r in b["licensees"]}
    assert (
        rows[NORTH]["pp_cost_per_unit_input"]["value"] == "5.600"
        and rows[SOUTH]["pp_cost_per_unit_input"]["value"] == "5.500"
    )
