"""Milestone 5a gate items at the API layer: approval without rendered evidence is impossible;
decisions against a stale version fail with `conflict_stale_version` and never overwrite;
corrections need a cause tag and an evidence selection and keep the original record; the
second-review policy routes material items and first-order candidates to a different
reviewer; undo restores the candidate from the decision's own snapshot and keeps the
history; batch approval is refused for anything but high-confidence, no-risk candidates and
still needs each candidate's evidence rendered.  Nothing here publishes."""

from __future__ import annotations

import shutil
import uuid

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import structure_order_pdf

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
    assert _run_all(runner) == 4
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert _run_all(runner) == 3
    return src_id


def _view(client, cand_id: str, user: str, index: int = 0) -> str:
    r = client.get(f"/candidates/{cand_id}/evidence/{index}/image", headers=headers(user))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    return r.headers["x-evidence-view-id"]


def test_decisions_need_rendered_evidence_current_versions_and_a_second_reviewer(client, runner):
    src_id = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure.pdf")

    # the per-order queue is ordered by risk first and says why; the checklist starts empty
    q = client.get(f"/sources/{src_id}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    assert q["total"] > 3 and [i["position"] for i in q["items"]] == list(range(1, q["total"] + 1))
    findings = [i["candidate"]["finding_count"] for i in q["items"]]
    assert findings[0] >= findings[-1] and findings[0] >= 1
    assert "finding" in q["items"][0]["reason"]
    assert all(i["candidate"]["review_status"] == "pending" for i in q["items"])
    filtered = client.get(
        f"/sources/{src_id}/review/queue", params={"risk": "new_profile"}, headers=headers(ANALYST)
    ).json()
    assert filtered["total"] == q["total"]  # first order read with this profile: everything carries new_profile
    cl = client.get(f"/sources/{src_id}/review/checklist", headers=headers(ANALYST)).json()
    assert cl["summary"].get("not_started", 0) >= 1 and cl["awaiting_second_review"] == 0
    assert any(i["kind"] == "category_component" and i["expected_from"] == "inventory" for i in cl["items"])
    assert all(i["status"] == "not_started" for i in cl["items"] if i["kind"] == "category_component")
    assert cl["second_review_policy"] == {"material": True, "first_order": True}

    c = q["items"][-1]["candidate"]  # a plain candidate (no finding) for the main path
    cid, version = c["id"], c["version"]

    # analysts can neither render evidence for a decision nor decide
    assert client.get(f"/candidates/{cid}/evidence/0/image", headers=headers(ANALYST)).status_code == 403
    approve = {"outcome": "approve", "expected_version": version}
    assert client.post(f"/candidates/{cid}/decision", json=approve, headers=headers(ANALYST)).status_code == 403

    # approval without the evidence rendered to this reviewer is impossible
    r = client.post(f"/candidates/{cid}/decision", json=approve, headers=headers(REVIEWER))
    assert r.status_code == 422 and r.json()["error_type"] == "validation_failed"
    assert r.json()["extra"]["evidence_required"] == [0]
    ev = client.get(f"/candidates/{cid}/evidence", headers=headers(REVIEWER)).json()
    assert ev["viewed_required"] is False and ev["views"] == [] and len(ev["evidence"]) >= 1

    view_id = _view(client, cid, REVIEWER)
    ev = client.get(f"/candidates/{cid}/evidence", headers=headers(REVIEWER)).json()
    assert ev["viewed_required"] is True and ev["views"][0]["id"] == view_id and ev["views"][0]["page_index"] >= 1
    # another reviewer's view is not this reviewer's
    other_view = _view(client, cid, ADMIN)
    r = client.post(
        f"/candidates/{cid}/decision",
        json={**approve, "evidence_view_ids": [other_view]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "not yours" in r.json()["detail"]

    # stale version: refused, nothing written
    r = client.post(
        f"/candidates/{cid}/decision",
        json={"outcome": "approve", "expected_version": version + 1, "evidence_view_ids": [view_id]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 409 and r.json()["error_type"] == "conflict_stale_version"
    assert r.json()["extra"]["current_version"] == version
    assert client.get(f"/candidates/{cid}", headers=headers(ANALYST)).json()["review_status"] == "pending"

    # first review of the first order from this utility: approved pending a second reviewer
    r = client.post(
        f"/candidates/{cid}/decision",
        json={**approve, "evidence_view_ids": [view_id], "time_spent_ms": 4200},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["decision"]["review_round"] == 1 and out["decision"]["evidence_viewed"] is True
    assert out["decision"]["view_to_decision_ms"] is not None and out["decision"]["time_spent_ms"] == 4200
    assert out["candidate"]["review_status"] == "awaiting_second_review"
    assert out["candidate"]["second_review"] == "pending" and out["candidate"]["version"] == version + 1
    assert "first_order_from_utility" in out["decision"]["after"]["second_review_reasons"]
    assert out["candidate"]["first_reviewer"] == REVIEWER

    # the same reviewer cannot be the second reviewer; a different one can
    r = client.post(
        f"/candidates/{cid}/decision",
        json={"outcome": "approve", "expected_version": version + 1, "evidence_view_ids": [view_id]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "different reviewer" in r.json()["detail"]
    r = client.post(
        f"/candidates/{cid}/decision",
        json={"outcome": "approve", "expected_version": version + 1, "evidence_view_ids": [other_view]},
        headers=headers(ADMIN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["review_status"] == "approved" and r.json()["candidate"]["second_review"] == "done"
    assert r.json()["decision"]["review_round"] == 2
    # decided candidates cannot be decided again without undo
    r = client.post(
        f"/candidates/{cid}/decision",
        json={"outcome": "reject", "expected_version": version + 2, "rationale": "changed my mind"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 409 and r.json()["error_type"] == "invalid_transition"
    audit = client.get("/audit", params={"entity_type": "candidate", "entity_id": cid}, headers=headers(ADMIN)).json()
    assert [a["action"] for a in audit] == ["candidate.approve", "candidate.approve"]
    assert {a["before"]["review_status"] for a in audit} == {"pending", "awaiting_second_review"}
    assert {a["after"]["review_status"] for a in audit} == {"awaiting_second_review", "approved"}

    # idempotency: the same request with the same key replays; a different one conflicts
    c2 = q["items"][-2]["candidate"]
    v2 = _view(client, c2["id"], REVIEWER)
    body2 = {"outcome": "approve", "expected_version": c2["version"], "evidence_view_ids": [v2]}
    key = str(uuid.uuid4())
    r1 = client.post(
        f"/candidates/{c2['id']}/decision", json=body2, headers=headers(REVIEWER, **{"Idempotency-Key": key})
    )
    assert r1.status_code == 200 and r1.json()["idempotent_replay"] is False
    r2 = client.post(
        f"/candidates/{c2['id']}/decision", json=body2, headers=headers(REVIEWER, **{"Idempotency-Key": key})
    )
    assert r2.status_code == 200 and r2.json()["idempotent_replay"] is True
    assert r2.json()["decision"]["id"] == r1.json()["decision"]["id"]
    assert client.get(f"/candidates/{c2['id']}/decisions", headers=headers(ANALYST)).json()["total"] == 1
    r3 = client.post(
        f"/candidates/{c2['id']}/decision",
        json={**body2, "rationale": "x"},
        headers=headers(REVIEWER, **{"Idempotency-Key": key}),
    )
    assert r3.status_code == 409 and r3.json()["error_type"] == "idempotency_conflict"

    # correction: cause tag and evidence selection are mandatory; the original record stays
    c3 = q["items"][-3]["candidate"]
    v3 = _view(client, c3["id"], REVIEWER)
    base = {"outcome": "correct", "expected_version": c3["version"], "evidence_view_ids": [v3]}
    r = client.post(
        f"/candidates/{c3['id']}/decision", json={**base, "correction": {"value": "9.99"}}, headers=headers(REVIEWER)
    )
    assert r.status_code == 422 and "rationale" in r.json()["detail"]
    base["rationale"] = "cell reads 9.99 in the source; the reader dropped a digit"
    r = client.post(
        f"/candidates/{c3['id']}/decision", json={**base, "correction": {"value": "9.99"}}, headers=headers(REVIEWER)
    )
    assert r.status_code == 422 and "cause tag" in r.json()["detail"]
    base["cause_tag"] = "ocr"
    r = client.post(
        f"/candidates/{c3['id']}/decision", json={**base, "correction": {"value": "9.99"}}, headers=headers(REVIEWER)
    )
    assert r.status_code == 422 and "select its evidence" in r.json()["detail"]
    r = client.post(
        f"/candidates/{c3['id']}/decision",
        json={**base, "correction": {"value": "not a number"}, "evidence_indices": [0]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "decimal" in r.json()["detail"]
    r = client.post(
        f"/candidates/{c3['id']}/decision",
        json={**base, "correction": {"value": "9.99", "bogus": 1}, "evidence_indices": [0]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "bogus" in r.json()["detail"]
    r = client.post(
        f"/candidates/{c3['id']}/decision",
        json={**base, "correction": {"value": "9.99"}, "evidence_indices": [0]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["decision"]["cause_tag"] == "ocr" and out["decision"]["corrected_fields"] == ["value"]
    assert out["candidate"]["reviewed_record"]["value"] == "9.99" and out["candidate"]["record"]["value"] == c3["value"]
    assert (
        out["candidate"]["value"] == c3["value"]
    )  # the column is the extractor's reading; the correction is the record
    assert out["candidate"]["review_status"] == "awaiting_second_review"
    assert out["decision"]["after"]["revalidation_job_id"] is not None
    # the correction re-runs the validators over the effective records; review state survives
    assert runner.run_once() is True
    c3b = client.get(f"/candidates/{c3['id']}", headers=headers(ANALYST)).json()
    assert c3b["review_status"] == "awaiting_second_review" and c3b["reviewed_record"]["value"] == "9.99"
    assert client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()["state"] == "awaiting_review"

    # reject and unresolved need a rationale; neither needs a second review
    c4 = q["items"][-4]["candidate"]
    r = client.post(
        f"/candidates/{c4['id']}/decision",
        json={"outcome": "reject", "expected_version": c4["version"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422
    r = client.post(
        f"/candidates/{c4['id']}/decision",
        json={
            "outcome": "reject",
            "expected_version": c4["version"],
            "rationale": "this row is an illustration, not a rate",
        },
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200 and r.json()["candidate"]["review_status"] == "rejected"
    rejected_decision = r.json()["decision"]["id"]

    # undo: only the deciding reviewer, only the latest decision, history intact
    assert client.post(f"/review/decisions/{rejected_decision}/undo", headers=headers(ANALYST)).status_code == 403
    r = client.post(f"/review/decisions/{rejected_decision}/undo", headers=headers(ADMIN))
    assert r.status_code == 403 and r.json()["error_type"] == "permission_denied"
    r = client.post(f"/review/decisions/{rejected_decision}/undo", headers=headers(REVIEWER))
    assert r.status_code == 200, r.text
    assert r.json()["candidate"]["review_status"] == "pending" and r.json()["decision"]["undone"] is True
    assert r.json()["candidate"]["version"] == c4["version"] + 2
    hist = client.get(f"/candidates/{c4['id']}/decisions", headers=headers(ANALYST)).json()
    assert hist["total"] == 1 and hist["decisions"][0]["undone_by"] == REVIEWER
    assert client.post(f"/review/decisions/{rejected_decision}/undo", headers=headers(REVIEWER)).status_code == 409
    r = client.post(
        f"/candidates/{c4['id']}/decision",
        json={
            "outcome": "unresolved",
            "expected_version": c4["version"] + 2,
            "rationale": "needs the footnote on the next page",
        },
        headers=headers(REVIEWER),
    )
    assert r.status_code == 200 and r.json()["candidate"]["review_status"] == "unresolved"

    # the checklist and queues reflect the decisions; telemetry has no document text
    cl = client.get(f"/sources/{src_id}/review/checklist", headers=headers(ANALYST)).json()
    assert cl["unresolved"] == 1 and cl["awaiting_second_review"] == 2  # c2 (approve) and c3 (correct)
    assert cl["candidates"]["approved"] == 1 and cl["candidates"]["unresolved"] == 1
    assert any(i["status"] in ("in_progress", "approved", "unresolved") for i in cl["items"])
    qd = client.get(f"/sources/{src_id}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    assert qd["total"] == q["total"] - 2  # c (approved) and c4 (unresolved) left the open queue
    assert client.get("/review/queue", headers=headers(ANALYST)).json()["total_pending"] == q["total"] - 2
    t = client.get("/review/telemetry", params={"source_id": src_id}, headers=headers(ANALYST)).json()
    assert t["outcomes"] == {"approve": 3, "correct": 1, "unresolved": 1} and t["undone"] == 1
    assert t["second_reviews"] == 1 and t["corrections_by_cause"] == {"ocr": 1}
    assert "new_profile" in t["review_ms_by_risk_tag"] and t["review_ms_by_risk_tag"]["new_profile"]["n"] == 4
    assert client.get(f"/sources/{src_id}/decisions", headers=headers(ANALYST)).json()["total"] == 6


def test_batch_approval_is_limited_to_high_confidence_no_risk_candidates_each_with_evidence(client, runner):
    # a first order carries `new_profile` on everything, so nothing is batch-eligible there
    first = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure.pdf")
    q1 = client.get(f"/sources/{first}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    assert all(i["candidate"]["routing"] == "individual" for i in q1["items"])
    # the second order from the same profile routes clean candidates to batch review
    second = _to_review(client, runner, structure_order_pdf(adversarial=True), "SYNTHETIC_structure_adv.pdf")
    q2 = client.get(f"/sources/{second}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    batch = [i["candidate"] for i in q2["items"] if i["candidate"]["routing"] == "batch"]
    individual = [i["candidate"] for i in q2["items"] if i["candidate"]["routing"] == "individual"]
    assert len(batch) >= 2 and individual, "fixture should yield both routings on a second order"
    assert q2["items"][0]["candidate"]["routing"] == "individual"  # risk first

    a, b = batch[0], batch[1]
    ind = individual[0]
    va = _view(client, a["id"], REVIEWER)
    vi = _view(client, ind["id"], REVIEWER)
    items = [
        {"candidate_id": a["id"], "expected_version": a["version"], "evidence_view_ids": [va]},
        {"candidate_id": b["id"], "expected_version": b["version"], "evidence_view_ids": []},  # never rendered
        {"candidate_id": ind["id"], "expected_version": ind["version"], "evidence_view_ids": [vi]},
        {"candidate_id": str(uuid.uuid4()), "expected_version": 1, "evidence_view_ids": []},
    ]
    assert client.post("/review/batch", json={"items": items}, headers=headers(ANALYST)).status_code == 403
    r = client.post("/review/batch", json={"items": items}, headers=headers(REVIEWER))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["approved"] == 1 and out["refused"] == 3
    by_id = {x["candidate_id"]: x for x in out["results"]}
    assert by_id[a["id"]]["ok"] is True and by_id[a["id"]]["review_status"] == "approved"
    assert by_id[b["id"]]["error_type"] == "validation_failed" and "rendered" in by_id[b["id"]]["message"]
    assert by_id[ind["id"]]["error_type"] == "validation_failed" and "individual" in by_id[ind["id"]]["message"]
    assert by_id[items[3]["candidate_id"]]["error_type"] == "not_found"
    # a refused item never blocks the others: `a` is approved, `b` untouched
    assert client.get(f"/candidates/{b['id']}", headers=headers(ANALYST)).json()["review_status"] == "pending"
    assert client.get(f"/candidates/{a['id']}", headers=headers(ANALYST)).json()["review_status"] == "approved"
    # batch never bypasses the second-review policy: a material candidate goes to second review
    material = [
        i["candidate"]
        for i in q2["items"]
        if i["candidate"]["component_type"] == "condition" and i["candidate"]["routing"] == "batch"
    ]
    if material:
        m = material[0]
        vm = _view(client, m["id"], REVIEWER)
        r = client.post(
            "/review/batch",
            json={"items": [{"candidate_id": m["id"], "expected_version": m["version"], "evidence_view_ids": [vm]}]},
            headers=headers(REVIEWER),
        )
        assert r.json()["results"][0]["review_status"] == "awaiting_second_review"


def test_one_page_render_issues_a_view_per_candidate_on_that_page_and_those_views_decide(client, runner):
    import json

    src_id = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure_pageview.pdf")
    q = client.get(f"/sources/{src_id}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    by_page: dict[int, list[dict]] = {}
    for it in q["items"]:
        by_page.setdefault(it["page_index"], []).append(it["candidate"])
    page, cands = max(by_page.items(), key=lambda kv: len(kv[1]))
    assert len(cands) >= 2
    other_page = next(p for p in by_page if p != page)
    stranger = by_page[other_page][0]
    ids = ",".join([c["id"] for c in cands] + [stranger["id"]])

    # analysts cannot render for a decision
    r = client.get(f"/sources/{src_id}/review/pages/{page}/image", params={"candidates": ids}, headers=headers(ANALYST))
    assert r.status_code == 403
    r = client.get(
        f"/sources/{src_id}/review/pages/{page}/image", params={"candidates": ids}, headers=headers(REVIEWER)
    )
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    views = json.loads(r.headers["x-evidence-view-ids"])
    assert set(views) == {c["id"] for c in cands} and json.loads(r.headers["x-evidence-skipped"]) == [stranger["id"]]

    # every candidate on the page now decides with its own view from that single render
    for c in cands[:2]:
        r = client.post(
            f"/candidates/{c['id']}/decision",
            json={"outcome": "approve", "expected_version": c["version"], "evidence_view_ids": [views[c["id"]]]},
            headers=headers(REVIEWER),
        )
        assert r.status_code == 200, r.text
        assert r.json()["decision"]["outcome"] == "approve" and r.json()["decision"]["evidence_viewed"] is True
    # the skipped one has no view: refused as before
    r = client.post(
        f"/candidates/{stranger['id']}/decision",
        json={"outcome": "approve", "expected_version": stranger["version"], "evidence_view_ids": []},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422
    # a bad id list is a validation error, not a crash
    r = client.get(
        f"/sources/{src_id}/review/pages/{page}/image", params={"candidates": "nope"}, headers=headers(REVIEWER)
    )
    assert r.status_code == 422
