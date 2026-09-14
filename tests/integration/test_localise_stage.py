"""Milestone 3a gate items: the localisation stage runs after parse, records regions with
cues, halts on ambiguity, and opens a reviewer checkpoint that the rules can never pass on
their own; the reviewer's decision is role-gated, versioned and audited; an administrator can
assign a profile and the stage re-runs."""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import gerc_like_order_pdf, kerc_like_order_pdf, uperc_like_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]


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


def test_uperc_layout_is_localised_and_confirmed_by_a_reviewer(client, runner, storage):
    src_id = _upload(client, uperc_like_order_pdf(), "SYNTHETIC_uperc_like.pdf")
    assert _run_all(runner) == 4  # inventory -> triage -> parse -> localise
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised"
    assert d["reading_profile"] == {
        "profile_id": "uperc-npcl",
        "version": 1,
        "source": "detected",
        "rationale": "3 `rate_schedule` headings in the inventory",
    }
    assert d["localisation"]["status"] == "proposed" and d["localisation"]["extraction_allowed"] is False
    assert d["localisation"]["approved_schedule_pages"] == ["8-11"]

    L = client.get(f"/sources/{src_id}/localisation", headers=headers(ANALYST)).json()
    roles = {(r["role"], r["sub_role"]): (r["page_start"], r["page_end"]) for r in L["regions"]}
    assert roles[("approved_schedule", None)] == (8, 11)
    assert roles[("derived_not_tariff", None)] == (12, 12)
    assert roles[("other", None)] == (13, 14)
    assert roles[("network_charges", "additional_surcharge")] == (7, 7)
    approved = next(r for r in L["regions"] if r["role"] == "approved_schedule")
    assert approved["cue_text"].startswith("12.1 ANNEXURE-I: RATE SCHEDULE") and approved["origin"] == "detected"
    assert approved["grid_count"] == 3  # the three ruled RATE SCHEDULE tables sit inside the region
    assert L["profile_ref"] == "uperc-npcl@1" and L["decided_by"] is None
    art = json.loads(storage.get("artefacts", L["artefact_key"]))
    # the scans have no text layer, so their text came from the parse stage's OCR artefacts;
    # they are still classed `other` by page class, never by what the OCR read
    assert art["status"] == "proposed" and art["page_text_sources"]["13"] == "ocr"

    # the checkpoint is a human boundary: analysts cannot decide, reviewers can
    body = {
        "decision": "confirm",
        "rationale": "Annexure-I is the approved schedule; pages checked",
        "pages_viewed": True,
    }
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=body, headers=headers(ANALYST)).status_code == 403
    )
    unseen = {**body, "pages_viewed": False}
    r = client.post(f"/sources/{src_id}/localisation/decision", json=unseen, headers=headers(REVIEWER))
    assert r.status_code == 422 and r.json()["error_type"] == "validation_failed"
    stale = {**body, "expected_version": L["version"] + 5}
    r = client.post(f"/sources/{src_id}/localisation/decision", json=stale, headers=headers(REVIEWER))
    assert r.status_code == 409 and r.json()["error_type"] == "conflict_stale_version"
    r = client.post(
        f"/sources/{src_id}/localisation/decision",
        json={**body, "expected_version": L["version"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "confirmed" and out["extraction_allowed"] is True
    assert out["decided_by"] == REVIEWER and out["decision_count"] == 1 and out["version"] == L["version"] + 1
    audit = client.get(
        "/audit", params={"entity_type": "localisation_record", "entity_id": src_id}, headers=headers(ADMIN)
    ).json()
    assert [a["action"] for a in audit] == ["localisation.confirm"]
    assert audit[0]["before"]["status"] == "proposed" and audit[0]["after"]["status"] == "confirmed"
    assert len(audit[0]["before"]["regions"]) == len(L["regions"])


def test_ambiguous_localisation_halts_until_a_reviewer_corrects(client, runner):
    src_id = _upload(client, uperc_like_order_pdf(second_annexure=True), "SYNTHETIC_uperc_two_annexures.pdf")
    assert _run_all(runner) == 4
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised"
    assert d["localisation"]["status"] == "ambiguous" and d["localisation"]["blocking_findings"] == 1
    L = client.get(f"/sources/{src_id}/localisation", headers=headers(ANALYST)).json()
    assert [f["code"] for f in L["findings"] if f["severity"] == "blocking"] == [
        "multiple_approved_schedule_candidates"
    ]
    assert [(r["page_start"], r["page_end"]) for r in L["regions"] if r["role"] == "approved_schedule"] == [
        (8, 11),
        (13, 16),
    ]

    # confirming an ambiguous record is refused: the reviewer must say which one
    r = client.post(
        f"/sources/{src_id}/localisation/decision",
        json={"decision": "confirm", "rationale": "looks fine", "pages_viewed": True},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "correct the regions" in r.json()["detail"]

    corrected = {
        "decision": "correct",
        "rationale": "The first annexure is the approved schedule; the second is a reprint of the draft",
        "pages_viewed": True,
        "regions": [
            {"role": "approved_schedule", "page_start": 8, "page_end": 11, "note": "Annexure-I"},
            {"role": "derived_not_tariff", "page_start": 12, "page_end": 12},
            {"role": "illustrative", "page_start": 13, "page_end": 16, "note": "reprint, not binding"},
        ],
    }
    bad = {**corrected, "regions": [{"role": "approved_schedule", "page_start": 8, "page_end": 99}]}
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=bad, headers=headers(REVIEWER)).status_code == 422
    )
    none = {**corrected, "regions": [{"role": "other", "page_start": 1, "page_end": 2}]}
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=none, headers=headers(REVIEWER)).status_code == 422
    )
    r = client.post(f"/sources/{src_id}/localisation/decision", json=corrected, headers=headers(ADMIN))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "corrected" and out["extraction_allowed"] is True
    assert [(x["role"], x["page_start"], x["page_end"], x["origin"]) for x in out["regions"]] == [
        ("approved_schedule", 8, 11, "reviewer"),
        ("derived_not_tariff", 12, 12, "reviewer"),
        ("illustrative", 13, 16, "reviewer"),
    ]
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["localisation"]["approved_schedule_pages"] == ["8-11"] and d["localisation"]["status"] == "corrected"


