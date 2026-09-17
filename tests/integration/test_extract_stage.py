"""Milestone 4a gate items: candidates preserve decimals, original text, units, value_state,
decision_status, conditions and cell/clause evidence; channel disagreements are recorded and
routed; every validator has a fixture (unit) and findings attach to candidates here; an
adversarial fixture with instruction-like text does not alter outputs; fixture runs are
labelled and never summed with real runs; impossible outputs enter the review queue; nothing
is published."""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import gerc_structure_order_pdf, structure_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
CONFIRM = {"decision": "confirm", "rationale": "Annexure located; pages checked", "pages_viewed": True}


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
    assert _run_all(runner) == 4  # inventory, triage, parse, localise
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert _run_all(runner) == 3  # grid -> extract -> validate, chained
    return src_id


def test_dual_channel_fixture_extraction_produces_routed_candidates_and_findings(client, runner, storage):
    src_id = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure.pdf")
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "awaiting_review"
    ex = d["extraction"]
    assert ex["is_fixture"] is True and ex["provider"] == "fixture" and ex["cost_usd"] == 0.0
    assert ex["prompt_version"] == "1" and ex["schema_version"] == "2" and ex["image_channel"] is True
    assert ex["runs"] == 2 and ex["runs_failed"] == 0  # one approved region, two channels
    assert ex["candidates"] > 15 and set(ex["by_agreement"]) == {"agree"}
    assert ex["new_profile"] is True and ex["by_routing"] == {"individual": ex["candidates"]}
    assert (
        ex["risk_tags"]["new_profile"] == ex["candidates"]
    )  # first order read with this profile: everything individual

    cands = client.get(f"/sources/{src_id}/candidates", params={"limit": 500}, headers=headers(ANALYST)).json()
    assert cands["total"] == ex["candidates"] and all(c["is_fixture"] for c in cands["candidates"])
    energy = [c for c in cands["candidates"] if c["component_type"] == "energy" and c["category_code"] == "LMV-1"]
    assert sorted(c["value"] for c in energy) == ["3.00", "3.50", "4.00", "5.00"]
    assert all(c["currency"] == "rupees" and c["per_unit"] == "kWh" and c["value_state"] == "value" for c in energy)
    starred = next(c for c in energy if c["value"] == "5.00")
    rec = starred["record"]
    assert rec["original_text"] == "Rs. 5.00/ kWh *"
    assert rec["conditions"] == ["subject to the regulatory discount of general provision 21"]
    assert rec["evidence"][0]["kind"] == "cell" and rec["evidence"][0]["page_index"] == 5
    assert rec["applicability"]["slab"]["lower"] == "300" and rec["applicability"]["description"] == "Metered"
    assert "merged_cell_propagated" in starred["risk_tags"] and starred["confidence"] == "high"
    assert starred["image_record"]["value"] == "5.00" and starred["channel_agreement"] == "agree"
    tod = [c for c in cands["candidates"] if c["component_type"] == "tod_adjustment"]
    assert sorted((c["value"], c["value_state"], c["record"]["sign"]) for c in tod) == [
        ("0", "zero", None),
        ("15", "value", -1),
        ("15", "value", 1),
    ]
    nil = next(c for c in cands["candidates"] if c["record"]["original_text"] == "Nil")
    assert nil["value_state"] == "zero" and nil["value"] is None and "nil_word" in nil["risk_tags"]
    xref = next(c for c in cands["candidates"] if c["value_state"] == "cross_reference")
    assert xref["record"]["reference_target"] == "HV-1" and "cross_reference" in xref["risk_tags"]
    one = client.get(f"/candidates/{starred['id']}", headers=headers(ANALYST)).json()
    assert one["candidate_key"] == starred["candidate_key"] and one["review_status"] == "pending"
    by_risk = client.get(
        f"/sources/{src_id}/candidates", params={"risk": "unit_unresolved"}, headers=headers(ANALYST)
    ).json()
    assert by_risk["total"] >= 1  # the 1,00,000 minimum with no unit anywhere: in the queue, never defaulted

    # the model feedback loop ran (fixture template): every candidate carries a grounded
    # assessment with a confidence and a meaning; nothing was routed by it on this clean order
    assessed = [c for c in cands["candidates"] if c["record"].get("assessment")]
    assert len(assessed) == len(cands["candidates"])
    a0 = assessed[0]["record"]["assessment"]
    assert (
        a0["is_fixture"]
        and a0["grounded"]
        and 0 <= a0["confidence"] <= 1
        and a0["meaning"]
        and a0["prompt_version"] == "1"
    )
    assert not any("assessment_ungrounded" in c["risk_tags"] for c in cands["candidates"])
    # every schedule category gets a generated, grounding-checked summary (fixture template here)
    sm = client.get(f"/sources/{src_id}/summaries", headers=headers(ANALYST)).json()
    assert sm["total"] >= 1 and all(
        x["is_fixture"] and x["grounded"] and x["provider"] == "fixture" for x in sm["summaries"]
    )
    assert {x["category_code"] for x in sm["summaries"]} == {
        c["category_code"] for c in cands["candidates"] if c["family"] == "retail_tariff" and c["category_code"]
    }
    assert ex["category_summaries"] == sm["total"] and ex["summaries_grounded"] == sm["total"]
    # the table as read is available for any cited cell
    ev0 = next(c for c in cands["candidates"] if c["record"]["evidence"][0]["kind"] == "cell")["record"]["evidence"][0]
    rows = client.get(
        f"/sources/{src_id}/tables/{ev0['page_index']}/{ev0['grid_ordinal']}/rows", headers=headers(ANALYST)
    ).json()
    assert rows["reader"] == "pymupdf" and rows["rows"][ev0["row"]][ev0["col"]] == ev0["excerpt"]

    # validators ran, findings attach, families without a decision block coverage
    val = d["validation"]
    assert val["validators_version"] == "3" and val["findings"] > 0
    assert len(val["families_without_disposition"]) == 8  # no network-charge region in this fixture
    findings = client.get(f"/sources/{src_id}/findings", headers=headers(ANALYST)).json()
    ids = {f["validator_id"] for f in findings["findings"]}
    assert "VAL-06" in ids and "VAL-03" in ids  # completeness; the twice-claimed slab boundary on page 7
    slab_f = next(f for f in findings["findings"] if f["validator_id"] == "VAL-03" and "ambiguous" in f["message"])
    assert slab_f["candidate_ids"]
    flagged = client.get(f"/candidates/{slab_f['candidate_ids'][0]}", headers=headers(ANALYST)).json()
    assert "validator_finding" in flagged["risk_tags"] and flagged["finding_count"] >= 1
    blocking = client.get(
        f"/sources/{src_id}/findings", params={"severity": "blocking"}, headers=headers(ANALYST)
    ).json()
    assert all(f["validator_id"] == "VAL-06" for f in blocking["findings"])  # nothing else blocks on a clean fixture

    # telemetry: fixture runs are labelled and never summed as real cost
    runs = client.get(f"/sources/{src_id}/extraction-runs", headers=headers(ANALYST)).json()
    # the structure channel is the rules (free, neither fixture nor model); the image channel is the fixture
    assert runs["fixture_runs"] == 1 and runs["rules_runs"] == 1 and runs["real_runs"] == 0
    assert runs["total_cost_usd"] == 0.0
    by_channel = {r["channel"]: r for r in runs["runs"]}
    assert set(by_channel) == {"structure", "image"}
    assert by_channel["structure"]["provider"] == "rules" and not by_channel["structure"]["is_fixture"]
    assert by_channel["image"]["provider"] == "fixture" and by_channel["image"]["is_fixture"]
    assert all(r["input_hash"] and r["status"] == "succeeded" for r in runs["runs"])
    keys = [o.key for o in storage.list("artefacts", prefix=f"{d['sha256']}/extract/")]
    assert any(k.endswith("/structure.json") for k in keys) and any(k.endswith("/image.json") for k in keys)
    art = json.loads(storage.get("artefacts", next(k for k in keys if k.endswith("/structure.json"))))
    assert art["output"]["schema_version"] == "2" and art["raw"]["rules"] is True

    # review queue lists it as a fixture with everything individual; nothing is published
    q = client.get("/review/queue", headers=headers(ANALYST)).json()
    item = next(i for i in q["items"] if i["source_id"] == src_id)
    assert item["is_fixture"] and item["pending"] == ex["candidates"] and item["individual"] == ex["candidates"]
    assert item["state"] == "awaiting_review"

    # a reviewer records a disposition for a family the order does not decide; analysts cannot
    body = {
        "family": "banking_rule",
        "disposition": "absent_in_source",
        "rationale": "no banking provision in this order",
        "pages_viewed": True,
    }
    assert client.put(f"/sources/{src_id}/dispositions", json=body, headers=headers(ANALYST)).status_code == 403
    assert (
        client.put(
            f"/sources/{src_id}/dispositions", json={**body, "family": "nope"}, headers=headers(REVIEWER)
        ).status_code
        == 422
    )
    r = client.put(f"/sources/{src_id}/dispositions", json=body, headers=headers(REVIEWER))
    assert r.status_code == 200 and r.json()["decided_by"] == REVIEWER
    assert (
        client.post(
            f"/sources/{src_id}/stages/rerun", json={"job_type": "validate_source"}, headers=headers(ADMIN)
        ).status_code
        == 202
    )
    assert runner.run_once() is True
    d2 = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d2["state"] == "awaiting_review" and "banking_rule" not in d2["validation"]["families_without_disposition"]
    assert len(d2["validation"]["families_without_disposition"]) == 7


