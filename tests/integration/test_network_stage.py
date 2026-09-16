"""Milestone 4b end to end: network-charge tables become typed facts with derivation inputs
that VAL-07 recomputes; prose decisions and green-tariff premiums are candidates; condition
records exist and VAL-12 links them; a second authoritative table is compared cell for cell
(VAL-16); an amendment table is checked against the consolidated schedule (VAL-05).  All
with the fixture provider; nothing is published."""

from __future__ import annotations

import shutil

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import dual_representation_pdf, gerc_amendment_order_pdf, network_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
CONFIRM = {"decision": "confirm", "rationale": "regions located; pages checked", "pages_viewed": True}


def _upload(client, data: bytes, name: str) -> str:
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["source"]["id"]


def _run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def _to_review(client, runner, data: bytes, name: str) -> str:
    src_id = _upload(client, data, name)
    assert _run_all(runner) == 4
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert _run_all(runner) == 3
    return src_id


def test_network_order_yields_typed_network_facts_with_derivations_and_conditions(client, runner):
    src_id = _to_review(client, runner, network_order_pdf(), "SYNTHETIC_network.pdf")
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "awaiting_review"
    fams = d["extraction"]["by_family"]
    assert {
        "wheeling_charge",
        "oa_loss",
        "cross_subsidy_surcharge",
        "distribution_loss_approved",
        "additional_surcharge",
        "banking_rule",
        "green_tariff",
        "retail_tariff",
    } <= set(fams)
    assert d["extraction"]["conditions"] >= 3  # provisions 20, 21 and the footnote
    assert d["validation"]["families_without_disposition"] == []  # 9.3.8 names the transmission loss and its order

    cands = client.get(f"/sources/{src_id}/candidates", params={"limit": 500}, headers=headers(ANALYST)).json()[
        "candidates"
    ]
    by_fam = {}
    for c in cands:
        by_fam.setdefault(c["family"], []).append(c)
    (w,) = by_fam["wheeling_charge"]
    assert (
        w["value"] == "1.03"
        and w["currency"] == "rupees"
        and w["per_unit"] == "kWh"
        and w["decision_status"] == "approved"
    )
    assert w["record"]["derivation"]["inputs"]["arr"]["value"] == "451.70" and "single_channel" in w["risk_tags"]
    losses = sorted((c["record"]["applicability"]["voltage"], c["value"]) for c in by_fam["oa_loss"])
    assert losses == [
        ("11 kV", "2.58"),
        ("33 kV", "0.79"),
        ("Below 11 kV", "6.97"),
        ("Inter-state transmission", "3.58"),
        ("Intra-state transmission", "3.18"),
    ]
    traj = sorted((c["period"], c["value"]) for c in by_fam["distribution_loss_approved"])
    assert traj == [("FY2025-26", "8.00"), ("FY2026-27", "7.48"), ("FY2027-28", "7.00")]
    css = {c["category_code"]: c for c in by_fam["cross_subsidy_surcharge"]}
    assert css["LMV-2"]["value"] == "1.33" and css["HV-1"]["value_state"] == "not_applicable"
    (add,) = by_fam["additional_surcharge"]
    assert add["decision_status"] == "approved_zero" and add["value"] == "0" and add["value_state"] == "zero"
    # the CSS approved rows carry the formula: inputs with evidence, D from DC + TC + WC, the
    # recomputed S and the cap; VAL-07 recomputes and compares with what the order printed
    f11 = css["LMV-2"]["record"]["derivation"]["formula"]
    assert f11["rule"] == "css_formula" and f11["level"] == "11kv" and f11["computed"] == "1.3348"
    assert f11["inputs"]["T"]["value"] == "7.06" and f11["inputs"]["DC"]["value"] == "0.10"
    assert f11["inputs"]["C"]["evidence"]["page_index"] == 6 and f11["inputs"]["C"]["evidence"]["kind"] == "cell"
    assert f11["printed_computed"] == "1.33" and f11["printed_cap"] == "1.41" and f11["cap_20pct_of_T"] == "1.4120"
    assert f11["formula_as_printed"]["text"].startswith("S = T - [C/(1-L/100) + D + R]")
    assert f11["definitions"]["D"]["text"].startswith("D is the aggregate of transmission, distribution and wheeling")
    f33 = css["HV-2"]["record"]["derivation"]["formula"]
    assert f33["computed"] == "1.4487" and f33["d_used"] == "0.34"
    # transmission loss and charges appear as inputs of the open-access determination:
    # captured as referenced values with their source, never as a transmission tariff
    tr = by_fam["transmission_reference"]
    loss = next(c for c in tr if c["component_type"] == "loss")
    assert loss["value"] == "3.18" and loss["per_unit"] == "percent" and loss["decision_status"] == "by_reference"
    assert "order dated" in (loss["record"]["reference_target"] or "") or "determined" in (
        loss["record"]["reference_target"] or ""
    )
    (bank,) = by_fam["banking_rule"]
    assert bank["decision_status"] == "by_reference" and "Regulations" in bank["record"]["reference_target"]
    green = sorted((c["record"]["applicability"]["voltage"], c["value"]) for c in by_fam["green_tariff"])
    assert green == [("HV", "0.34"), ("LMV", "0.17")]
    assert all(
        "regulatory discount shall not be applicable" in c["record"]["conditions"][0] for c in by_fam["green_tariff"]
    )
    retail = by_fam["retail_tariff"]
    starred = next(c for c in retail if c["record"]["original_text"].endswith("*"))
    assert starred["record"]["conditions"] == ["subject to the regulatory discount of general provision 21"]

    findings = client.get(f"/sources/{src_id}/findings", headers=headers(ANALYST)).json()["findings"]
    v07 = [f for f in findings if f["validator_id"] == "VAL-07"]
    assert any(f["severity"] == "info" and "agrees with ARR/sales (1.0266)" in f["message"] for f in v07)
    assert any("CSS at 11kv: printed computed 1.33 agrees with S = T" in f["message"] for f in v07)
    assert any("CSS at 11kv: approved 1.33 is within the 20% cap 1.41" in f["message"] for f in v07)
    assert any(
        f["severity"] == "blocking" and "CSS at 33kv: approved 1.45 exceeds the 20% cap 1.42" in f["message"]
        for f in v07
    )
    assert any(
        f["severity"] == "blocking" and "not the lower" in f["message"] for f in v07
    )  # HV-2: 1.45 is not min(1.20, 1.45)
    hv2 = css["HV-2"]
    assert (
        hv2["blocking_finding_count"] >= 1
        and "validator_finding" in hv2["risk_tags"]
        and hv2["routing"] == "individual"
    )
    v08 = [f for f in findings if f["validator_id"] == "VAL-08"]
    assert v08 == []  # losses cite the regions that give them their roles
    v12 = [f for f in findings if f["validator_id"] == "VAL-12"]
    assert v12 == []  # every candidate condition is a recorded provision or footnote
    conds = client.get(f"/sources/{src_id}/conditions", headers=headers(ANALYST)).json()
    kinds = {c["kind"] for c in conds["conditions"]}
    assert {"general_provision", "footnote"} <= kinds
    p21 = next(c for c in conds["conditions"] if c["number"] == "21")
    assert p21["interpretation_status"] == "verbatim_only" and "regulatory discount of 10%" in p21["text"]
    assert (
        client.get(f"/sources/{src_id}/conditions", params={"kind": "footnote"}, headers=headers(ANALYST)).json()[
            "total"
        ]
        == 1
    )