def test_kerc_and_gerc_layouts_detect_their_profiles(client, runner):
    k = _upload(client, kerc_like_order_pdf(), "SYNTHETIC_kerc_like.pdf")
    g = _upload(client, gerc_like_order_pdf(), "SYNTHETIC_gerc_like.pdf")
    assert _run_all(runner) == 8
    dk = client.get(f"/sources/{k}", headers=headers(ANALYST)).json()
    dg = client.get(f"/sources/{g}", headers=headers(ANALYST)).json()
    assert dk["reading_profile"]["profile_id"] == "kerc-escoms" and dk["localisation"]["approved_schedule_pages"] == [
        "7-11"
    ]
    assert dg["reading_profile"]["profile_id"] == "gerc-discoms" and dg["localisation"]["approved_schedule_pages"] == [
        "6-11"
    ]
    lk = client.get(f"/sources/{k}/localisation", headers=headers(ANALYST)).json()
    per_escom = [(r["utility"], r["page_start"]) for r in lk["regions"] if r["role"] == "existing_tariff"]
    assert per_escom == [("BESCOM", 3), ("MESCOM", 4)]
    assert any(r["role"] == "approved_summary" for r in lk["regions"])
    lg = client.get(f"/sources/{g}/localisation", headers=headers(ANALYST)).json()
    assert {r["role"] for r in lg["regions"]} >= {"approved_schedule", "amendment_diff", "formula_parameters"}


def test_admin_assigns_a_profile_and_the_stage_reruns_reopening_the_checkpoint(client, runner):
    src_id = _upload(client, gerc_like_order_pdf(), "SYNTHETIC_gerc_like.pdf")
    assert _run_all(runner) == 4
    ok = {"decision": "confirm", "rationale": "clause schedule located; pages checked", "pages_viewed": True}
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=ok, headers=headers(REVIEWER)).status_code == 200
    )

    # analysts cannot assign; an unknown profile is refused; the wrong profile is allowed but visible
    body = {"profile_id": "uperc-npcl", "reason": "testing a deliberate mis-assignment"}
    assert client.put(f"/sources/{src_id}/profile", json=body, headers=headers(ANALYST)).status_code == 403
    missing = client.put(f"/sources/{src_id}/profile", json={**body, "profile_id": "nope-x"}, headers=headers(ADMIN))
    assert missing.status_code == 404
    r = client.put(f"/sources/{src_id}/profile", json=body, headers=headers(ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["reading_profile"]["source"] == "assigned" and r.json()["localisation"] is None
    assert runner.run_once() is True  # the re-queued localisation
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert d["state"] == "localised" and d["localisation"]["status"] == "ambiguous"
    L = client.get(f"/sources/{src_id}/localisation", headers=headers(ANALYST)).json()
    assert L["profile_ref"] == "uperc-npcl@1" and L["extraction_allowed"] is False and L["decided_by"] is None
    assert any(f["code"] == "approved_schedule_not_found" for f in L["findings"])
    audit = client.get(
        "/audit", params={"entity_type": "source_document", "entity_id": src_id}, headers=headers(ADMIN)
    ).json()
    assert any(a["action"] == "source.profile_assigned" for a in audit)
    assert client.get("/profiles", headers=headers(ANALYST)).json()["profiles"][0]["id"] == "gerc-discoms"
