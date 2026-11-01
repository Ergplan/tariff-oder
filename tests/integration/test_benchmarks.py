"""Benchmarks across licensees (increment 34): ratios derived from reviewed, published ARR facts,
each with its inputs; fixture licensees only when asked for; a missing input is a reason, not
a value.  SYNTHETIC fixture data."""

from __future__ import annotations

import shutil

import pytest
from arr_helpers import read_and_publish

from conftest import CLIENT_A, headers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]


def test_benchmarks_are_derived_from_published_facts_with_their_inputs(client, runner, object_store_root):
    read_and_publish(client, runner, "SYNTH-BM-A")
    read_and_publish(client, runner, "SYNTH-BM-B")

    r = client.get("/arr/benchmarks?fiscal_year=FY2025-26", headers=headers(CLIENT_A))
    assert r.status_code == 200 and r.json()["licensees"] == []  # fixtures only when asked for
    assert client.get("/arr/benchmarks?fiscal_year=2025", headers=headers(CLIENT_A)).status_code == 422

    b = client.get("/arr/benchmarks?fiscal_year=FY2025-26&include_fixtures=true", headers=headers(CLIENT_A)).json()
    assert b["kind"] == "derived" and {m["id"] for m in b["metrics"]} >= {"pp_cost_per_unit_input", "gap_share_of_arr"}
    rows = {r["code"]: r for r in b["licensees"]}
    assert set(rows) == {"SYNTH-BM-A", "SYNTH-BM-B"} and all(r["is_fixture"] for r in rows.values())
    v = rows["SYNTH-BM-A"]["values"]
    # approved FY2025-26 of the synthetic order: PP 5,000 / input 10,000 MU; O&M 600 and ARR
    # 6,600 over sales 9,000 MU; gap 200; RoE 300 of expenditure 6,700
    assert v["pp_cost_per_unit_input"]["value"] == "5.000"
    assert v["om_per_unit_sold"]["value"] == "0.667"
    assert v["arr_per_unit_sold"]["value"] == "7.333"
    assert v["distribution_loss"]["value"] == "10.00"
    assert v["gap_share_of_arr"]["value"] == "3.03"
    assert v["roe_share_of_expenditure"]["value"] == "4.48"
    pp = v["pp_cost_per_unit_input"]["inputs"]
    assert [i["line_code"] for i in pp] == ["C.PP", "E.INPUT.DIST"] and pp[0]["page"] == 3 and pp[0]["fact_id"]
    st = b["stats"]["arr_per_unit_sold"]
    assert (st["n"], st["min"], st["median"], st["max"]) == (2, "7.333", "7.333", "7.333")
    assert v["arr_per_unit_sold"]["rank"] == 1

    # the petition's printed total failed its identity and was rejected: no value, a reason
    p = client.get(
        "/arr/benchmarks?fiscal_year=FY2025-26&value_type=petitioned&include_fixtures=true", headers=headers(CLIENT_A)
    ).json()
    roe = {r["code"]: r for r in p["licensees"]}["SYNTH-BM-A"]["values"]["roe_share_of_expenditure"]
    assert roe["value"] is None and "C.TOTAL" in roe["reason"]
    assert {r["code"]: r for r in p["licensees"]}["SYNTH-BM-A"]["values"]["pp_cost_per_unit_input"]["value"] == "5.150"