def test_two_authoritative_representations_are_compared_cell_for_cell(client, runner):
    src_id = _to_review(client, runner, dual_representation_pdf(disagree=True), "SYNTHETIC_dual.pdf")
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["reading_profile"]["profile_id"] == "kerc-escoms"
    findings = client.get(
        f"/sources/{src_id}/findings", params={"validator": "VAL-16"}, headers=headers(ANALYST)
    ).json()["findings"]
    assert findings, "the KERC profile declares a secondary authoritative table"
    msgs = [f["message"] for f in findings]
    assert any("LT-1" in m and "agree (145)" in m for m in msgs) or any(
        "LT-1" in m and "agree (580)" in m for m in msgs
    )
    block = [f for f in findings if f["severity"] == "blocking"]
    assert (
        len(block) == 1
        and "LT-2" in block[0]["message"]
        and "585" in block[0]["message"]
        and "650" in block[0]["message"]
    )
    assert len(block[0]["candidate_ids"]) == 2
    for cid in block[0]["candidate_ids"]:
        c = client.get(f"/candidates/{cid}", headers=headers(ANALYST)).json()
        assert c["blocking_finding_count"] >= 1 and c["routing"] == "individual"

    agree_id = _to_review(client, runner, dual_representation_pdf(disagree=False), "SYNTHETIC_dual_ok.pdf")
    ok = client.get(f"/sources/{agree_id}/findings", params={"validator": "VAL-16"}, headers=headers(ANALYST)).json()[
        "findings"
    ]
    assert ok and all(f["severity"] == "info" for f in ok)