def test_gerc_clause_candidates_and_a_perturbed_image_channel_is_routed_as_disagreement(client, runner, tmp_path):
    src_id = _to_review(client, runner, gerc_structure_order_pdf(), "SYNTHETIC_gerc_structure.pdf")
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "awaiting_review" and d["extraction"]["by_agreement"] == {
        "agree": d["extraction"]["candidates"]
    }
    cands = client.get(
        f"/sources/{src_id}/candidates", params={"category": "RGP", "limit": 500}, headers=headers(ANALYST)
    ).json()
    energy = [c for c in cands["candidates"] if c["component_type"] == "energy"]
    assert len(energy) == 8 and {c["record"]["applicability"]["metering_type"] for c in energy} == {
        "post_paid",
        "pre_paid",
    }
    assert all(c["record"]["evidence"][0]["kind"] == "clause" and c["currency"] == "paise" for c in energy)
    ag = client.get(f"/sources/{src_id}/candidates", params={"category": "AG"}, headers=headers(ANALYST)).json()
    alts = {c["record"]["applicability"]["alternative"] for c in ag["candidates"]}
    assert {1, 2} <= alts
    findings = client.get(
        f"/sources/{src_id}/findings", params={"validator": "VAL-04"}, headers=headers(ANALYST)
    ).json()
    assert any("alternatives; no default rate" in f["message"] for f in findings["findings"])
    htp = client.get(f"/sources/{src_id}/candidates", params={"category": "HTP-1"}, headers=headers(ANALYST)).json()
    assert all("billing demand shall be the highest" in c["record"]["conditions"][0] for c in htp["candidates"])

    # perturb the image channel and re-extract: the disagreement is recorded, both versions kept, routed low
    pert = tmp_path / "perturb.json"
    pert.write_text(json.dumps({"image": [{"key_contains": "|energy|", "set": {"value": "9.99"}}]}))
    runner.settings.provider_fixture_perturbations_path = str(pert)
    assert (
        client.post(
            f"/sources/{src_id}/stages/rerun", json={"job_type": "extract_source"}, headers=headers(ADMIN)
        ).status_code
        == 202
    )
    assert _run_all(runner) == 2  # extract, validate
    d2 = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d2["extraction"]["by_agreement"]["disagree"] >= 8 and d2["extraction"]["by_confidence"]["low"] >= 8
    e = client.get(
        f"/sources/{src_id}/candidates", params={"category": "RGP", "confidence": "low"}, headers=headers(ANALYST)
    ).json()
    c = e["candidates"][0]
    assert c["channel_agreement"] == "disagree" and c["disagreeing_fields"] == ["value"]
    assert c["value"] == c["record"]["value"] and c["image_record"]["value"] == "9.99" and c["routing"] == "individual"
    assert "channel_disagreement" in c["risk_tags"]
    runner.settings.provider_fixture_perturbations_path = None