def test_amendment_table_is_checked_against_the_consolidated_schedule(client, runner):
    src_id = _to_review(client, runner, gerc_amendment_order_pdf(mismatch=True), "SYNTHETIC_amend.pdf")
    findings = client.get(
        f"/sources/{src_id}/findings", params={"validator": "VAL-05"}, headers=headers(ANALYST)
    ).json()["findings"]
    assert [(f["severity"], f["detail"]["clause"]) for f in findings] == [("info", "1.4"), ("blocking", "4.4")]
    assert "not found in the consolidated schedule" in findings[1]["message"]
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["validation"]["by_validator"]["VAL-05"] == 2 and d["state"] == "awaiting_review"
    cands = client.get(f"/sources/{src_id}/candidates", params={"limit": 500}, headers=headers(ANALYST)).json()[
        "candidates"
    ]
    assert all(
        c["record"]["evidence"][0]["page_index"] >= 3 for c in cands
    )  # nothing extracted from the amendment table itself


def test_a_reviewer_can_exclude_a_region_with_a_note_and_the_stages_leave_it_alone(client, runner):
    """Section 6.5: a reviewer's comment on one region, with an exclusion the structure and
    extraction stages honour; the note follows the family into the checklist.  Role-gated,
    versioned, audited; frozen once candidates exist."""
    src_id = _upload(client, network_order_pdf(), "SYNTHETIC_network_excluded.pdf")
    assert _run_all(runner) == 4
    L = client.get(f"/sources/{src_id}/localisation", headers=headers(ANALYST)).json()
    # the wheeling region is the only one covering its page, so excluding it removes the family
    bank = next(r for r in L["regions"] if r["sub_role"] == "wheeling_charge")
    assert bank["reviewer_note"] is None and bank["excluded"] is False
    url = f"/sources/{src_id}/localisation/regions/{bank['id']}"
    note = {
        "note": "These are the utility's own inter-state charges, not the open-access wheeling charge; out of scope.",
        "excluded": True,
        "expected_version": L["version"],
    }
    assert client.put(url, json=note, headers=headers(ANALYST)).status_code == 403
    r = client.put(url, json={**note, "expected_version": L["version"] + 7}, headers=headers(REVIEWER))
    assert r.status_code == 409 and r.json()["error_type"] == "conflict_stale_version"
    r = client.put(url, json={**note, "note": "no"}, headers=headers(REVIEWER))
    assert r.status_code == 422
    r = client.put(url, json=note, headers=headers(REVIEWER))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == L["version"] + 1 and out["extraction_allowed"] is False  # a note is not a decision
    bank2 = next(x for x in out["regions"] if x["id"] == bank["id"])
    assert bank2["excluded"] is True and bank2["annotated_by"] == REVIEWER and bank2["reviewer_note"] == note["note"]
    audit = client.get(
        "/audit", params={"entity_type": "localisation_region", "entity_id": bank["id"]}, headers=headers(ADMIN)
    ).json()
    assert [a["action"] for a in audit] == ["localisation.annotate"]
    assert audit[0]["before"]["excluded"] is False and audit[0]["after"]["excluded"] is True

    # confirm with the current version, run the remaining stages
    r = client.post(
        f"/sources/{src_id}/localisation/decision",
        json={**CONFIRM, "expected_version": out["version"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    assert _run_all(runner) == 3
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "awaiting_review"
    assert "wheeling_charge" not in d["extraction"]["by_family"]
    assert "wheeling_charge" in d["validation"]["families_without_disposition"]
    assert "additional_surcharge" in d["extraction"]["by_family"]  # the neighbouring family is unaffected
    assert d["structure"]["regions_excluded"] == [bank["ordinal"]]
    cl = client.get(f"/sources/{src_id}/review/checklist", headers=headers(ANALYST)).json()
    fam = next(i for i in cl["items"] if i["kind"] == "family" and i["key"] == "wheeling_charge")
    assert fam["candidates"] == 0 and fam["status"] == "not_started"
    assert "no candidate and no reviewed disposition" in fam["note"] and "inter-state charges" in fam["note"]
    assert f"excluded by {REVIEWER}" in fam["note"]

    # candidates exist: the region set is frozen
    r = client.put(url, json={**note, "excluded": False, "expected_version": None}, headers=headers(REVIEWER))
    assert r.status_code == 409 and r.json()["error_type"] == "invalid_transition"