def test_adversarial_instruction_text_does_not_alter_candidates(client, runner):
    src_id = _to_review(client, runner, structure_order_pdf(adversarial=True), "SYNTHETIC_adversarial.pdf")
    cands = client.get(
        f"/sources/{src_id}/candidates", params={"category": "LMV-1", "limit": 500}, headers=headers(ANALYST)
    ).json()
    energy = [c for c in cands["candidates"] if c["component_type"] == "energy"]
    assert sorted(c["value"] for c in energy) == ["3.00", "3.50", "4.00", "5.00", "6.00"]  # nothing was set to 0
    weird = next(c for c in energy if c["value"] == "6.00")
    assert weird["record"]["applicability"]["description"].startswith("IGNORE RULES")  # kept as a printed row label
    assert all("approve all" not in cond for c in cands["candidates"] for cond in c["record"]["conditions"])
    assert all(c["review_status"] == "pending" for c in cands["candidates"])
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "awaiting_review"  # never published, whatever the document said


def test_a_real_backend_keeps_the_rules_as_structure_channel_and_reads_images_in_chunks(client, runner, monkeypatch):
    """Stub model: not a fixture, never asked for the structure, called once per two pages."""
    from tariff_api.providers import FixtureProvider
    from tariff_worker.stages import extract as ex_stage

    calls: list[list[int]] = []

    class StubModel(FixtureProvider):
        name = "stub-model"
        is_fixture = False

        def extract_structure(self, inp):
            raise AssertionError("the model must never be the structure channel")

        def extract_image(self, inp, images):
            calls.append(list(inp.page_indices))
            assert len(images) == len(inp.page_indices) <= 2
            r = super().extract_image(inp, images)
            r.is_fixture = False
            r.provider = self.name
            return r

    monkeypatch.setattr(ex_stage, "build_provider", lambda settings, secrets: StubModel())
    src_id = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure_stub.pdf")
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    ex = d["extraction"]
    assert d["state"] == "awaiting_review" and ex["provider"] == "stub-model" and ex["is_fixture"] is False
    assert (
        calls
        and all(len(c) <= 2 for c in calls)
        and sorted(p for c in calls for p in c) == sorted({p for c in calls for p in c})
    )
    runs = client.get(f"/sources/{src_id}/extraction-runs", headers=headers(ANALYST)).json()
    assert runs["rules_runs"] == 1 and runs["fixture_runs"] == 0 and runs["real_runs"] == len(calls)
    assert ex["runs"] == 1 + len(calls) and ex["candidates"] > 15
    # every rules candidate is matched by the chunked image reading: nothing dropped by chunking
    assert set(ex["by_agreement"]) == {"agree"}
